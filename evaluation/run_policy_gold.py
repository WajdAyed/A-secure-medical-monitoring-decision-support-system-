"""Experiment 2: evaluate RAG policy generation against clinician-filled gold policies."""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import time
from pathlib import Path

from evaluation_utils import RESULTS, SEED, seed_everything, write_csv

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool


def load_gold(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle: rows = list(csv.DictReader(handle))
    required = {"condition", "age", "parameter", "ref_min", "ref_max", "source_page"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("gold_policies.csv must contain the template headers and at least one reviewed row")
    for row in rows:
        if not all(row.get(name, "").strip() for name in required):
            raise ValueError("gold_policies.csv contains blank values; do not run until all references are filled")
        row["age"], row["ref_min"], row["ref_max"] = int(row["age"]), float(row["ref_min"]), float(row["ref_max"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=ROOT / "evaluation" / "gold_policies.csv")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--tolerance", type=float, default=0, help="Absolute error tolerance in the policy parameter's units")
    parser.add_argument("--rule-url", default=os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
    parser.add_argument("--knowledge-url", default=os.getenv("KNOWLEDGE_MCP_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--output", type=Path, default=RESULTS / "policy_gold_raw.csv")
    args = parser.parse_args()
    if args.repeats != 5: parser.error("This preregistered experiment uses exactly --repeats 5")
    if args.tolerance < 0: parser.error("--tolerance cannot be negative")
    seed_everything(); cases = load_gold(args.gold); rows = []
    for case_index, case in enumerate(cases):
        patient = {"id": f"gold-{case_index}", "condition": case["condition"], "age": case["age"]}
        for mode, use_rag in (("no_rag", False), ("rag", True)):
            retrieved = []
            retrieval_error = ""
            if use_rag:
                try: retrieved = call_tool(args.knowledge_url, "search_guidelines", {"query": case["condition"], "k": 3}, timeout=60).get("guidelines", [])
                except Exception as exc: retrieval_error = str(exc)
            ref_text = f"{case['ref_min']:g}" in "\n".join(retrieved) and f"{case['ref_max']:g}" in "\n".join(retrieved)
            for repeat in range(1, 6):
                began = time.perf_counter()
                try:
                    policy = call_tool(args.rule_url, "generate_policy", {"patient": patient, "use_rag": use_rag}, timeout=180)
                    valid = isinstance(policy.get("min"), (int, float)) and isinstance(policy.get("max"), (int, float)) and policy["min"] < policy["max"]
                    minimum, maximum = policy.get("min", ""), policy.get("max", "")
                    min_error = abs(float(minimum) - case["ref_min"]) if valid else ""
                    max_error = abs(float(maximum) - case["ref_max"]) if valid else ""
                    within = valid and min_error <= args.tolerance and max_error <= args.tolerance
                    error = ""
                except Exception as exc:
                    valid, minimum, maximum, min_error, max_error, within, error = False, "", "", "", "", False, str(exc)
                rows.append({"seed": SEED, "case_index": case_index, "condition": case["condition"], "age": case["age"], "parameter": case["parameter"], "source_page": case["source_page"], "mode": mode, "repeat": repeat, "json_valid": valid, "min": minimum, "max": maximum, "min_absolute_error": min_error, "max_absolute_error": max_error, "within_tolerance": within, "retrieval_hit_at_3": ref_text if use_rag else "", "retrieval_error": retrieval_error, "latency_ms": round((time.perf_counter()-began)*1000, 4), "error": error})
    fields = list(rows[0]) if rows else []
    write_csv(args.output, rows, fields)
    summary = []
    for mode in ("no_rag", "rag"):
        subset = [row for row in rows if row["mode"] == mode]
        valid = [row for row in subset if row["json_valid"]]
        mae = [((float(r["min_absolute_error"]) + float(r["max_absolute_error"])) / 2) for r in valid]
        case_stds = []
        for case in {r["case_index"] for r in valid}:
            values = [float(r["min"]) for r in valid if r["case_index"] == case]
            if len(values) > 1: case_stds.append(statistics.stdev(values))
        summary.append({"mode": mode, "n": len(subset), "json_valid_rate": len(valid)/len(subset) if subset else "", "mean_bound_mae": statistics.mean(mae) if mae else "", "within_tolerance_rate": sum(bool(r["within_tolerance"]) for r in subset)/len(subset) if subset else "", "run_to_run_min_sd": statistics.mean(case_stds) if case_stds else "", "retrieval_hit_at_3": sum(bool(r["retrieval_hit_at_3"]) for r in subset if r["retrieval_hit_at_3"] != "") / max(1, sum(r["retrieval_hit_at_3"] != "" for r in subset)) if mode == "rag" else ""})
    write_csv(RESULTS / "policy_gold_summary.csv", summary, list(summary[0]))
    print(f"Wrote {len(rows)} raw policy results to {args.output}")


if __name__ == "__main__": main()
