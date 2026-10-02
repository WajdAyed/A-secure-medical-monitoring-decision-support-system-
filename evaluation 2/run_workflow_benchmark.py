"""Benchmark the complete CDSS workflow across 199 warmed-up EMR patients."""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "clean" / "patients_200.json"
DEFAULT_OUTPUT = ROOT / "evaluation 2" / "results" / "workflow_raw.csv"


def patient_ids() -> list[str]:
    records = json.loads(DATASET.read_text(encoding="utf-8"))
    identifiers = [str(record["identifier"][0]["value"]) for record in records]
    if len(identifiers) != 200 or len(set(identifiers)) != 200:
        raise ValueError("Expected 200 unique EMR patient identifiers")
    return sorted(identifiers)


def call_workflow(url: str, patient_id: str, timeout: float, use_rag: bool, max_latency_ms: float) -> dict:
    payload = {"jsonrpc": "2.0", "id": f"workflow-{patient_id}", "method": "tools/call", "params": {"name": "run_cdss", "arguments": {"patient_id": patient_id, "use_rag": use_rag}}}
    started = time.perf_counter()
    try:
        response = requests.post(f"{url.rstrip('/')}/rpc", json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(str(body["error"]))
        result = body["result"]["structuredContent"]
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        latency_ms = (time.perf_counter() - started) * 1000
        excluded = latency_ms > max_latency_ms
        return {"patient_id": patient_id, "ok": not excluded, "excluded": excluded, "status_code": response.status_code, "latency_ms": latency_ms, "result": result, "error": "over_latency_limit" if excluded else ""}
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return {"patient_id": patient_id, "ok": False, "excluded": latency_ms > max_latency_ms, "status_code": "", "latency_ms": latency_ms, "result": {}, "error": str(exc)}


def run_level(url: str, patient_ids_to_measure: list[str], concurrency: int, timeout: float, use_rag: bool, max_latency_ms: float, checkpoint) -> tuple[list[dict], float]:
    started = time.perf_counter()
    rows = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(call_workflow, url, patient_id, timeout, use_rag, max_latency_ms): patient_id for patient_id in patient_ids_to_measure}
        for future in as_completed(futures):
            row = future.result()
            row["concurrency"] = concurrency
            rows.append(row)
            checkpoint(row)
    return rows, (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007"))
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--max-latency-seconds", type=float, default=40)
    parser.add_argument("--sample-size", type=int, default=20, help="Measured patients per concurrency level; use 199 for patients 2-200")
    parser.add_argument("--use-rag", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if any(level < 1 for level in args.concurrency):
        parser.error("concurrency values must be positive")
    if args.timeout <= 0 or args.max_latency_seconds <= 0 or args.sample_size < 1 or args.sample_size > 199:
        parser.error("timeout values must be positive")
    max_latency_ms = args.max_latency_seconds * 1000
    all_ids = patient_ids()
    warmup_id = all_ids[0]
    measured_ids = all_ids[1:1 + args.sample_size]
    try:
        requests.get(f"{args.url.rstrip('/')}/docs", timeout=3).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Coordinator unavailable at {args.url}: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress_path = args.output.with_name("workflow_progress.csv")
    rows = []
    fields = ["patient_id", "warmup_patient_id", "concurrency", "use_rag", "ok", "excluded", "status_code", "latency_ms", "patient_ms", "policy_ms", "proof_ms", "decision_ms", "workflow_total_ms", "proof_verified", "decision", "batch_wall_ms", "error"]
    def checkpoint(row):
        progress = {"concurrency": row["concurrency"], "patient_id": row["patient_id"], "latency_ms": row["latency_ms"], "ok": row["ok"], "excluded": row.get("excluded", False), "error": row["error"]}
        existing = []
        if progress_path.exists():
            with progress_path.open(newline="", encoding="utf-8") as stream:
                existing = list(csv.DictReader(stream))
        existing.append(progress)
        with progress_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(progress)); writer.writeheader(); writer.writerows(existing)
    print(f"Warm-up patient: {warmup_id}; measured patients: {len(measured_ids)}")
    for concurrency in args.concurrency:
        warmup = call_workflow(args.url, warmup_id, args.timeout, args.use_rag, max_latency_ms)
        print(f"concurrency={concurrency} warm-up ok={warmup['ok']} latency={warmup['latency_ms']:.2f} ms")
        level_rows, wall_ms = run_level(args.url, measured_ids, concurrency, args.timeout, args.use_rag, max_latency_ms, checkpoint)
        for row in level_rows:
            row["warmup_patient_id"] = warmup_id
            row["batch_wall_ms"] = wall_ms
            row["use_rag"] = args.use_rag
            result = row.pop("result", {})
            timings = result.get("timings", {}) if isinstance(result, dict) else {}
            row.update({"patient_ms": timings.get("patient_ms", ""), "policy_ms": timings.get("policy_ms", ""), "proof_ms": timings.get("proof_ms", ""), "decision_ms": timings.get("decision_ms", ""), "workflow_total_ms": timings.get("total_ms", ""), "proof_verified": result.get("proof", {}).get("verified", "") if isinstance(result, dict) else "", "decision": result.get("decision", {}).get("status", result.get("decision", {}).get("message", "")) if isinstance(result, dict) else ""})
        rows.extend(level_rows)
        progress_rows = [{"concurrency": row["concurrency"], "patient_id": row["patient_id"], "latency_ms": row["latency_ms"], "ok": row["ok"], "excluded": row.get("excluded", False), "error": row["error"]} for row in rows]
        with progress_path.open("w", newline="", encoding="utf-8") as stream:
            progress_writer = csv.DictWriter(stream, fieldnames=list(progress_rows[0])); progress_writer.writeheader(); progress_writer.writerows(progress_rows)
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        success = sum(row["ok"] for row in level_rows)
        excluded = sum(row.get("excluded", False) for row in level_rows)
        print(f"concurrency={concurrency} measured={len(level_rows)} included={success} excluded={excluded} wall={wall_ms:.2f} ms")
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
