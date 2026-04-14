from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure


def get_backlog_data(conn, start_tick: int, end_tick: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tick, system_backlog
            FROM tick_metrics
            WHERE tick BETWEEN %s AND %s
            ORDER BY tick
            """,
            (start_tick, end_tick),
        )
        rows = cur.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["tick", "system_backlog"])
    else:
        df = pd.DataFrame({"tick": list(range(start_tick, end_tick + 1)), "system_backlog": [0] * (end_tick - start_tick + 1)})

    points = [{"tick": int(r.tick), "backlog": float(r.system_backlog)} for _, r in df.iterrows()]
    peak_idx = int(df["system_backlog"].idxmax()) if not df.empty else 0
    peak_row = df.iloc[peak_idx] if not df.empty else pd.Series({"tick": start_tick, "system_backlog": 0})
    return {
        "series": points,
        "stats": {
            "peak_tick": int(peak_row["tick"]),
            "peak_backlog": float(peak_row["system_backlog"]),
        },
    }


def build_backlog_figure(data: dict) -> Figure:
    fig = Figure(figsize=(6.4, 4), dpi=120)
    ax = fig.add_subplot(111)
    x = [p["tick"] for p in data["series"]]
    y = [p["backlog"] for p in data["series"]]
    ax.plot(x, y, color="#ab47bc", linewidth=2, label="System backlog")
    peak_tick = data["stats"]["peak_tick"]
    peak_backlog = data["stats"]["peak_backlog"]
    ax.scatter([peak_tick], [peak_backlog], color="#ff1744", s=50, zorder=5, label="Peak spike")
    ax.annotate(f"{int(peak_backlog)}", (peak_tick, peak_backlog), textcoords="offset points", xytext=(6, -10), color="#ff8a80")

    ax.set_title("Backlog Trend", color="#e0e0e0")
    ax.set_xlabel("Tick", color="#bdbdbd")
    ax.set_ylabel("Backlog Units", color="#bdbdbd")
    ax.grid(True, alpha=0.2)
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#0b0b0b")
    ax.tick_params(colors="#9e9e9e")
    ax.legend(facecolor="#111111", edgecolor="#333333", labelcolor="#e0e0e0")
    fig.tight_layout()
    return fig
