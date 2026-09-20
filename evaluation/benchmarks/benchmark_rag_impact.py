"""Compare policy-generation quality and latency with RAG enabled versus disabled."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool

DATASET_PATH = ROOT / "datasets" / "clean" / "patients_200.json"


def load_patient_cases(dataset_path: Path = DATASET_PATH) -> list[dict]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    patients = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = []
    for patient in patients:
        identifier = next((str(item.get("value", "")).strip() for item in patient.get("identifier", [])
                           if str(item.get("value", "")).strip()), "")
        if not identifier:
            continue
        birth_date = patient.get("birthDate", "")
        birth_year, birth_month, birth_day = (int(part) for part in birth_date.split("-"))
        from datetime import date
        today = date.today()
        age = today.year - birth_year - ((today.month, today.day) < (birth_month, birth_day))
        cases.append({"id": identifier, "patient": {"id": identifier, "age": age, "condition": patient.get("condition", "hypertension")}})
    if len(cases) != len({case["id"] for case in cases}):
        raise ValueError(f"Dataset contains duplicate patient identifiers: {dataset_path}")
    return cases


def reported_cases(cases: list[dict], exclude_first: bool) -> list[tuple[dict, str]]:
    if not exclude_first:
        return [(case, "") for case in cases]
    return [(case, "") for case in cases[1:]] + [(cases[-1], cases[0]["id"])]


def score(policy: dict, reference: dict | None, tolerance: float) -> tuple[bool, bool | None, float | None, float | None]:
    lower, upper = policy.get("min"), policy.get("max")
    valid = isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and lower < upper
    if not valid:
        return False, None if reference is None else False, None, None
    if reference is None:
        return True, None, None, None
    min_error, max_error = abs(lower - reference["min"]), abs(upper - reference["max"])
    matches = policy.get("parameter") == reference["parameter"] and min_error <= tolerance and max_error <= tolerance
    return True, matches, min_error, max_error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
    parser.add_argument("--cases", type=Path, default=None, help="Optional fixture cases; omit to evaluate all patients in the dataset")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--patient-ids", nargs="*", default=None)
    parser.add_argument("--runs", type=int, default=1, help="Requests per patient/case and mode")
    parser.add_argument("--warmup", type=int, default=0, help="Additional discarded requests per reported patient and RAG mode (default: 0)")
    parser.add_argument("--exclude-first", action=argparse.BooleanOptionalAction, default=True,
                        help="Run and discard the first patient, then replace its reported row with a marked duplicate of the last patient")
    parser.add_argument("--tolerance", type=float, default=0, help="Allowed error for each reference bound")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "rag_impact_raw.csv")
    parser.add_argument("--checkpoint-every", type=int, default=10, help="Persist partial rows after this many measurements")
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0 or args.tolerance < 0 or args.checkpoint_every < 1:
        parser.error("runs and checkpoint-every must be positive; warmup and tolerance cannot be negative")
    if args.cases:
        selected_cases = [(case, "") for case in json.loads(args.cases.read_text(encoding="utf-8"))]
    else:
        cases = load_patient_cases(args.dataset)
        if args.patient_ids:
            selected = set(args.patient_ids)
            cases = [case for case in cases if case["id"] in selected]
        selected_cases = reported_cases(cases, args.exclude_first)
    if not selected_cases:
        parser.error("No RAG evaluation patients or cases selected")
    expected_rows = len(selected_cases) * 2 * args.runs
    print(f"Evaluating {len(selected_cases)} patient/case entries in both RAG modes")
    print(f"Expected measured rows: {expected_rows}; warm-up rows will be discarded")
    rows = []

    def write_rows() -> None:
        if not rows:
            return
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    if args.exclude_first and not args.cases:
        # Exercise each RAG mode for the first patient without recording either
        # cold-start latency. The last patient supplies the replacement rows.
        first_case = cases[0]
        for use_rag in (False, True):
            call_tool(args.url, "generate_policy", {"patient": first_case["patient"], "use_rag": use_rag}, timeout=args.timeout)
        print(f"Discarded cold-start requests for first patient {first_case['id']}")
    for case, replacement_for in selected_cases:
        for mode, use_rag in (("without_rag", False), ("with_rag", True)):
            for _ in range(args.warmup):
                call_tool(args.url, "generate_policy", {"patient": case["patient"], "use_rag": use_rag}, timeout=args.timeout)
            for run in range(1, args.runs + 1):
                started = time.perf_counter()
                try:
                    policy = call_tool(args.url, "generate_policy", {"patient": case["patient"], "use_rag": use_rag}, timeout=args.timeout)
                    if "error" in policy:
                        raise ValueError(f"Rule Engine error: {policy['error']}")
                    valid, matches, min_error, max_error = score(policy, case.get("reference_policy"), args.tolerance)
                    status_code, error = 200, ""
                except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
                    policy, valid, matches, min_error, max_error, status_code, error = {}, False, False, None, None, "", str(exc)
                row = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "case_id": case["id"], "patient_id": case["patient"].get("id", ""),
                       "replacement_for": replacement_for, "duplicate_replacement": bool(replacement_for), "run": run,
                       "mode": mode, "use_rag": use_rag, "latency_ms": round((time.perf_counter() - started) * 1000, 4),
                       "status_code": status_code, "valid_policy": valid, "matches_reference": matches,
                       "min_absolute_error": min_error, "max_absolute_error": max_error,
                       "parameter": policy.get("parameter", ""), "min": policy.get("min", ""), "max": policy.get("max", ""), "error": error}
                rows.append(row)
                print(f"{case['id']} {mode}: {row['latency_ms']:.2f} ms, reference_match={matches}")
                if len(rows) % args.checkpoint_every == 0:
                    write_rows()
    write_rows()
    if len(rows) != expected_rows:
        raise SystemExit(f"Expected {expected_rows} measured rows, wrote {len(rows)}")
    print(f"Wrote {len(rows)} measured rows to {args.output}")
    if any(row["error"] for row in rows):
        raise SystemExit("One or more policy requests failed; inspect the CSV.")


if __name__ == "__main__":
    main()
