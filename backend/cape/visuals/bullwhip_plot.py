from __future__ import annotations

import pandas as pd
from matplotlib.figure import Figure


def _dense_series(df: pd.DataFrame, start_tick: int, end_tick: int, value_col: str) -> list[dict]:
    ticks = pd.DataFrame({"tick": list(range(start_tick, end_tick + 1))})
    merged = ticks.merge(df[["tick", value_col]], on="tick", how="left").fillna(0)
    return [{"tick": int(row.tick), value_col: float(row[value_col])} for _, row in merged.iterrows()]


def get_bullwhip_data(conn, start_tick: int, end_tick: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'RET-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (start_tick, end_tick),
        )
        ret_df = pd.DataFrame(cur.fetchall(), columns=["tick", "qty"]) if cur.rowcount else pd.DataFrame(columns=["tick", "qty"])

        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'DIST-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (start_tick, end_tick),
        )
        dist_df = pd.DataFrame(cur.fetchall(), columns=["tick", "qty"]) if cur.rowcount else pd.DataFrame(columns=["tick", "qty"])

        cur.execute(
            """
            SELECT tick_placed AS tick, SUM(quantity_ordered)::numeric AS qty
            FROM orders
            WHERE from_node LIKE 'MFG-%%' AND tick_placed BETWEEN %s AND %s
            GROUP BY tick_placed
            ORDER BY tick_placed
            """,
            (start_tick, end_tick),
        )
        mfg_df = pd.DataFrame(cur.fetchall(), columns=["tick", "qty"]) if cur.rowcount else pd.DataFrame(columns=["tick", "qty"])

    ret_series = _dense_series(ret_df, start_tick, end_tick, "qty")
    dist_series = _dense_series(dist_df, start_tick, end_tick, "qty")
    mfg_series = _dense_series(mfg_df, start_tick, end_tick, "qty")
    return {
        "series": {
            "ret_demand": ret_series,
            "dist_orders": dist_series,
            "mfg_orders": mfg_series,
        },
        "stats": {
            "ret_max": max((p["qty"] for p in ret_series), default=0.0),
            "dist_max": max((p["qty"] for p in dist_series), default=0.0),
            "mfg_max": max((p["qty"] for p in mfg_series), default=0.0),
        },
    }


def build_bullwhip_figure(data: dict) -> Figure:
    fig = Figure(figsize=(12, 4), dpi=120)
    ax = fig.add_subplot(111)
    x = [p["tick"] for p in data["series"]["ret_demand"]]
    ret_y = [p["qty"] for p in data["series"]["ret_demand"]]
    dist_y = [p["qty"] for p in data["series"]["dist_orders"]]
    mfg_y = [p["qty"] for p in data["series"]["mfg_orders"]]

    ax.plot(x, ret_y, label="RET demand", color="#4dd0e1", linewidth=2)
    ax.plot(x, dist_y, label="DIST orders", color="#ffa726", linewidth=2)
    ax.plot(x, mfg_y, label="MFG orders", color="#ef5350", linewidth=2)
    ax.fill_between(x, ret_y, mfg_y, color="#ef5350", alpha=0.08)

    ax.set_title("Bullwhip Amplification", color="#e0e0e0")
    ax.set_xlabel("Tick", color="#bdbdbd")
    ax.set_ylabel("Quantity", color="#bdbdbd")
    ax.grid(True, alpha=0.2)
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#0b0b0b")
    ax.tick_params(colors="#9e9e9e")
    ax.legend(facecolor="#111111", edgecolor="#333333", labelcolor="#e0e0e0")
    fig.tight_layout()
    return fig
