"""Summarise matched baseline and proof-enabled CDSS workflow measurements."""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def percentile(samples: list[float], quantile: float) -> float:
    samples = sorted(samples)
    position = (len(samples) - 1) * quantile
    lower, upper = int(position), min(int(position) + 1, len(samples) - 1)
    return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "evaluation" / "results" / "workflow_overhead_raw.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "workflow_overhead_summary.csv")
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    successful = [row for row in rows if not row["baseline_error"] and not row["proof_error"]]
    if not successful:
        raise ValueError("No successful paired workflow measurements")
    baseline = [float(row["baseline_latency_ms"]) for row in successful]
    proof = [float(row["proof_enabled_latency_ms"]) for row in successful]
    overhead = [float(row["proof_overhead_ms"]) for row in successful]
    percentages = [(float(row["proof_enabled_latency_ms"]) - float(row["baseline_latency_ms"])) /
                   float(row["baseline_latency_ms"]) * 100 for row in successful if float(row["baseline_latency_ms"]) > 0]
    summary = {
        "requests": len(rows), "successful_pairs": len(successful),
        "decision_match_rate": round(sum(row["decision_matches_baseline"].lower() == "true" for row in successful) / len(successful), 4),
        "proof_verification_rate": round(sum(row["proof_verified"].lower() == "true" for row in successful) / len(successful), 4),
        "baseline_mean_latency_ms": round(statistics.mean(baseline), 4),
        "proof_enabled_mean_latency_ms": round(statistics.mean(proof), 4),
        "proof_enabled_p95_latency_ms": round(percentile(proof, .95), 4),
        "mean_proof_overhead_ms": round(statistics.mean(overhead), 4),
        "mean_proof_overhead_pct": round(statistics.mean(percentages), 4) if percentages else "",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary))
        writer.writeheader(); writer.writerow(summary)
    print(summary)


if __name__ == "__main__":
    main()
