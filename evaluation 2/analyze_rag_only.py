"""Summarise Chroma retrieval latency and guideline-source accuracy."""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "evaluation 2" / "results" / "rag_only_raw.csv"
RESULTS = ROOT / "evaluation 2" / "results"


def rate(rows: list[dict], field: str) -> float:
    return sum(row[field].lower() == "true" for row in rows) / len(rows) if rows else 0.0


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))
    successful = [row for row in raw if not row.get("error")]
    if not successful:
        raise SystemExit(f"No successful RAG-only measurements in {args.input}")
    summaries = []
    for condition in sorted({row["condition"] for row in successful}):
        group = [row for row in successful if row["condition"] == condition]
        latency = [float(row["latency_ms"]) for row in group]
        summaries.append({
            "condition": condition, "n": len(group), "mean_latency_ms": statistics.mean(latency),
            "median_latency_ms": statistics.median(latency), "p95_latency_ms": percentile(latency, .95),
            "source_hit_rate": rate(group, "source_hit"),
            "bounds_present_rate": rate(group, "bounds_present_in_retrieved_text"),
            "nonempty_result_rate": sum(int(row["chunks"]) > 0 for row in group) / len(group),
        })
    write_csv(RESULTS / "rag_only_summary.csv", summaries)
    all_latency = [float(row["latency_ms"]) for row in successful]
    mean_source = statistics.mean(float(row["source_hit_rate"]) for row in summaries)
    mean_bounds = statistics.mean(float(row["bounds_present_rate"]) for row in summaries)
    report = [
        "# RAG-only evaluation results", "",
        f"Source: `{args.input}`; successful retrievals: {len(successful)}; failed retrievals: {len(raw) - len(successful)}.", "",
        "## Scope", "",
        "This experiment evaluates only ChromaDB guideline retrieval for the three conditions with local PDFs. It does not compare against no-RAG, does not call the policy-generation LLM, and does not claim that retrieval alone generates a personalized clinical policy.", "",
        "## Results", "",
        f"Mean Chroma retrieval latency: **{statistics.mean(all_latency):.2f} ms**; median: **{statistics.median(all_latency):.2f} ms**; p95: **{percentile(all_latency, .95):.2f} ms**.",
        f"Mean correct-source rate across conditions: **{mean_source:.1%}**.",
        f"Mean expected-bound presence rate in retrieved text: **{mean_bounds:.1%}**.", "",
        "## Interpretation", "",
        "A correct source hit means that Chroma returned the expected guideline PDF in the top-k result metadata. Bound presence means both documented reference numbers were visible in the returned chunks; it is a retrieval-content check, not clinical validation. The next valid comparison is to measure this retrieval-only path against a PDF full-scan baseline, using the same queries and machine.",
    ]
    (RESULTS / "rag_only_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Analysed {len(successful)} successful RAG-only retrievals")
    print(f"Mean retrieval ms: {statistics.mean(all_latency):.2f}")


if __name__ == "__main__":
    main()
