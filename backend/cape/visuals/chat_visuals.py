from __future__ import annotations


def build_bullwhip_chart(visuals: dict) -> dict:
    data = (visuals or {}).get("bullwhip") or {}
    return {
        "type": "bullwhip",
        "series": data.get("series") or {},
        "stats": data.get("stats") or {},
    }


def build_capacity_chart(visuals: dict) -> dict:
    data = (visuals or {}).get("capacity") or {}
    return {
        "type": "capacity",
        "series": data.get("series") or {},
        "stats": data.get("stats") or {},
    }


def build_backlog_chart(visuals: dict) -> dict:
    data = (visuals or {}).get("backlog") or {}
    return {
        "type": "backlog",
        "series": data.get("series") or [],
        "stats": data.get("stats") or {},
    }


def build_flow_diagram(flow_or_legacy: dict | list | None) -> dict:
    """
    Prefer structured `flow_diagram` from tools (stages with demand/order/amp%).
    Legacy: list of edge dicts from old causality_chain.
    """
    if isinstance(flow_or_legacy, dict) and (flow_or_legacy.get("stages") or flow_or_legacy.get("chain_line")):
        return flow_or_legacy
    if isinstance(flow_or_legacy, list):
        nodes: dict[str, dict] = {}
        edges = []
        for row in flow_or_legacy or []:
            if not isinstance(row, dict):
                continue
            src = row.get("from") or "UNKNOWN"
            dst = row.get("to") or "UNKNOWN"
            nodes[src] = {"id": src, "label": src}
            nodes[dst] = {"id": dst, "label": dst}
            edges.append(
                {
                    "source": src,
                    "target": dst,
                    "weight": int(row.get("quantity", 0) or 0),
                    "event_type": row.get("event_type"),
                    "sku_id": row.get("sku_id"),
                    "tick": int(row.get("tick", 0) or 0),
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges, "stages": [], "chain_line": ""}
    return {"nodes": [], "edges": [], "stages": [], "chain_line": ""}
