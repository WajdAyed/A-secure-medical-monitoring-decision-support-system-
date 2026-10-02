"""Generate thesis figures from Evaluation 2 CSV summaries."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
FIGURES = ROOT / "figures 2"


def rows(name: str) -> list[dict]:
    with (RESULTS / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Install matplotlib first: python -m pip install matplotlib") from exc
    FIGURES.mkdir(parents=True, exist_ok=True)
    colors = {"without_rag": "#6b7280", "with_rag": "#0f766e"}
    labels = {"without_rag": "Without RAG", "with_rag": "With RAG"}

    summary = rows("rag_summary.csv")
    modes = ["without_rag", "with_rag"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, field, title, ylabel in ((axes[0], "mean_interval_iou", "Policy interval accuracy", "Mean interval IoU"), (axes[1], "inside_reference_rate", "Policy containment", "Rate")):
        values = [float(next(row for row in summary if row["mode"] == mode)[field]) for mode in modes]
        bars = axis.bar([labels[mode] for mode in modes], values, color=[colors[mode] for mode in modes])
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.set_ylim(0, 1)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, value + .02, f"{value:.2f}", ha="center")
    fig.suptitle("RAG effect on policy quality across paired EMRs")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_1_rag_accuracy.png", dpi=250)
    fig.savefig(FIGURES / "figure_1_rag_accuracy.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(7, 4))
    values = [float(next(row for row in summary if row["mode"] == mode)["mean_policy_ms"]) for mode in modes]
    bars = axis.bar([labels[mode] for mode in modes], values, color=[colors[mode] for mode in modes])
    axis.set_ylabel("Mean policy-generation time (ms)")
    axis.set_title("RAG policy-generation latency")
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,.0f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_2_rag_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_2_rag_latency.svg")
    plt.close(fig)

    stage_rows = rows("process_summary.csv")
    stages = ["EMR retrieval", "Policy generation", "ZKP validation", "Decision"]
    fig, axis = plt.subplots(figsize=(9, 4.5))
    width = .36
    positions = list(range(len(stages)))
    for offset, mode in ((-.18, "without_rag"), (.18, "with_rag")):
        values = [float(next(row for row in stage_rows if row["mode"] == mode and row["stage"] == stage)["mean_ms"]) for stage in stages]
        axis.bar([pos + offset for pos in positions], values, width, label=labels[mode], color=colors[mode])
    axis.set_xticks(positions, stages, rotation=15)
    axis.set_ylabel("Mean time (ms)")
    axis.set_title("Mean EMR-to-decision process stages")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_3_emr_process_stages.png", dpi=250)
    fig.savefig(FIGURES / "figure_3_emr_process_stages.svg")
    plt.close(fig)

    zkp = rows("zkp_measurements.csv")
    fig, axis = plt.subplots(figsize=(8, 4))
    for mode in modes:
        values = [float(row["proof_ms"]) for row in zkp if row["mode"] == mode and row["proof_ms"] != ""]
        axis.hist(values, bins=20, alpha=.65, label=labels[mode], color=colors[mode])
    axis.set_xlabel("ZKP-stage latency (ms)")
    axis.set_ylabel("EMR runs")
    axis.set_title("ZKP validation latency distribution")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_4_zkp_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_4_zkp_latency.svg")
    plt.close(fig)
    print(f"Figures written to {FIGURES}")


if __name__ == "__main__":
    main()
