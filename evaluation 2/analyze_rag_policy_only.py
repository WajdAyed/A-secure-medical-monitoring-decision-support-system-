"""Summarise RAG-enabled policy generation without a no-RAG control."""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
DEFAULT_INPUT = RESULTS / "rag_policy_only_raw.csv"


def rate(rows: list[dict], field: str) -> float:
    return sum(row[field].lower() == "true" for row in rows) / len(rows) if rows else 0.0


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))
    successful = [row for row in raw if not row.get("error")]
    if not successful:
        raise SystemExit(f"No successful RAG policy measurements in {args.input}")
    summaries = []
    for condition in sorted({row["condition"] for row in successful}):
        group = [row for row in successful if row["condition"] == condition]
        total = [float(row["latency_ms"]) for row in group]
        retrieval = [float(row["retrieval_ms"]) for row in group if row["retrieval_ms"]]
        llm = [float(row["llm_ms"]) for row in group if row["llm_ms"]]
        errors = [float(row["total_bound_absolute_error"]) for row in group if row["total_bound_absolute_error"]]
        summaries.append({"condition": condition, "n": len(group), "mean_total_ms": statistics.mean(total), "median_total_ms": statistics.median(total), "p95_total_ms": p95(total), "mean_retrieval_ms": statistics.mean(retrieval) if retrieval else "", "mean_llm_ms": statistics.mean(llm) if llm else "", "valid_policy_rate": rate(group, "valid_policy"), "parameter_match_rate": rate(group, "parameter_match"), "exact_reference_match_rate": rate(group, "exact_reference_match"), "mean_total_bound_absolute_error": statistics.mean(errors) if errors else ""})
    with (RESULTS / "rag_policy_only_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0])); writer.writeheader(); writer.writerows(summaries)
    total = [float(row["latency_ms"]) for row in successful]
    report = ["# RAG-only policy evaluation results", "", f"Successful RAG policy generations: {len(successful)}; failed: {len(raw) - len(successful)}.", "", "This experiment calls the Rule Engine only with `use_rag=True`. It measures retrieval plus LLM policy generation and scores the answer against the documented condition reference. It does not establish that RAG is faster or more accurate than no-RAG because no control group was run.", "", f"Mean total RAG policy time: **{statistics.mean(total):.2f} ms**; median: **{statistics.median(total):.2f} ms**; p95: **{p95(total):.2f} ms**.", f"Overall valid-policy rate: **{rate(successful, 'valid_policy'):.1%}**.", f"Overall parameter-match rate: **{rate(successful, 'parameter_match'):.1%}**.", f"Overall exact-reference rate: **{rate(successful, 'exact_reference_match'):.1%}**.", "", "Reference ranges remain clinician-reviewable project references, not clinical ground truth. Use the paired historical experiment only when a no-RAG control is needed."]
    (RESULTS / "rag_policy_only_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Analysed {len(successful)} RAG policy generations")
    print(f"Mean RAG policy ms: {statistics.mean(total):.2f}")


if __name__ == "__main__":
    main()
