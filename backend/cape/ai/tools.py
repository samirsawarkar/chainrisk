from __future__ import annotations

import json
import re
from typing import Any

from cape.ai.causality_engine import get_root_cause
from cape.ai.counterfactual import simulate_adjustment as cf_simulate_adjustment
from cape.db import get_redis_client
from cape.ledger.adapter import _get_pg_conn
from cape.metrics.amplification import compute_canonical_edge_metrics, discover_chain_nodes, enrich_bullwhip_stats
from cape.simulation.metrics import MetricsEngine
from cape.visuals.backlog_plot import get_backlog_data
from cape.visuals.bullwhip_plot import get_bullwhip_data
from cape.visuals.capacity_plot import get_capacity_data


def _infer_tick_range(question: str, fallback_end: int) -> tuple[int, int]:
    q = (question or "").upper()
    m = re.search(r"(?:T|TICK)\s*(\d+)\s*[–—\-]\s*T?\s*(\d+)", q)
    if not m:
        m = re.search(r"(?:T|TICK)\s*=?\s*(\d+)\s*(?:-|TO)\s*(\d+)", q)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    s = re.search(r"(?:T|TICK)\s*=?\s*(\d+)", q)
    if s:
        t = int(s.group(1))
        return (max(0, t - 2), t)
    end_tick = max(0, int(fallback_end))
    return (max(0, end_tick - 9), end_tick)


def filter_by_tick(data: Any, start_tick: int, end_tick: int) -> Any:
    """Filter time-series structures to [start_tick, end_tick] inclusive."""
    lo, hi = int(start_tick), int(end_tick)
    if hi < lo:
        lo, hi = hi, lo
    if isinstance(data, list):
        out = []
        for x in data:
            if not isinstance(x, dict):
                continue
            tk = x.get("tick")
            if tk is None:
                continue
            if lo <= int(tk) <= hi:
                out.append(x)
        return out
    if isinstance(data, dict) and "series" in data:
        ser = data.get("series") or {}
        if isinstance(ser, dict):
            new_series = {}
            for k, arr in ser.items():
                if isinstance(arr, list):
                    new_series[k] = [p for p in arr if isinstance(p, dict) and lo <= int(p.get("tick", -1)) <= hi]
                else:
                    new_series[k] = arr
            return {**data, "series": new_series}
        if isinstance(ser, list):
            return {**data, "series": [p for p in ser if isinstance(p, dict) and lo <= int(p.get("tick", -1)) <= hi]}
    return data


def _infer_node(question: str) -> str | None:
    m = re.search(r"\b(SUP|MFG|DIST|RET)-\d{2}\b", (question or "").upper())
    return m.group(0) if m else None


def _infer_sku(question: str) -> str | None:
    m = re.search(r"\bSKU[_\s-]?([A-Z0-9]+)\b", (question or "").upper())
    if m:
        return m.group(1)
    m2 = re.search(r"\bsku\s+([A-Z0-9]+)\b", (question or "").lower())
    if m2:
        return m2.group(1).upper()
    m3 = re.search(r"\b([AB])\b", (question or "").upper())
    if m3 and len(question or "") < 80:
        return m3.group(1)
    return None


def _scenario_demand_sku_total(r, sku: str, start_tick: int, end_tick: int) -> int:
    total = 0
    for t in range(int(start_tick), int(end_tick) + 1):
        total += int(r.hget(f"cape:scenario:demand:{t}", sku) or 0)
    return total


def get_metrics(current_tick: int) -> dict:
    tick = max(0, int(current_tick))
    metrics = MetricsEngine().compute(tick)
    ex = metrics.get("explainability") or {}
    em = metrics.get("edge_metrics") or {}
    return {
        "tick": tick,
        "metric_window": None,
        "window_note": None,
        "backlog": int(metrics.get("system_backlog", 0)),
        "instability": float(metrics.get("instability_index", 0.0)),
        "amplification": metrics.get("amplification_ratios") or {},
        "edge_metrics": em,
        "capacity_by_node": metrics.get("capacity_utilization") or {},
        "metric_anomalies": metrics.get("metric_anomalies") or [],
        "spike_sku": ex.get("spike_sku"),
        "spike_from": int(ex.get("spike_from") or 0),
        "spike_to": int(ex.get("spike_to") or 0),
    }


