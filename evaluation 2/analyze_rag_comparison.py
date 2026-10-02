"""Summarise paired Chroma-RAG versus full-PDF guideline processing."""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
DEFAULT_INPUT = RESULTS / "rag_vs_full_pdf_raw.csv"


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)]


def rate(rows: list[dict], field: str) -> float:
    return sum(row[field].lower() == "true" for row in rows) / len(rows) if rows else 0.0


def write_csv(path: Path, rows: list[dict]) -> None:
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
        raise SystemExit(f"No successful comparison measurements in {args.input}")
    summaries = []
    for mode in ("rag_chroma", "no_rag_full_pdf"):
        group = [row for row in successful if row["mode"] == mode]
        total = [float(row["latency_ms"]) for row in group]
        stage = [float(row["retrieval_or_scan_ms"]) for row in group if row["retrieval_or_scan_ms"]]
        llm = [float(row["llm_ms"]) for row in group if row["llm_ms"]]
        errors = [float(row["total_bound_absolute_error"]) for row in group if row["total_bound_absolute_error"]]
        summaries.append({"mode": mode, "n": len(group), "mean_total_ms": statistics.mean(total), "median_total_ms": statistics.median(total), "p95_total_ms": p95(total), "mean_retrieval_or_scan_ms": statistics.mean(stage) if stage else "", "mean_llm_ms": statistics.mean(llm) if llm else "", "valid_policy_rate": rate(group, "valid_policy"), "parameter_match_rate": rate(group, "parameter_match"), "exact_reference_match_rate": rate(group, "exact_reference_match"), "mean_total_bound_absolute_error": statistics.mean(errors) if errors else ""})
    write_csv(RESULTS / "rag_comparison_summary.csv", summaries)
    rag = next(row for row in summaries if row["mode"] == "rag_chroma")
    full_pdf = next(row for row in summaries if row["mode"] == "no_rag_full_pdf")
    latency_delta = rag["mean_total_ms"] - full_pdf["mean_total_ms"]
    report = ["# RAG versus full-PDF comparison", "", f"Successful measurements: {len(successful)}; failed measurements: {len(raw) - len(successful)}.", "", "## Definitions", "", "`rag_chroma` queries the Chroma vector database for the top-k chunks and then uses the Rule Engine's RAG-enabled LLM prompt. `no_rag_full_pdf` bypasses Chroma, loads the complete condition-specific guideline PDF, and sends that full text to the same Ollama model. Both modes use the same three conditions, age, model settings, references, and repeat count.", "", "## Results", "", f"Mean total time, Chroma RAG: **{rag['mean_total_ms']:.2f} ms**.", f"Mean total time, full-PDF no-RAG: **{full_pdf['mean_total_ms']:.2f} ms**.", f"RAG minus full-PDF: **{latency_delta:.2f} ms** ({latency_delta / full_pdf['mean_total_ms']:.1%}).", f"Parameter match: RAG **{rag['parameter_match_rate']:.1%}**, full-PDF **{full_pdf['parameter_match_rate']:.1%}**.", f"Exact reference match: RAG **{rag['exact_reference_match_rate']:.1%}**, full-PDF **{full_pdf['exact_reference_match_rate']:.1%}**.", "", "## Interpretation", "", "This is the requested architecture comparison: semantic vector retrieval versus reading the complete condition guideline. A lower RAG time supports the efficiency claim, while higher parameter/exact-match rates support the accuracy claim. These references are still project evaluation references and require clinical review before being presented as clinical ground truth."]
    (RESULTS / "rag_comparison_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Compared {len(successful)} successful measurements")
    print(f"Mean ms: RAG={rag['mean_total_ms']:.2f}, full-PDF={full_pdf['mean_total_ms']:.2f}")


if __name__ == "__main__":
    main()
