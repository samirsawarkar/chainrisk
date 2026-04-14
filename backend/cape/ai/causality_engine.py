"""Ledger-backed causal chains with strict tick windows (no event dumps)."""

from __future__ import annotations

from cape.db import get_redis_client
from cape.ledger.adapter import _get_pg_conn
from cape.metrics.amplification import compute_canonical_edge_metrics, discover_chain_nodes

_CHAIN_ORDER = ("RET-01", "DIST-01", "MFG-01", "SUP-01")


def _scenario_sku_min_max(r, sku: str, t0: int, t1: int) -> tuple[int, int, int, int]:
    vals: list[tuple[int, int]] = []
    for t in range(int(t0), int(t1) + 1):
        d = int(r.hget(f"cape:scenario:demand:{t}", sku) or 0)
        vals.append((t, d))
    if not vals:
        return 0, 0, t0, t0
    mn = min(vals, key=lambda x: x[1])
    mx = max(vals, key=lambda x: x[1])
    return mn[1], mx[1], mn[0], mx[0]


def _ret_order_sku_tick(cur, sku: str, tick: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity_ordered), 0)
        FROM orders
        WHERE from_node LIKE 'RET-%%' AND sku_id = %s AND tick_placed = %s
        """,
        (sku, int(tick)),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def _dist_order_sku_tick(cur, sku: str, tick: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity_ordered), 0)
        FROM orders
        WHERE from_node LIKE 'DIST-%%' AND sku_id = %s AND tick_placed = %s
        """,
        (sku, int(tick)),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def _system_backlog_tick(cur, tick: int) -> int:
    cur.execute("SELECT COALESCE(SUM(backlog), 0) FROM inventory_state WHERE tick = %s", (int(tick),))
    row = cur.fetchone()
    return int(row[0] or 0)


def get_causal_chain(node_id: str | None, tick_lo: int, tick_hi: int) -> dict:
    """
    1) First tick in [tick_lo, tick_hi] where utilization ≥ 95% for the node (else peak in range).
    2) Largest inbound order to that node at or before that tick (within range).
    3) Two-tier upstream lines (RET scenario + DIST orders) + canonical amplification.
    """
    target = (node_id or "DIST-01").strip().upper()
    lo, hi = int(tick_lo), int(tick_hi)
    if hi < lo:
        lo, hi = hi, lo
    r = get_redis_client()
    note: str | None = None
    amp = 1.0
    sku = "UNKNOWN"
    trigger_tick = hi
    cap_pct = 0.0
    inc_qty = 0
    inc_tick = hi
    from_n = "?"

    with _get_pg_conn() as conn, conn.cursor() as cur:
        ret_id, dist_id, _, _ = discover_chain_nodes(cur)
        cur.execute(
            """
            SELECT tick, utilization_pct
            FROM capacity_state
            WHERE node_id = %s AND tick BETWEEN %s AND %s
            ORDER BY tick ASC
            """,
            (target, lo, hi),
        )
        cap_rows = cur.fetchall()
        trigger_tick = None
        for tk, util in cap_rows:
            u = float(util or 0.0)
            if u >= 95.0:
                trigger_tick = int(tk)
                cap_pct = u
                break
        if trigger_tick is None and cap_rows:
            trigger_tick, cap_pct = int(cap_rows[-1][0]), float(cap_rows[-1][1] or 0.0)
            note = f"No util≥95% in T{lo}–T{hi}; using peak in window (T{trigger_tick})."
        if trigger_tick is None:
            trigger_tick = hi
            cur.execute(
                "SELECT utilization_pct FROM capacity_state WHERE node_id = %s AND tick = %s LIMIT 1",
                (target, hi),
            )
            row = cur.fetchone()
            cap_pct = float(row[0] or 0.0) if row else 0.0
            note = f"No capacity rows in T{lo}–T{hi}; using T{hi}."

        cur.execute(
            """
            SELECT sku_id, from_node, quantity_ordered, tick_placed
            FROM orders
            WHERE to_node = %s AND tick_placed BETWEEN %s AND %s AND tick_placed <= %s
            ORDER BY quantity_ordered DESC
            LIMIT 1
            """,
            (target, lo, hi, trigger_tick),
        )
        inc = cur.fetchone()
        if inc and inc[0]:
            sku = str(inc[0])
            from_n = str(inc[1] or "?")
            inc_qty = int(inc[2] or 0)
            inc_tick = int(inc[3] or 0)

        lines: list[str] = []
        if sku != "UNKNOWN":
            mn, mx, tmn, tmx = _scenario_sku_min_max(r, sku, lo, hi)
            lines.append(f"RET demand {sku}: {mn} → {mx} (T{tmn}–T{tmx})")
            rtick = min(max(lo, trigger_tick), hi)
            dtick = min(max(lo, trigger_tick + 1), hi)
            ro = _ret_order_sku_tick(cur, sku, rtick)
            do = _dist_order_sku_tick(cur, sku, dtick)
            lines.append(f"RET order {sku}: {ro} (T{rtick})")
            lines.append(f"DIST order {sku}: {do} (T{dtick})")
        lines.append(f"{target} inbound peak: {from_n}→{target} qty={inc_qty} (T{inc_tick})")
        lines.append(f"{target} capacity: {cap_pct:.1f}% (T{trigger_tick})")
        bl_tick = min(hi, trigger_tick + 1)
        bl = _system_backlog_tick(cur, bl_tick)
        lines.append(f"Backlog created (system total): {bl} units (T{bl_tick})")

        canon = compute_canonical_edge_metrics(cur, r, lo, hi, sku=sku if sku != "UNKNOWN" else None)
        rd_key = f"{ret_id}|{dist_id}"
        amp = float(canon["edges"].get(rd_key, {}).get("ratio", canon["ratios"]["dist_over_ret"]))
        lines.append(f"RET→DIST amplification: {amp:.2f}× (window T{lo}–T{hi}, metrics formula)")

    return {
        "lines": lines,
        "tick_range_used": [lo, hi],
        "nearest_tick_note": note,
        "sku": sku,
        "trigger_tick": trigger_tick,
        "capacity_util_pct": round(cap_pct, 2),
        "incoming_order_qty": inc_qty,
        "incoming_from": from_n,
        "amplification_ret_dist": round(amp, 4),
    }


def get_root_cause(node_id: str | None, tick_hi: int, tick_lo: int | None = None) -> dict:
    hi = int(tick_hi)
    lo = int(tick_lo) if tick_lo is not None else max(0, hi - 5)
    if lo > hi:
        lo, hi = hi, lo
    c = get_causal_chain(node_id, lo, hi)
    return {
        "sku": c.get("sku", "UNKNOWN"),
        "trigger_tick": c.get("trigger_tick"),
        "trigger_node": (node_id or "DIST-01").strip().upper(),
        "capacity_util_pct": float(c.get("capacity_util_pct", 0.0)),
        "incoming_order_qty": int(c.get("incoming_order_qty", 0)),
        "incoming_from": str(c.get("incoming_from", "")),
        "dist_amplification_vs_ret": float(c.get("amplification_ret_dist", 1.0)),
        "chain": c.get("lines") or [],
        "chain_roles": "RET → DIST → MFG → SUP",
        "tick_range_used": c.get("tick_range_used") or [lo, hi],
        "nearest_tick_note": c.get("nearest_tick_note"),
    }


def chain_template() -> str:
    return " → ".join(_CHAIN_ORDER)
