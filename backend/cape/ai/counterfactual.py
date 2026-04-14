"""Counterfactual adjustments using canonical amplification (same formula as metrics)."""

from __future__ import annotations

from cape.db import get_redis_client
from cape.ledger.adapter import _get_pg_conn
from cape.metrics.amplification import compute_canonical_edge_metrics, scenario_sku_demand_sum
from cape.simulation.metrics import MetricsEngine


def simulate_adjustment(sku: str, percent_change: float, start_tick: int, end_tick: int) -> dict:
    """
    Recompute RET→DIST amplification after scaling scenario demand for one SKU (or whole retail
    if sku empty) by ``percent_change`` %. DIST/MFG/SUP order totals stay as in ledger.
    """
    sku = str(sku or "").strip()
    pct = float(percent_change)
    t0, t1 = int(start_tick), int(end_tick)
    if t1 < t0:
        t0, t1 = t1, t0
    r = get_redis_client()
    factor = 1.0 + pct / 100.0

    with _get_pg_conn() as conn, conn.cursor() as cur:
        base = compute_canonical_edge_metrics(cur, r, t0, t1, sku=None)
        ret_id = base["ret_node"]
        dist_id = base["dist_node"]
        key_rd = f"{ret_id}|{dist_id}"
        edge_rd = base["edges"][key_rd]
        old_d = int(edge_rd["demand"])
        old_o = int(edge_rd["orders"])
        old_ratio = float(edge_rd["ratio"])

        sku_base = scenario_sku_demand_sum(r, sku, t0, t1) if sku else 0
        if sku and sku_base > 0:
            new_d = max(1, old_d - sku_base + int(round(sku_base * factor)))
        else:
            new_d = max(1, int(round(old_d * factor)))
        new_ratio = min(10.0, old_o / max(new_d, 1))

    m = MetricsEngine().compute(t1)
    backlog = int(m.get("system_backlog", 0))
    inst = float(m.get("instability_index", 1.0))

    ratio_delta = new_ratio - old_ratio
    if pct < 0:
        backlog_delta = int(round(min(0.0, backlog * ratio_delta * 0.35)))
        inst_delta = round(min(0.0, ratio_delta * max(0.0, inst - 1.0) * 0.55), 4)
    else:
        backlog_delta = int(round(max(0.0, -backlog * min(0.15, -ratio_delta * 0.2))))
        inst_delta = round(max(0.0, ratio_delta * max(0.0, inst - 1.0) * 0.55), 4)

    return {
        "sku": sku or "ALL",
        "percent_change": pct,
        "tick_range": [t0, t1],
        "ret_dist_orders": old_o,
        "retail_demand_baseline": old_d,
        "retail_demand_counterfactual": new_d,
        "amplification_baseline": round(old_ratio, 4),
        "amplification_counterfactual": round(new_ratio, 4),
        "backlog_change": backlog_delta,
        "instability_change": inst_delta,
        "instability_baseline_snapshot": round(inst, 4),
        "model": "canonical_edge_rescale_retail_demand",
    }
