from __future__ import annotations

from matplotlib.figure import Figure

from cape.simulation.metrics import MetricsEngine


def get_amplification_data(start_tick: int, end_tick: int) -> dict:
    engine = MetricsEngine()
    ratios = []
    for tick in range(start_tick, end_tick + 1):
        metrics = engine.compute(tick)
        amp = metrics.get("amplification_ratios") or {}
        ratios.append(
            {
                "tick": tick,
                "dist_over_ret": float(amp.get("dist_over_ret", 1.0)),
                "mfg_over_dist": float(amp.get("mfg_over_dist", 1.0)),
                "sup_over_mfg": float(amp.get("sup_over_mfg", 1.0)),
            }
        )

    def _avg(key: str) -> float:
        return round(sum(r[key] for r in ratios) / max(1, len(ratios)), 4)

    bars = [
        {"label": "DIST/RET", "value": _avg("dist_over_ret")},
        {"label": "MFG/DIST", "value": _avg("mfg_over_dist")},
        {"label": "SUP/MFG", "value": _avg("sup_over_mfg")},
    ]
    return {"bars": bars, "series": ratios}


def build_amplification_figure(data: dict) -> Figure:
    fig = Figure(figsize=(6.4, 4), dpi=120)
    ax = fig.add_subplot(111)
    labels = [b["label"] for b in data["bars"]]
    values = [b["value"] for b in data["bars"]]
    colors = ["#4fc3f7" if v < 2 else "#ffa726" if v < 4 else "#ef5350" for v in values]
    bars = ax.bar(labels, values, color=colors, edgecolor="#222")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.05, f"{value:.2f}", ha="center", va="bottom", color="#e0e0e0")

    ax.set_title("Amplification Ratios", color="#e0e0e0")
    ax.set_ylabel("Ratio", color="#bdbdbd")
    ax.set_ylim(0, max(6, max(values) + 1))
    ax.grid(True, axis="y", alpha=0.2)
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#0b0b0b")
    ax.tick_params(colors="#9e9e9e")
    fig.tight_layout()
    return fig