def get_metrics_aligned(end_tick: int, tick_range: tuple[int, int], sku: str | None = None) -> dict:
    """
    Metrics for chat/charts: backlog at end_tick, amplification + instability from canonical
    window [tick_lo, tick_hi] (same formula as tick_metrics.edge_metrics persistence).
    """
    lo, hi = int(tick_range[0]), int(tick_range[1])
    if hi < lo:
        lo, hi = hi, lo
    end_tick = max(0, int(end_tick))
    base = MetricsEngine().compute(end_tick)
    ex = base.get("explainability") or {}
    spike_from, spike_to = int(ex.get("spike_from") or 0), int(ex.get("spike_to") or 0)
    window_note = None
    if spike_to and (spike_to < lo or spike_from > hi):
        window_note = (
            f"Global explainability spike T{spike_from}→T{spike_to} is outside the question window T{lo}–T{hi}; "
            "amplification and chain use the question window only."
        )
    r = get_redis_client()
    with _get_pg_conn() as conn, conn.cursor() as cur:
        canon = compute_canonical_edge_metrics(cur, r, lo, hi, sku=sku)
        cur.execute(
            """
            SELECT node_id, MAX(utilization_pct) AS mx
            FROM capacity_state
            WHERE tick BETWEEN %s AND %s
            GROUP BY node_id
            """,
            (lo, hi),
        )
        cap_peak = {str(row[0]): float(row[1] or 0.0) for row in cur.fetchall()}
    edge_metrics = {k: {"ratio": v["ratio"], "orders": v["orders"], "demand": v["demand"]} for k, v in canon["edges"].items()}
    return {
        "tick": end_tick,
        "metric_window": [lo, hi],
        "window_note": window_note,
        "backlog": int(base.get("system_backlog", 0)),
        "instability": float(canon["global_index"]),
        "amplification": canon["ratios"],
        "edge_metrics": edge_metrics,
        "capacity_by_node": cap_peak or (base.get("capacity_utilization") or {}),
        "metric_anomalies": base.get("metric_anomalies") or [],
        "spike_sku": ex.get("spike_sku"),
        "spike_from": spike_from,
        "spike_to": spike_to,
    }


def _node_backlog_sum(cur, node_id: str, tick: int) -> int:
    cur.execute(
        "SELECT COALESCE(SUM(backlog), 0) FROM inventory_state WHERE tick = %s AND node_id = %s",
        (int(tick), node_id),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def get_events(node_id: str | None, tick_range: tuple[int, int]) -> list[dict]:
    start_tick, end_tick = tick_range
    with _get_pg_conn() as conn, conn.cursor() as cur:
        if node_id:
            cur.execute(
                """
                SELECT tick, event_type, source_node, target_node, sku_id, payload
                FROM event_log
                WHERE tick BETWEEN %s AND %s
                  AND (source_node = %s OR target_node = %s)
                ORDER BY tick, event_type
                LIMIT 200
                """,
                (start_tick, end_tick, node_id, node_id),
            )
        else:
            cur.execute(
                """
                SELECT tick, event_type, source_node, target_node, sku_id, payload
                FROM event_log
                WHERE tick BETWEEN %s AND %s
                ORDER BY tick, event_type
                LIMIT 200
                """,
                (start_tick, end_tick),
            )
        rows = cur.fetchall()

    out = []
    for tick, event_type, source_node, target_node, sku_id, payload in rows:
        parsed = payload if isinstance(payload, dict) else json.loads(payload or "{}")
        out.append(
            {
                "tick": int(tick),
                "event_type": event_type,
                "source_node": source_node,
                "target_node": target_node,
                "sku_id": sku_id,
                "quantity": int(parsed.get("quantity", 0) or 0),
                "reason": parsed.get("reorder_reason") or parsed.get("delay_reason") or "",
            }
        )
    return out


def get_sku_impact(tick_range: tuple[int, int]) -> list[dict]:
    """One row per configured SKU: scenario demand + RET orders + fills (ledger-only)."""
    start_tick, end_tick = tick_range
    r = get_redis_client()
    with _get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT sku_id FROM skus ORDER BY sku_id")
        sku_ids = [row[0] for row in cur.fetchall()]
        cur.execute(
            """
            SELECT o.sku_id,
                COALESCE(SUM(CASE WHEN o.from_node LIKE 'RET-%%' THEN o.quantity_ordered ELSE 0 END), 0),
                COALESCE(SUM(o.quantity_ordered), 0),
                COALESCE(SUM(o.quantity_filled), 0) AS filled_qty
            FROM orders o
            WHERE o.tick_placed BETWEEN %s AND %s
            GROUP BY o.sku_id
            """,
            (start_tick, end_tick),
        )
        by_sku = {row[0]: (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)) for row in cur.fetchall()}

    out = []
    for sku_id in sku_ids:
        ret_ord, _tot, filled = by_sku.get(sku_id, (0, 0, 0))
        scen_demand = _scenario_demand_sku_total(r, sku_id, start_tick, end_tick)
        out.append(
            {
                "sku_id": sku_id,
                "demand": scen_demand,
                "retailer_orders": ret_ord,
                "allocation_filled": filled,
            }
        )
    out.sort(key=lambda x: x["demand"] + x["retailer_orders"], reverse=True)
    return out


