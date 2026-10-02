"""Generate figures for RAG-enabled policy answers only."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
FIGURES = ROOT / "figures 2"


def main() -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Install matplotlib first: python -m pip install matplotlib") from exc
    with (RESULTS / "rag_policy_only_summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    FIGURES.mkdir(parents=True, exist_ok=True)
    conditions = [row["condition"] for row in rows]
    positions = list(range(len(rows)))
    width = .28
    fig, axis = plt.subplots(figsize=(9, 4.5))
    for offset, field, label, color in ((-.28, "valid_policy_rate", "Valid policy", "#2563eb"), (0, "parameter_match_rate", "Parameter match", "#0f766e"), (.28, "exact_reference_match_rate", "Exact reference", "#d97706")):
        values = [float(row[field]) for row in rows]
        axis.bar([x + offset for x in positions], values, width, label=label, color=color)
    axis.set_xticks(positions, conditions)
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Rate")
    axis.set_title("RAG-enabled policy answer quality")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_7_rag_policy_accuracy.png", dpi=250)
    fig.savefig(FIGURES / "figure_7_rag_policy_accuracy.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    values = [float(row["mean_total_ms"]) for row in rows]
    bars = axis.bar(conditions, values, color="#0f766e")
    axis.set_ylabel("Mean policy-generation time (ms)")
    axis.set_title("RAG-enabled policy-generation latency")
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,.0f}", ha="center", va="bottom")
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_8_rag_policy_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_8_rag_policy_latency.svg")
    plt.close(fig)
    print(f"RAG policy figures written to {FIGURES}")


if __name__ == "__main__":
    main()
