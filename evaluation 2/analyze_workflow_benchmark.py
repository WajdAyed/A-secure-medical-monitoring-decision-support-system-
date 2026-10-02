"""Summarise whole-workflow latency and concurrency results."""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
DEFAULT_INPUT = RESULTS / "workflow_raw.csv"


def percentile(values: list[float], q: float) -> float:
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))
    successful = [row for row in raw if row["ok"].lower() == "true" and row.get("excluded", "false").lower() != "true" and float(row["latency_ms"]) <= 40000]
    if not successful:
        raise SystemExit(f"No successful workflow rows in {args.input}")
    summaries = []
    for concurrency in sorted({int(row["concurrency"]) for row in raw}):
        group = [row for row in raw if int(row["concurrency"]) == concurrency]
        good = [row for row in successful if int(row["concurrency"]) == concurrency]
        latencies = [float(row["latency_ms"]) for row in good]
        workflow = [float(row["workflow_total_ms"]) for row in good if row["workflow_total_ms"]]
        wall = float(group[0]["batch_wall_ms"])
        summaries.append({"concurrency": concurrency, "requested_patients": len(group), "included_patients": len(good), "excluded_patients": len(group) - len(good), "included_rate": len(good) / len(group), "mean_patient_latency_ms": statistics.mean(latencies) if latencies else "", "median_patient_latency_ms": statistics.median(latencies) if latencies else "", "p95_patient_latency_ms": percentile(latencies, .95) if latencies else "", "mean_workflow_internal_ms": statistics.mean(workflow) if workflow else "", "batch_wall_time_ms": wall, "throughput_patients_per_second": len(good) / (wall / 1000), "mean_proof_ms": statistics.mean(float(row["proof_ms"]) for row in good if row["proof_ms"]) if any(row["proof_ms"] for row in good) else "", "proof_verified_rate": sum(row["proof_verified"].lower() == "true" for row in good) / len(good) if good else ""})
    write_csv(RESULTS / "workflow_summary.csv", summaries)
    baseline = summaries[0]
    best = min(summaries, key=lambda row: row["batch_wall_time_ms"])
    measured_per_level = max(row["requested_patients"] for row in summaries)
    report = ["# Whole-workflow evaluation", "", f"Input: `{args.input}`. Patient 1 was discarded as warm-up before each concurrency level. Patients 2 onward were measured; this run used {measured_per_level} measured patients per level. Requests over 40 seconds were excluded from statistics but retained in the raw CSV.", "", "## Results", "", f"Sequential mean included-patient latency: **{baseline['mean_patient_latency_ms']:.2f} ms**.", f"Sequential batch wall time: **{baseline['batch_wall_time_ms']:.2f} ms**.", f"Best measured concurrency: **{best['concurrency']}**, wall time **{best['batch_wall_time_ms']:.2f} ms**, throughput **{best['throughput_patients_per_second']:.2f} patients/s**.", "", "## Interpretation", "", "Patient latency is the elapsed time seen by each request; batch wall time is the time to process the measured patient set at that concurrency. Higher concurrency can reduce batch wall time while increasing individual latency or service contention. All stages represent the complete EMR retrieval, policy generation, ZKP validation, and final decision workflow when timing metadata is enabled.", "", "This benchmark measures system performance, not clinical correctness. A successful request means the workflow returned successfully; it does not validate the medical policy itself."]
    (RESULTS / "workflow_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Analysed {len(raw)} rows")
    for row in summaries:
        print(row)


if __name__ == "__main__":
    main()
