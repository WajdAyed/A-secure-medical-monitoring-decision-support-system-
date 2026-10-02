"""Run additional offline tests on completed workflow benchmark data."""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
INPUT = RESULTS / "workflow_raw.csv"


def main() -> None:
    with INPUT.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    levels = sorted({int(row["concurrency"]) for row in rows})
    summaries = []
    baseline_wall = None
    baseline_throughput = None
    for level in levels:
        group = [row for row in rows if int(row["concurrency"]) == level]
        included = [row for row in group if row["ok"].lower() == "true" and row.get("excluded", "false").lower() != "true"]
        latencies = [float(row["latency_ms"]) for row in included]
        wall = float(group[0]["batch_wall_ms"])
        throughput = len(included) / (wall / 1000)
        if baseline_wall is None:
            baseline_wall = wall
            baseline_throughput = throughput
        summaries.append({
            "concurrency": level,
            "requested": len(group),
            "included": len(included),
            "excluded": len(group) - len(included),
            "timeout_rate": (len(group) - len(included)) / len(group),
            "batch_wall_s": wall / 1000,
            "throughput_patients_s": throughput,
            "speedup_vs_c1": baseline_wall / wall,
            "throughput_gain_vs_c1": throughput / baseline_throughput,
            "parallel_efficiency": (throughput / baseline_throughput) / level,
            "mean_latency_s": statistics.mean(latencies) / 1000 if latencies else "",
            "latency_stdev_s": statistics.stdev(latencies) / 1000 if len(latencies) > 1 else "",
            "p95_latency_s": sorted(latencies)[max(0, int(.95 * len(latencies) + .9999) - 1)] / 1000 if latencies else "",
        })
    output = RESULTS / "workflow_extra_summary.csv"
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0])); writer.writeheader(); writer.writerows(summaries)
    best = min(summaries, key=lambda row: row["batch_wall_s"])
    report = [
        "# Additional workflow tests", "",
        "These tests are calculated from the completed workflow benchmark; no new service calls are made.", "",
        "## Tests", "",
        "- **Speedup:** sequential batch wall time divided by each concurrent batch wall time.",
        "- **Parallel efficiency:** speedup divided by concurrency; 1.0 would be ideal linear scaling.",
        "- **Timeout rate:** requests excluded because they exceeded 40 seconds.",
        "- **Latency variability:** standard deviation and p95 request latency.", "",
        f"Best batch level: concurrency {best['concurrency']} with {best['batch_wall_s']:.2f} seconds.",
        "Higher concurrency improves total batch completion but can increase per-request latency because the model and services contend for resources.",
    ]
    (RESULTS / "workflow_extra_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    for row in summaries:
        print(row)


if __name__ == "__main__":
    main()