def compute_bullwhip_chain(tick_range: tuple[int, int]) -> dict:
    start_tick, end_tick = int(tick_range[0]), int(tick_range[1])
    if end_tick < start_tick:
        start_tick, end_tick = end_tick, start_tick
    with _get_pg_conn() as conn:
        r = get_redis_client()
        with conn.cursor() as cur:
            canon = compute_canonical_edge_metrics(cur, r, start_tick, end_tick, sku=None)
        data = get_bullwhip_data(conn, start_tick, end_tick)
        data = enrich_bullwhip_stats(conn, r, start_tick, end_tick, data)
    ratios = canon["ratios"]
    return {
        "dist_over_ret_peak": float(ratios["dist_over_ret"]),
        "mfg_over_dist_peak": float(ratios["mfg_over_dist"]),
        "sup_over_mfg_peak": float(ratios["sup_over_mfg"]),
        "canonical_edges": {k: {"ratio": v["ratio"], "orders": v["orders"], "demand": v["demand"]} for k, v in canon["edges"].items()},
        "series": data["series"],
        "stats": data.get("stats") or {},
    }


def get_causality_chain(node_id: str | None, tick_range: tuple[int, int]) -> list[str]:
    """Narrative chain from ledger (not raw event_log dump)."""
    lo, hi = int(tick_range[0]), int(tick_range[1])
    if hi < lo:
        lo, hi = hi, lo
    rc = get_root_cause(node_id, hi, lo)
    return list(rc.get("chain") or [])


