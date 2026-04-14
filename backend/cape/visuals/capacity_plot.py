from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure


def _dense_capacity(df: pd.DataFrame, node_id: str, start_tick: int, end_tick: int) -> list[dict]:
    ticks = pd.DataFrame({"tick": list(range(start_tick, end_tick + 1))})
    node = df[df["node_id"] == node_id][["tick", "utilization_pct"]]
    merged = ticks.merge(node, on="tick", how="left").fillna(0)
    return [{"tick": int(row.tick), "utilization_pct": float(row.utilization_pct)} for _, row in merged.iterrows()]


def get_capacity_data(conn, start_tick: int, end_tick: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tick, node_id, utilization_pct
            FROM capacity_state
            WHERE tick BETWEEN %s AND %s
              AND node_id IN ('MFG-01', 'DIST-01')
            ORDER BY tick, node_id
            """,
            (start_tick, end_tick),
        )
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["tick", "node_id", "utilization_pct"]) if rows else pd.DataFrame(columns=["tick", "node_id", "utilization_pct"])
    mfg = _dense_capacity(df, "MFG-01", start_tick, end_tick)
    dist = _dense_capacity(df, "DIST-01", start_tick, end_tick)
    return {
        "series": {"mfg_utilization": mfg, "dist_utilization": dist},
        "stats": {
            "mfg_peak": max((p["utilization_pct"] for p in mfg), default=0.0),
            "dist_peak": max((p["utilization_pct"] for p in dist), default=0.0),
        },
    }


def build_capacity_figure(data: dict) -> Figure:
    fig = Figure(figsize=(6.4, 4), dpi=120)
    ax = fig.add_subplot(111)
    x = [p["tick"] for p in data["series"]["mfg_utilization"]]
    mfg_y = [p["utilization_pct"] for p in data["series"]["mfg_utilization"]]
    dist_y = [p["utilization_pct"] for p in data["series"]["dist_utilization"]]

    ax.plot(x, mfg_y, label="MFG utilization", color="#ef5350", linewidth=2)
    ax.plot(x, dist_y, label="DIST utilization", color="#ffa726", linewidth=2)
    ax.axhline(100.0, color="#d50000", linestyle="--", linewidth=1.5, label="100% limit")

    ax.set_title("Capacity Utilization", color="#e0e0e0")
    ax.set_xlabel("Tick", color="#bdbdbd")
    ax.set_ylabel("Utilization %", color="#bdbdbd")
    ax.set_ylim(0, 120)
    ax.grid(True, alpha=0.2)
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#0b0b0b")
    ax.tick_params(colors="#9e9e9e")
    ax.legend(facecolor="#111111", edgecolor="#333333", labelcolor="#e0e0e0")
    fig.tight_layout()
    return fig
