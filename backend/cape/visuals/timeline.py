from __future__ import annotations

import json


def build_timeline_data(conn, start_tick: int, end_tick: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tick, event_type, source_node, target_node, sku_id, payload
            FROM event_log
            WHERE tick BETWEEN %s AND %s
            ORDER BY tick, event_type
            """,
            (start_tick, end_tick),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT tick, system_backlog, system_capacity_util, instability_index
            FROM tick_metrics
            WHERE tick BETWEEN %s AND %s
            ORDER BY tick
            """,
            (start_tick, end_tick),
        )
        metric_rows = cur.fetchall()

    metric_map = {
        int(t): {
            "system_backlog": int(b or 0),
            "system_capacity_util": float(c or 0.0),
            "instability_index": float(i or 0.0),
        }
        for t, b, c, i in metric_rows
    }

    timeline_items = []
    for tick, event_type, source_node, target_node, sku_id, payload in rows:
        parsed = payload if isinstance(payload, dict) else json.loads(payload or "{}")
        timeline_items.append(
            {
                "tick": int(tick),
                "event_type": event_type,
                "node": source_node,
                "target": target_node,
                "sku": sku_id,
                "quantity": parsed.get("quantity", 0),
                "reason": parsed.get("reorder_reason") or parsed.get("delay_reason") or "",
                "metric_context": metric_map.get(int(tick), {}),
            }
        )

    failure_chain_summary = {
        "first_demand_spike_tick": next((item["tick"] for item in timeline_items if item["event_type"] == "OrderEvent" and item["node"].startswith("RET")), None),
        "first_capacity_hit_tick": next((item["tick"] for item in timeline_items if item["event_type"] == "CapacityEvent" and item["metric_context"].get("system_capacity_util", 0) >= 90), None),
        "first_backlog_spike_tick": next((t for t, m in metric_map.items() if m.get("system_backlog", 0) > 0), None),
    }

    root_cause_evidence = []
    for key in ("first_demand_spike_tick", "first_capacity_hit_tick", "first_backlog_spike_tick"):
        value = failure_chain_summary.get(key)
        if value is not None:
            root_cause_evidence.append(f"{key.replace('_', ' ')} at T{value}")

    return {
        "timeline_items": timeline_items,
        "failure_chain_summary": failure_chain_summary,
        "root_cause_evidence": root_cause_evidence,
    }
