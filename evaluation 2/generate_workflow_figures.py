"""Generate whole-workflow and concurrency figures."""
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
    with (RESULTS / "workflow_summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    FIGURES.mkdir(parents=True, exist_ok=True)
    levels = [int(row["concurrency"]) for row in rows]

    fig, axis = plt.subplots(figsize=(8, 4))
    values = [float(row["batch_wall_time_ms"]) / 1000 for row in rows]
    axis.plot(levels, values, marker="o", linewidth=2, color="#0f766e")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Complete batch wall time (s)")
    axis.set_title("Whole-workflow batch time by concurrency")
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_12_workflow_batch_time.png", dpi=250)
    fig.savefig(FIGURES / "figure_12_workflow_batch_time.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    values = [float(row["throughput_patients_per_second"]) for row in rows]
    axis.plot(levels, values, marker="s", linewidth=2, color="#2563eb")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Throughput (patients/s)")
    axis.set_title("Whole-workflow throughput")
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_13_workflow_throughput.png", dpi=250)
    fig.savefig(FIGURES / "figure_13_workflow_throughput.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    mean_latency = [float(row["mean_patient_latency_ms"]) / 1000 for row in rows]
    p95_latency = [float(row["p95_patient_latency_ms"]) / 1000 for row in rows]
    axis.plot(levels, mean_latency, marker="o", label="Mean request latency", color="#d97706")
    axis.plot(levels, p95_latency, marker="^", label="P95 request latency", color="#dc2626")
    axis.set_xticks(levels)
    axis.set_xlabel("Concurrent patients")
    axis.set_ylabel("Request latency (s)")
    axis.set_title("Per-patient workflow latency under concurrency")
    axis.legend()
    axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_14_workflow_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_14_workflow_latency.svg")
    plt.close(fig)

    extra_raw = RESULTS / "workflow_scalability_raw.csv"
    if extra_raw.exists():
        with extra_raw.open(newline="", encoding="utf-8") as stream:
            extra_rows = list(csv.DictReader(stream))
        by_concurrency = {int(row["concurrency"]): row for row in rows}
        extra_levels = sorted({int(row["concurrency"]) for row in extra_rows})
        for level in extra_levels:
            group = [row for row in extra_rows if int(row["concurrency"]) == level]
            by_concurrency[level] = {
                "concurrency": str(level),
                "requested_patients": str(len(group)),
                "included_patients": str(sum(
                    row["ok"].lower() == "true" and row["excluded"].lower() != "true"
                    for row in group
                )),
                "batch_wall_time_ms": group[0]["batch_wall_ms"],
            }
        scale_rows = [by_concurrency[level] for level in (1, 2, 4, 8, 16) if level in by_concurrency]
        if len(scale_rows) != 5:
            raise SystemExit("Scalability figure requires measured concurrency levels 1, 2, 4, 8, and 16")

        scale_levels = [int(row["concurrency"]) for row in scale_rows]
        batch_seconds = [float(row["batch_wall_time_ms"]) / 1000 for row in scale_rows]
        requested = [int(row["requested_patients"]) for row in scale_rows]
        included = [int(row["included_patients"]) for row in scale_rows]
        completion_rates = [success / total for success, total in zip(included, requested)]
        fig, axis = plt.subplots(figsize=(8, 4.5))
        axis.plot(scale_levels, batch_seconds, color="#64748b", linewidth=1.5, zorder=1)
        points = axis.scatter(
            scale_levels, batch_seconds, c=completion_rates, cmap="RdYlGn", vmin=0, vmax=1,
            s=85, edgecolor="white", linewidth=1, zorder=2,
        )
        for level, seconds, success, total in zip(scale_levels, batch_seconds, included, requested):
            axis.annotate(
                f"{seconds:.1f} s\n{success}/{total} completed",
                (level, seconds), xytext=(0, 10), textcoords="offset points",
                ha="center", fontsize=8,
            )
        colorbar = fig.colorbar(points, ax=axis, ticks=[0, .5, 1])
        colorbar.set_label("Share completed within 40 s")
        colorbar.ax.set_yticklabels(["0%", "50%", "100%"])
        axis.set_xticks(scale_levels)
        axis.set_xlabel("Patients processed at once")
        axis.set_ylabel("Elapsed batch time (s)")
        axis.set_title("Whole-workflow scalability (20 patients per level)")
        axis.grid(axis="y", alpha=.25)
        fig.tight_layout()
        fig.savefig(FIGURES / "figure_18_workflow_scalability.png", dpi=250)
        fig.savefig(FIGURES / "figure_18_workflow_scalability.svg")
        plt.close(fig)

    print(f"Workflow figures written to {FIGURES}")


if __name__ == "__main__":
    main()