def _orders_from_prefix_window(cur, from_prefix: str, t0: int, t1: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity_ordered), 0)
        FROM orders
        WHERE from_node LIKE %s AND tick_placed BETWEEN %s AND %s
        """,
        (f"{from_prefix}%", t0, t1),
    )
    row = cur.fetchone()
    return int(row[0] or 0)


def _role_tag(node_id: str) -> str:
    u = (node_id or "").upper()
    if u.startswith("RET"):
        return "RET"
    if u.startswith("DIST"):
        return "DIST"
    if u.startswith("MFG"):
        return "MFG"
    if u.startswith("SUP"):
        return "SUP"
    return u[:4]


def _edge_amp_pct(demand: int, orders: int) -> float:
    d = max(float(demand), 1.0)
    return round(max(0.0, (float(orders) / d - 1.0) * 100.0), 1)


def build_flow_diagram_struct(tick_range: tuple[int, int]) -> dict:
    """Per-node demand/order/backlog + edges from canonical edge_metrics (same as metrics table)."""
    start_tick, end_tick = int(tick_range[0]), int(tick_range[1])
    if end_tick < start_tick:
        start_tick, end_tick = end_tick, start_tick
    with _get_pg_conn() as conn, conn.cursor() as cur:
        r = get_redis_client()
        ret_id, dist_id, mfg_id, sup_id = discover_chain_nodes(cur)
        canon = compute_canonical_edge_metrics(cur, r, start_tick, end_tick, sku=None)
        e_rd = canon["edges"][f"{ret_id}|{dist_id}"]
        e_dm = canon["edges"][f"{dist_id}|{mfg_id}"]
        e_ms = canon["edges"][f"{mfg_id}|{sup_id}"]
        sup_out = _orders_from_prefix_window(cur, sup_id, start_tick, end_tick)
        bl_r = _node_backlog_sum(cur, ret_id, end_tick)
        bl_d = _node_backlog_sum(cur, dist_id, end_tick)
        bl_m = _node_backlog_sum(cur, mfg_id, end_tick)
        bl_s = _node_backlog_sum(cur, sup_id, end_tick)

    stages = [
        {
            "id": ret_id,
            "role": "RET",
            "demand": int(e_rd["demand"]),
            "order": int(e_rd["orders"]),
            "backlog": bl_r,
            "amplification_pct": 0.0,
        },
        {
            "id": dist_id,
            "role": "DIST",
            "demand": int(e_rd["orders"]),
            "order": int(e_dm["orders"]),
            "backlog": bl_d,
            "amplification_pct": _edge_amp_pct(int(e_rd["demand"]), int(e_rd["orders"])),
        },
        {
            "id": mfg_id,
            "role": "MFG",
            "demand": int(e_dm["orders"]),
            "order": int(e_ms["orders"]),
            "backlog": bl_m,
            "amplification_pct": _edge_amp_pct(int(e_dm["demand"]), int(e_dm["orders"])),
        },
        {
            "id": sup_id,
            "role": "SUP",
            "demand": int(e_ms["orders"]),
            "order": sup_out,
            "backlog": bl_s,
            "amplification_pct": _edge_amp_pct(int(e_ms["orders"]), max(int(e_ms["orders"]), sup_out)),
        },
    ]

    edges = [
        {
            "source": ret_id,
            "target": dist_id,
            "demand": int(e_rd["demand"]),
            "orders": int(e_rd["orders"]),
            "ratio": float(e_rd["ratio"]),
            "label": f"{_role_tag(ret_id)} → {_role_tag(dist_id)}: {int(e_rd['demand'])} → {int(e_rd['orders'])} ({float(e_rd['ratio']):.2f}×)",
        },
        {
            "source": dist_id,
            "target": mfg_id,
            "demand": int(e_dm["demand"]),
            "orders": int(e_dm["orders"]),
            "ratio": float(e_dm["ratio"]),
            "label": f"{_role_tag(dist_id)} → {_role_tag(mfg_id)}: {int(e_dm['demand'])} → {int(e_dm['orders'])} ({float(e_dm['ratio']):.2f}×)",
        },
        {
            "source": mfg_id,
            "target": sup_id,
            "demand": int(e_ms["demand"]),
            "orders": int(e_ms["orders"]),
            "ratio": float(e_ms["ratio"]),
            "label": f"{_role_tag(mfg_id)} → {_role_tag(sup_id)}: {int(e_ms['demand'])} → {int(e_ms['orders'])} ({float(e_ms['ratio']):.2f}×)",
        },
    ]
    return {
        "chain_line": "RET → DIST → MFG → SUP",
        "end_tick": end_tick,
        "metric_window": [start_tick, end_tick],
        "stages": stages,
        "edges": edges,
    }


def simulate_adjustment(sku: str, percent_change: float, tick_range: tuple[int, int]) -> dict:
    """Canonical-demand rescale counterfactual (see cape.ai.counterfactual)."""
    lo, hi = int(tick_range[0]), int(tick_range[1])
    if hi < lo:
        lo, hi = hi, lo
    return cf_simulate_adjustment(sku, percent_change, lo, hi)


def get_visual_payloads(tick_range: tuple[int, int]) -> dict:
    start_tick, end_tick = int(tick_range[0]), int(tick_range[1])
    if end_tick < start_tick:
        start_tick, end_tick = end_tick, start_tick
    r = get_redis_client()
    with _get_pg_conn() as conn:
        bullwhip = get_bullwhip_data(conn, start_tick, end_tick)
        bullwhip = enrich_bullwhip_stats(conn, r, start_tick, end_tick, bullwhip)
        capacity = get_capacity_data(conn, start_tick, end_tick)
        backlog = get_backlog_data(conn, start_tick, end_tick)
    return {"bullwhip": bullwhip, "capacity": capacity, "backlog": backlog}


def collect_tool_bundle(question: str, current_tick: int) -> dict:
    tick_range = _infer_tick_range(question, fallback_end=current_tick)
    node_id = _infer_node(question)
    sku_hint = _infer_sku(question)
    lo, hi = int(tick_range[0]), int(tick_range[1])
    if hi < lo:
        lo, hi = hi, lo
    tick_range = (lo, hi)
    metrics = get_metrics_aligned(hi, tick_range, sku=sku_hint)
    root = get_root_cause(node_id, hi, lo)
    chain = list(root.get("chain") or [])
    flow = build_flow_diagram_struct(tick_range)
    counterfactual = None
    if sku_hint and any(k in (question or "").lower() for k in ("what if", "counterfactual", "reduce", "cut", "lower demand")):
        m = re.search(r"(-?\d+)\s*%", question or "")
        pct = float(m.group(1)) if m else -10.0
        counterfactual = simulate_adjustment(sku_hint, pct, tick_range)

    return {
        "question_scope": {
            "node_id": node_id,
            "tick_range": list(tick_range),
            "sku_hint": sku_hint,
            "tick_filter_note": root.get("nearest_tick_note"),
            "metric_window_note": metrics.get("window_note"),
        },
        "metrics": metrics,
        "root_cause": root,
        "events": filter_by_tick(get_events(node_id, tick_range), lo, hi),
        "sku_impact": get_sku_impact(tick_range=tick_range),
        "bullwhip_chain": compute_bullwhip_chain(tick_range=tick_range),
        "causality_chain": chain,
        "flow_diagram": flow,
        "counterfactual": counterfactual,
        "visuals": get_visual_payloads(tick_range=tick_range),
    }
