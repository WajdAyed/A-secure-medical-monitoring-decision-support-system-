"""Evaluate the RAG-enabled policy answer only; no no-RAG requests are made."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evaluation 2" / "results" / "rag_policy_only_raw.csv"
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool

CASES = {
    "hypertension": {"parameter": "systolic_bp", "min": 110, "max": 135},
    "diabetes": {"parameter": "blood_glucose", "min": 70, "max": 140},
    "heart_failure": {"parameter": "weight_kg", "min": 60, "max": 90},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for condition, reference in CASES.items():
        for repeat in range(1, args.repeats + 1):
            started = time.perf_counter()
            try:
                policy = call_tool(args.url, "generate_policy", {"patient": {"id": f"rag-{condition}-{repeat}", "age": 50, "condition": condition}, "use_rag": True}, timeout=args.timeout)
                minimum, maximum = policy.get("min"), policy.get("max")
                valid = isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum < maximum
                parameter_match = valid and policy.get("parameter") == reference["parameter"]
                exact_match = parameter_match and minimum == reference["min"] and maximum == reference["max"]
                bound_error = abs(minimum - reference["min"]) + abs(maximum - reference["max"]) if valid else ""
                evaluation = policy.get("evaluation", {})
                error = ""
            except Exception as exc:
                policy, valid, parameter_match, exact_match, bound_error, evaluation, error = {}, False, False, False, "", {}, str(exc)
            rows.append({"condition": condition, "repeat": repeat, "latency_ms": round((time.perf_counter() - started) * 1000, 4), "retrieval_ms": evaluation.get("rag_retrieval_ms", ""), "llm_ms": evaluation.get("llm_ms", ""), "retrieved_chunks": evaluation.get("retrieved_chunks", ""), "parameter": policy.get("parameter", ""), "min": policy.get("min", ""), "max": policy.get("max", ""), "valid_policy": valid, "parameter_match": parameter_match, "exact_reference_match": exact_match, "total_bound_absolute_error": bound_error, "error": error})
            print(condition, repeat, f"{rows[-1]['latency_ms']:.2f} ms", "OK" if not error else "FAILED")
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} RAG policy measurements to {args.output}")


if __name__ == "__main__":
    main()
