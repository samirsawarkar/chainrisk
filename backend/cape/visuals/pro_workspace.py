"""Interactive Pro workspace payloads: one path for metrics (ledger + scenario + canonical amp)."""

from __future__ import annotations

import re
from typing import Any, Optional

import networkx as nx

from cape.db import get_redis_client
from cape.ledger.adapter import _get_pg_conn
from cape.metrics.amplification import compute_amplification, compute_canonical_edge_metrics, discover_chain_nodes


def parse_tick_range(
    range_str: Optional[str],
    start_tick: Optional[int],
    end_tick: Optional[int],
    latest_tick: int,
) -> tuple[int, int]:
    if range_str:
        m = re.search(r"T?\s*(\d+)\s*[–—\-]\s*T?\s*(\d+)", str(range_str), re.I)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (min(a, b), max(a, b))
    end_v = latest_tick if end_tick is None else max(0, int(end_tick))
    start_v = max(0, end_v - 9) if start_tick is None else max(0, int(start_tick))
    if start_v > end_v:
        start_v, end_v = end_v, start_v
    return start_v, end_v


def _scenario_total_tick(r, tick: int, sku: Optional[str]) -> float:
    h = r.hgetall(f"cape:scenario:demand:{int(tick)}") or {}
    if not sku:
        return float(sum(int(v or 0) for v in h.values()))
    return float(int(h.get(sku, 0) or 0))


def get_bullwhip_pro(conn, start_tick: int, end_tick: int, sku: Optional[str] = None) -> dict[str, Any]:
    """Per-tick series + per-tick RET→DIST amplification (canonical formula)."""
    r = get_redis_client()
    s, e = int(start_tick), int(end_tick)
    if e < s:
        s, e = e, s
    ticks = list(range(s, e + 1))
    with conn.cursor() as cur:
        ret_id, dist_id, mfg_id, sup_id = discover_chain_nodes(cur)
        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'RET-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (s, e),
        )
        ret_o = {int(t): float(q or 0) for t, q in cur.fetchall()}
        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'DIST-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (s, e),
        )
        dist_o = {int(t): float(q or 0) for t, q in cur.fetchall()}
        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'MFG-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (s, e),
        )
        mfg_o = {int(t): float(q or 0) for t, q in cur.fetchall()}
        canon = compute_canonical_edge_metrics(cur, r, s, e, sku=sku or None)

    ret_scenario = [_scenario_total_tick(r, t, sku) for t in ticks]
    ret_orders = [ret_o.get(t, 0.0) for t in ticks]
    dist_orders = [dist_o.get(t, 0.0) for t in ticks]
    mfg_orders = [mfg_o.get(t, 0.0) for t in ticks]
    amps: list[float] = []
    with conn.cursor() as cur:
        for t in ticks:
            a = compute_amplification(cur, r, ret_id, dist_id, sku or None, t, t)
            amps.append(float(a["ratio"]))
    out: dict[str, Any] = {
        "start_tick": s,
        "end_tick": e,
        "sku_filter": sku,
        "chain_nodes": {"ret": ret_id, "dist": dist_id, "mfg": mfg_id, "sup": sup_id},
        "ticks": ticks,
        "series": {
            "ret_scenario": ret_scenario,
            "ret_orders": ret_orders,
            "dist_orders": dist_orders,
            "mfg_orders": mfg_orders,
            "ret_dist_amplification": amps,
        },
        "canonical_window": {
            "ratios": canon["ratios"],
            "edges": {k: {"ratio": v["ratio"], "orders": v["orders"], "demand": v["demand"]} for k, v in canon["edges"].items()},
        },
    }
    return out


