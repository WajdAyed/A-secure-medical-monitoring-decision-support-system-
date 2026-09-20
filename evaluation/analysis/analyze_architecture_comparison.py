"""Summarise paired predicate-only and proof-enabled validation measurements."""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def percentile(samples: list[float], quantile: float) -> float:
    samples = sorted(samples)
    position = (len(samples) - 1) * quantile
    lower, upper = int(position), min(int(position) + 1, len(samples) - 1)
    return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)


def summarise(rows: list[dict[str, str]]) -> dict[str, object]:
    baseline = [float(row["baseline_predicate_ms"]) for row in rows]
    proof_enabled = [float(row["proof_enabled_ms"]) for row in rows]
    proof_layer = [float(row["proof_layer_ms"]) for row in rows]
    correct = [row["actual_status"] == row["expected_status"] and row["verified"].lower() == "true" for row in rows]
    non_zero = [row for row in rows if float(row["proof_enabled_ms"]) > 0]
    return {
        "concurrent_clients": rows[0]["concurrent_clients"], "samples": len(rows),
        "throughput_rps": rows[0]["throughput_rps"], "proof_correctness_rate": round(sum(correct) / len(correct), 4),
        "baseline_mean_ms": round(statistics.mean(baseline), 6),
        "proof_enabled_mean_ms": round(statistics.mean(proof_enabled), 4),
        "proof_enabled_median_ms": round(statistics.median(proof_enabled), 4),
        "proof_enabled_p95_ms": round(percentile(proof_enabled, .95), 4),
        "proof_layer_mean_ms": round(statistics.mean(proof_layer), 4),
        "proof_layer_share_pct": round(statistics.mean(
            float(row["proof_layer_ms"]) / float(row["proof_enabled_ms"]) * 100 for row in non_zero
        ), 4),
        "mean_public_response_fields": round(statistics.mean(float(row["response_public_field_count"]) for row in rows), 4),
        "sensitive_field_leak_rate": round(sum(float(row["response_sensitive_field_count"]) > 0 for row in rows) / len(rows), 4),
        "classification_disclosure_rate": round(sum(row["classification_disclosed"].lower() == "true" for row in rows) / len(rows), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "evaluation" / "results" / "architecture_comparison_raw.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "architecture_comparison_summary.csv")
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Input contains no measurements")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["concurrent_clients"]].append(row)
    summary = [summarise(group) for _, group in sorted(groups.items(), key=lambda item: int(item[0]))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader(); writer.writerows(summary)
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()
