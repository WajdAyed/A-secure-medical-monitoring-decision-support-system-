"""Generate additional workflow scaling figures from offline summaries."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
FIGURES = ROOT / "figures 2"


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with (RESULTS / "workflow_extra_summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    levels = [int(row["concurrency"]) for row in rows]
    FIGURES.mkdir(parents=True, exist_ok=True)

    fig, axis = plt.subplots(figsize=(8, 4))
    speedup = [float(row["speedup_vs_c1"]) for row in rows]
    ideal = levels
    axis.plot(levels, speedup, marker="o", label="Measured speedup", color="#0f766e")
    axis.plot(levels, ideal, linestyle="--", label="Ideal linear speedup", color="#9ca3af")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Speedup versus concurrency 1")
    axis.set_title("Workflow scaling speedup")
    axis.legend()
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_15_workflow_speedup.png", dpi=250)
    fig.savefig(FIGURES / "figure_15_workflow_speedup.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    efficiency = [float(row["parallel_efficiency"]) * 100 for row in rows]
    axis.plot(levels, efficiency, marker="s", color="#2563eb")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Parallel efficiency (%)")
    axis.set_title("Workflow parallel efficiency")
    axis.set_ylim(bottom=0)
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_16_workflow_efficiency.png", dpi=250)
    fig.savefig(FIGURES / "figure_16_workflow_efficiency.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    means = [float(row["mean_latency_s"]) for row in rows]
    deviations = [float(row["latency_stdev_s"]) for row in rows]
    axis.errorbar(levels, means, yerr=deviations, marker="o", capsize=5, color="#d97706")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Request latency (s)")
    axis.set_title("Mean latency with standard deviation")
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_17_workflow_variability.png", dpi=250)
    fig.savefig(FIGURES / "figure_17_workflow_variability.svg")
    plt.close(fig)
    print(f"Additional workflow figures written to {FIGURES}")


if __name__ == "__main__":
    main()