def bullwhip_pro_plotly_figure_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Same series as payload, as Plotly Figure JSON (for external tools / parity checks)."""
    import json

    import plotly.graph_objects as go

    ticks = payload.get("ticks") or []
    ser = payload.get("series") or {}
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ticks, y=ser.get("ret_scenario"), name="RET scenario", mode="lines"))
    fig.add_trace(go.Scatter(x=ticks, y=ser.get("ret_orders"), name="RET orders", mode="lines"))
    fig.add_trace(go.Scatter(x=ticks, y=ser.get("dist_orders"), name="DIST orders", mode="lines"))
    fig.add_trace(go.Scatter(x=ticks, y=ser.get("mfg_orders"), name="MFG orders", mode="lines"))
    fig.add_trace(
        go.Scatter(x=ticks, y=ser.get("ret_dist_amplification"), name="RET→DIST amp", mode="lines", yaxis="y2")
    )
    fig.update_layout(
        title="Bullwhip (Pro)",
        xaxis_title="Tick",
        yaxis=dict(title="Quantity"),
        yaxis2=dict(title="Amplification ×", overlaying="y", side="right"),
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=48, r=48, t=48, b=48),
    )
    return json.loads(fig.to_json())


def get_capacity_heatmap(conn, start_tick: int, end_tick: int) -> dict[str, Any]:
    s, e = int(start_tick), int(end_tick)
    if e < s:
        s, e = e, s
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT node_id
            FROM capacity_state
            WHERE tick BETWEEN %s AND %s
            ORDER BY node_id
            """,
            (s, e),
        )
        nodes = [row[0] for row in cur.fetchall()]
        if not nodes:
            cur.execute("SELECT node_id FROM sc_nodes ORDER BY node_id")
            nodes = [row[0] for row in cur.fetchall()]
        cur.execute(
            """
            SELECT node_id, tick, utilization_pct
            FROM capacity_state
            WHERE tick BETWEEN %s AND %s
            ORDER BY tick, node_id
            """,
            (s, e),
        )
        rows = cur.fetchall()
    ticks = list(range(s, e + 1))
    util: dict[tuple[str, int], float] = {}
    for node_id, tick, u in rows:
        util[(str(node_id), int(tick))] = float(u or 0.0)
    matrix: list[list[float]] = []
    for nid in nodes:
        row = [util.get((nid, t), 0.0) for t in ticks]
        matrix.append(row)
    heatmap_cells: list[list[int | float]] = []
    for yi, nid in enumerate(nodes):
        for xi, t in enumerate(ticks):
            heatmap_cells.append([xi, yi, round(matrix[yi][xi], 2)])
    return {
        "start_tick": s,
        "end_tick": e,
        "ticks": ticks,
        "nodes": [{"id": nid, "label": nid} for nid in nodes],
        "heatmap": heatmap_cells,
        "matrix": matrix,
    }


