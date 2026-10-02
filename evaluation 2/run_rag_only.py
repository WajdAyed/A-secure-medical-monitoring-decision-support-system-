"""Benchmark Chroma guideline retrieval only; no no-RAG or LLM comparison."""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evaluation 2" / "results" / "rag_only_raw.csv"
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool

CASES = {
    "hypertension": {"source": "Hypertension guideline.pdf", "parameter": "systolic_bp", "min": 110, "max": 135},
    "diabetes": {"source": "Diabetes guideline.pdf", "parameter": "blood_glucose", "min": 70, "max": 140},
    "heart_failure": {"source": "Heart Failure guideline.pdf", "parameter": "weight_kg", "min": 60, "max": 90},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("KNOWLEDGE_MCP_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.repeats < 1 or args.k < 1 or args.warmup < 0:
        parser.error("repeats and k must be positive; warmup cannot be negative")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for condition, reference in CASES.items():
        for _ in range(args.warmup):
            call_tool(args.url, "search_guidelines", {"condition": condition, "k": args.k}, timeout=args.timeout)
        for repeat in range(1, args.repeats + 1):
            started = time.perf_counter()
            try:
                response = call_tool(args.url, "search_guidelines", {"condition": condition, "k": args.k}, timeout=args.timeout)
                guidelines = response.get("guidelines", [])
                sources = response.get("sources", [])
                combined = "\n".join(guidelines)
                source_hit = reference["source"] in sources
                bounds_present = str(reference["min"]) in combined and str(reference["max"]) in combined
                error = ""
            except Exception as exc:
                guidelines, sources, source_hit, bounds_present, error = [], [], False, False, str(exc)
            rows.append({
                "condition": condition, "repeat": repeat, "k": args.k,
                "latency_ms": round((time.perf_counter() - started) * 1000, 4),
                "expected_source": reference["source"], "returned_sources": " | ".join(sources),
                "source_hit": source_hit, "expected_parameter": reference["parameter"],
                "expected_min": reference["min"], "expected_max": reference["max"],
                "bounds_present_in_retrieved_text": bounds_present, "chunks": len(guidelines), "error": error,
            })
            print(condition, repeat, f"{rows[-1]['latency_ms']:.2f} ms", "OK" if not error else "FAILED")
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} RAG-only measurements to {args.output}")


if __name__ == "__main__":
    main()
