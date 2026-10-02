"""Run the paired EMR RAG ablation for Evaluation 2."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation 2" / "results" / "rag_vs_norag_live.jsonl"
DATASET = ROOT / "datasets" / "clean" / "patients_200.json"
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool


def cases(limit: int) -> list[dict]:
    records = json.loads(DATASET.read_text(encoding="utf-8"))
    selected = []
    for record in records[:limit]:
        patient_id = str(record["identifier"][0]["value"])
        birth = record.get("birthDate", "")
        year, month, day = (int(part) for part in birth.split("-"))
        from datetime import date
        today = date.today()
        age = today.year - year - ((today.month, today.day) < (month, day))
        selected.append({"id": patient_id, "patient": {"id": patient_id, "age": age, "condition": record.get("condition", "hypertension")}})
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Required explicit flag for service calls")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--url", default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007"))
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to perform service calls; use analyze.py for saved results.")
    if not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected = cases(args.limit)
    with args.output.open("w", encoding="utf-8") as stream:
        for index, case in enumerate(selected, 1):
            order = (True, False) if index % 2 else (False, True)
            for run_order, use_rag in enumerate(order, 1):
                started = time.perf_counter()
                row = {"patient_id": case["id"], "index": index, "use_rag": use_rag, "run_order": run_order}
                try:
                    result = call_tool(args.url, "run_cdss", {"patient_id": case["id"], "use_rag": use_rag}, timeout=args.timeout)
                    row["result"] = result
                    row["client_total_ms"] = (time.perf_counter() - started) * 1000
                except Exception as exc:
                    row["error"] = str(exc)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
                print(case["id"], "RAG" if use_rag else "no-RAG", row.get("client_total_ms", "FAILED"))
    print(f"Wrote {2 * len(selected)} rows to {args.output}")


if __name__ == "__main__":
    main()