def get_node_tick_detail(conn, r, node_id: str, tick: int) -> dict[str, Any]:
    t = int(tick)
    nid = str(node_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sku_id, SUM(on_hand), SUM(backlog)
            FROM inventory_state
            WHERE node_id = %s AND tick = %s
            GROUP BY sku_id
            ORDER BY sku_id
            """,
            (nid, t),
        )
        sku_rows = cur.fetchall()
        cur.execute(
            """
            SELECT sku_id, COALESCE(SUM(quantity_ordered), 0)
            FROM orders
            WHERE to_node = %s AND tick_placed = %s
            GROUP BY sku_id
            ORDER BY sku_id
            """,
            (nid, t),
        )
        inbound = {str(rw[0]): int(rw[1] or 0) for rw in cur.fetchall()}
        cur.execute(
            "SELECT utilization_pct FROM capacity_state WHERE node_id = %s AND tick = %s LIMIT 1",
            (nid, t),
        )
        crow = cur.fetchone()
        cap_u = float(crow[0] or 0.0) if crow else 0.0
    sku_split = [
        {
            "sku_id": str(sku),
            "on_hand": int(oh or 0),
            "backlog": int(bl or 0),
            "incoming_orders": int(inbound.get(str(sku), 0)),
        }
        for sku, oh, bl in sku_rows
    ]
    scen = []
    if nid.upper().startswith("RET"):
        h = r.hgetall(f"cape:scenario:demand:{t}") or {}
        scen = [{"sku_id": k, "scenario_demand": int(v or 0)} for k, v in sorted(h.items())]
    return {
        "node_id": nid,
        "tick": t,
        "capacity_utilization_pct": round(cap_u, 2),
        "sku_split": sku_split,
        "retail_scenario": scen,
    }


def get_flow_network(conn, tick: int, sku: Optional[str] = None) -> dict[str, Any]:
    r = get_redis_client()
    t = int(tick)
    with conn.cursor() as cur:
        ret_id, dist_id, mfg_id, sup_id = discover_chain_nodes(cur)
        canon = compute_canonical_edge_metrics(cur, r, t, t, sku=sku or None)
        e_rd = canon["edges"][f"{ret_id}|{dist_id}"]
        e_dm = canon["edges"][f"{dist_id}|{mfg_id}"]
        e_ms = canon["edges"][f"{mfg_id}|{sup_id}"]

        def bl(nid: str) -> int:
            cur.execute(
                "SELECT COALESCE(SUM(backlog), 0) FROM inventory_state WHERE node_id = %s AND tick = %s",
                (nid, t),
            )
            row = cur.fetchone()
            return int(row[0] or 0)

        bl_r, bl_d, bl_m, bl_s = bl(ret_id), bl(dist_id), bl(mfg_id), bl(sup_id)

    nodes = [
        {"id": ret_id, "role": "RET", "demand": int(e_rd["demand"]), "order": int(e_rd["orders"]), "backlog": bl_r},
        {"id": dist_id, "role": "DIST", "demand": int(e_rd["orders"]), "order": int(e_dm["orders"]), "backlog": bl_d},
        {"id": mfg_id, "role": "MFG", "demand": int(e_dm["orders"]), "order": int(e_ms["orders"]), "backlog": bl_m},
        {"id": sup_id, "role": "SUP", "demand": int(e_ms["orders"]), "order": int(e_ms["orders"]), "backlog": bl_s},
    ]
    edges = [
        {"from": ret_id, "to": dist_id, "value": int(e_rd["orders"]), "demand": int(e_rd["demand"]), "amp": float(e_rd["ratio"])},
        {"from": dist_id, "to": mfg_id, "value": int(e_dm["orders"]), "demand": int(e_dm["demand"]), "amp": float(e_dm["ratio"])},
        {"from": mfg_id, "to": sup_id, "value": int(e_ms["orders"]), "demand": int(e_ms["demand"]), "amp": float(e_ms["ratio"])},
    ]
    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e["from"], e["to"])
    pos = nx.spring_layout(G, seed=42, k=1.5)
    layout = {k: {"x": float(v[0]), "y": float(v[1])} for k, v in pos.items()}
    return {"tick": t, "sku_filter": sku, "nodes": nodes, "edges": edges, "layout": layout}


def get_causality_payload(node_id: Optional[str], start_tick: int, end_tick: int) -> dict[str, Any]:
    from cape.ai.causality_engine import get_causal_chain

    lo, hi = int(start_tick), int(end_tick)
    if hi < lo:
        lo, hi = hi, lo
    c = get_causal_chain(node_id, lo, hi)
    steps = []
    for i, line in enumerate(c.get("lines") or []):
        steps.append({"id": f"s{i}", "tick": None, "label": line, "kind": "chain"})
    return {
        "node_id": node_id,
        "tick_range": [lo, hi],
        "steps": steps,
        "lines": c.get("lines") or [],
        "amplification_ret_dist": c.get("amplification_ret_dist"),
        "sku": c.get("sku"),
        "nearest_tick_note": c.get("nearest_tick_note"),
        "trigger_tick": c.get("trigger_tick"),
    }


def build_whatif_preview(
    conn,
    start_tick: int,
    end_tick: int,
    sku: str,
    demand_pct: float,
    capacity_relax_pct: float,
    amplification_overlay: float,
) -> dict[str, Any]:
    """Non-mutating preview: scaled scenario line, relaxed util heatmap factor, amplified overlay."""
    r = get_redis_client()
    base = get_bullwhip_pro(conn, start_tick, end_tick, sku=sku or None)
    factor = 1.0 + float(demand_pct) / 100.0
    ticks = base["ticks"]
    adj_scenario: list[float] = []
    for i, t in enumerate(ticks):
        total = float(base["series"]["ret_scenario"][i])
        if sku:
            part = float(int(r.hget(f"cape:scenario:demand:{t}", sku) or 0))
            new_total = total - part + part * factor
        else:
            new_total = total * factor
        adj_scenario.append(round(new_total, 2))
    cap_factor = 1.0 / max(0.01, 1.0 + float(capacity_relax_pct) / 100.0)
    amp_ov = max(0.1, float(amplification_overlay))
    adj_amp = [round(min(10.0, a * amp_ov), 4) for a in base["series"]["ret_dist_amplification"]]
    hm = get_capacity_heatmap(conn, start_tick, end_tick)
    relaxed = [[round(v * cap_factor, 2) for v in row] for row in hm["matrix"]]
    return {
        "ret_scenario_adjusted": adj_scenario,
        "ret_dist_amplification_adjusted": adj_amp,
        "capacity_matrix_relaxed": relaxed,
        "parameters": {
            "demand_percent": demand_pct,
            "capacity_relax_pct": capacity_relax_pct,
            "amplification_overlay": amplification_overlay,
        },
    }
