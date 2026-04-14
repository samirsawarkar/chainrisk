"""
Single source of truth for supply-chain amplification.

Formula (per edge, over a tick window [t0, t1]):
  amplification = orders_on_arc / max(demand_downstream, 1)

- RET→DIST: orders = SUM(orders) where from=RET, to=DIST; demand = SUM(scenario retail demand all SKUs) per tick, summed over window.
- DIST→MFG: demand = SUM(RET→DIST orders) in window; orders = SUM(DIST→MFG orders).
- MFG→SUP: demand = SUM(DIST→MFG orders); orders = SUM(MFG→SUP orders).

All values come from orders table + Redis scenario keys only.
"""

from __future__ import annotations

from typing import Any

import redis

_MAX_AMP = 10.0


def _scenario_total_at_tick(r: redis.Redis, tick: int) -> int:
    h = r.hgetall(f"cape:scenario:demand:{int(tick)}") or {}
    return sum(int(v or 0) for v in h.values())


def _orders_arc_sum(cur, from_prefix: str, to_prefix: str, t0: int, t1: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity_ordered), 0)
        FROM orders
        WHERE from_node LIKE %s AND to_node LIKE %s
          AND tick_placed BETWEEN %s AND %s
        """,
        (from_prefix, to_prefix, t0, t1),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def _orders_arc_sum_sku(cur, from_prefix: str, to_prefix: str, sku: str, t0: int, t1: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity_ordered), 0)
        FROM orders
        WHERE from_node LIKE %s AND to_node LIKE %s AND sku_id = %s
          AND tick_placed BETWEEN %s AND %s
        """,
        (from_prefix, to_prefix, sku, t0, t1),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def scenario_sku_demand_sum(r: redis.Redis, sku: str, t0: int, t1: int) -> int:
    s = 0
    for t in range(int(t0), int(t1) + 1):
        s += int(r.hget(f"cape:scenario:demand:{t}", sku) or 0)
    return s


def compute_amplification(
    cur,
    r: redis.Redis,
    from_node: str,
    to_node: str,
    sku: str | None,
    start_tick: int,
    end_tick: int,
) -> dict[str, Any]:
    """
    Single canonical ratio for one directed edge in [start_tick, end_tick].
    from_node / to_node are full ids (e.g. RET-01, DIST-01).
    """
    t0, t1 = int(start_tick), int(end_tick)
    if t1 < t0:
        t0, t1 = t1, t0
    fp = f"{from_node}%"
    tp = f"{to_node}%"
    if sku:
        orders = _orders_arc_sum_sku(cur, fp, tp, sku, t0, t1)
        if from_node.upper().startswith("RET"):
            demand = scenario_sku_demand_sum(r, sku, t0, t1)
        elif from_node.upper().startswith("DIST"):
            demand = _orders_arc_sum(cur, "RET%", f"{from_node}%", t0, t1)
        else:
            demand = _orders_arc_sum_sku(cur, "DIST%", f"{from_node}%", sku, t0, t1)
    else:
        orders = _orders_arc_sum(cur, fp, tp, t0, t1)
        if from_node.upper().startswith("RET"):
            demand = sum(_scenario_total_at_tick(r, t) for t in range(t0, t1 + 1))
        elif from_node.upper().startswith("DIST"):
            demand = _orders_arc_sum(cur, "RET%", f"{from_node}%", t0, t1)
        else:
            demand = _orders_arc_sum(cur, "DIST%", f"{from_node}%", t0, t1)

    ratio = min(_MAX_AMP, max(1.0, orders / max(demand, 1)))
    return {"ratio": round(ratio, 4), "orders": int(orders), "demand": int(demand), "from_node": from_node, "to_node": to_node, "sku": sku}


def _one_node(cur, node_type: str, fallback: str) -> str:
    cur.execute(
        "SELECT node_id FROM sc_nodes WHERE lower(node_type) = %s ORDER BY node_id LIMIT 1",
        (node_type.lower(),),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else fallback


def discover_chain_nodes(cur) -> tuple[str, str, str, str]:
    """Return (ret, dist, mfg, sup) node ids from sc_nodes if present."""
    return (
        _one_node(cur, "retailer", "RET-01"),
        _one_node(cur, "distributor", "DIST-01"),
        _one_node(cur, "manufacturer", "MFG-01"),
        _one_node(cur, "supplier", "SUP-01"),
    )


def compute_canonical_edge_metrics(cur, r: redis.Redis, start_tick: int, end_tick: int, sku: str | None = None) -> dict[str, Any]:
    """All edges + rolled-up ratios used everywhere (chat, charts metadata, persistence)."""
    t0, t1 = int(start_tick), int(end_tick)
    if t1 < t0:
        t0, t1 = t1, t0
    ret_id, dist_id, mfg_id, sup_id = discover_chain_nodes(cur)
    e_rd = compute_amplification(cur, r, ret_id, dist_id, sku, t0, t1)
    e_dm = compute_amplification(cur, r, dist_id, mfg_id, sku, t0, t1)
    e_ms = compute_amplification(cur, r, mfg_id, sup_id, sku, t0, t1)
    edges: dict[str, dict[str, Any]] = {
        f"{ret_id}|{dist_id}": e_rd,
        f"{dist_id}|{mfg_id}": e_dm,
        f"{mfg_id}|{sup_id}": e_ms,
    }
    dist_over_ret = e_rd["ratio"]
    mfg_over_dist = e_dm["ratio"]
    sup_over_mfg = e_ms["ratio"]
    peak = min(_MAX_AMP, max(dist_over_ret, mfg_over_dist, sup_over_mfg))
    return {
        "edges": edges,
        "ratios": {
            "dist_over_ret": round(dist_over_ret, 4),
            "mfg_over_dist": round(mfg_over_dist, 4),
            "sup_over_mfg": round(sup_over_mfg, 4),
        },
        "global_index": round(max(1.0, peak), 4),
        "ret_node": ret_id,
        "dist_node": dist_id,
        "mfg_node": mfg_id,
        "sup_node": sup_id,
    }


def enrich_bullwhip_stats(conn, r: redis.Redis, start_tick: int, end_tick: int, bullwhip_payload: dict) -> dict:
    """Attach canonical ratios to bullwhip JSON (same orders series; stats from amplification)."""
    with conn.cursor() as cur:
        canon = compute_canonical_edge_metrics(cur, r, start_tick, end_tick)
    stats = dict(bullwhip_payload.get("stats") or {})
    stats["canonical"] = canon["ratios"]
    stats["canonical_global"] = canon["global_index"]
    stats["canonical_edges"] = {k: {"ratio": v["ratio"], "orders": v["orders"], "demand": v["demand"]} for k, v in canon["edges"].items()}
    out = dict(bullwhip_payload)
    out["stats"] = stats
    return out
