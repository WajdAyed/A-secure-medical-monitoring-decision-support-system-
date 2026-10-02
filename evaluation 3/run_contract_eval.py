"""Execute end-to-end workflow, malformed-request, and privacy contract cases."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "clean" / "patients_200.json"
RANGES = ROOT / "evaluation" / "reference_ranges.json"
CASES = Path(__file__).with_name("cases.json")
DEFAULT_OUTPUT = Path(__file__).with_name("results") / "contract_raw.csv"
SENSITIVE_TERMS = ("sensor_value", "raw_sensor", "measurement_value", "device_value")


def load_patients(limit: int) -> list[dict]:
    records = json.loads(DATASET.read_text(encoding="utf-8"))
    selected = []
    seen = set()
    for record in records:
        condition = record.get("condition", "unknown")
        if condition not in seen:
            selected.append({"patient_id": record["identifier"][0]["value"], "condition": condition})
            seen.add(condition)
        if len(selected) >= limit:
            break
    return selected


def rpc(url: str, name: str, arguments: dict, timeout: float) -> tuple[dict, float, str]:
    started = time.perf_counter()
    try:
        response = requests.post(f"{url.rstrip('/')}/rpc", json={"jsonrpc": "2.0", "id": name, "method": "tools/call", "params": {"name": name, "arguments": arguments}}, timeout=timeout)
        latency = (time.perf_counter() - started) * 1000
        return response.json(), latency, ""
    except Exception as exc:
        return {}, (time.perf_counter() - started) * 1000, str(exc)


def has_sensitive_data(value: object) -> bool:
    serialized = json.dumps(value, default=str).lower()
    return any(term in serialized for term in SENSITIVE_TERMS)


def valid_workflow(body: dict) -> tuple[bool, str]:
    result = body.get("result", {}).get("structuredContent", {})
    if body.get("error") or not isinstance(result, dict):
        return False, "rpc_error_or_missing_result"
    for key in ("patient", "policy", "proof", "decision"):
        if key not in result:
            return False, f"missing_{key}"
    policies = result["policy"].get("policies") if isinstance(result["policy"], dict) else None
    policy_items = policies if isinstance(policies, list) else [result["policy"]]
    for policy in policy_items:
        if not isinstance(policy, dict) or not isinstance(policy.get("min"), (int, float)) or not isinstance(policy.get("max"), (int, float)) or policy["min"] > policy["max"]:
            return False, "invalid_policy_bounds"
    proof = result["proof"] if isinstance(result["proof"], dict) else {}
    decision = result["decision"].get("status") if isinstance(result["decision"], dict) else None
    proof_status = proof.get("status")
    verified = proof.get("verified") is True
    expected = "IN_RANGE" if verified and proof_status == "NORMAL" else "OUT_OF_RANGE" if proof_status == "ALERT" else "UNABLE_TO_ASSESS"
    if decision != expected:
        return False, f"decision_mismatch:{decision}!={expected}"
    if has_sensitive_data(result):
        return False, "sensitive_value_leak"
    return True, "ok"


def result_row(family: str, case: str, expected: str, passed: bool, latency: float, detail: str) -> dict:
    return {"family": family, "case": case, "expected": expected, "passed": passed, "latency_ms": round(latency, 3), "detail": detail}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinator-url", default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007"))
    parser.add_argument("--privacy-url", default=os.getenv("PRIVACY_MCP_URL", "http://127.0.0.1:8003"))
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.limit < 1 or args.repeats < 1 or args.timeout <= 0:
        parser.error("limit, repeats, and timeout must be positive")
    patients = load_patients(args.limit)
    invalid_cases = json.loads(CASES.read_text(encoding="utf-8"))["privacy_invalid_cases"]
    output_rows = []
    for repeat in range(args.repeats):
        for patient in patients:
            body, latency, error = rpc(args.coordinator_url, "run_cdss", {"patient_id": str(patient["patient_id"]), "use_rag": True, "debug_sensor_values": False}, args.timeout)
            passed, detail = valid_workflow(body) if not error else (False, error)
            output_rows.append(result_row("valid_workflow", f"{patient['condition']}:{patient['patient_id']}:r{repeat + 1}", "contract_pass", passed, latency, detail))
        body, latency, error = rpc(args.coordinator_url, "run_cdss", {"patient_id": "missing-evaluation-patient", "use_rag": False}, args.timeout)
        result = body.get("result", {}).get("structuredContent", {})
        passed = bool(error or body.get("error") or result.get("error"))
        output_rows.append(result_row("unknown_patient", "missing_patient", "clean_error", passed, latency, error or str(result.get("error", body.get("error", "")))))
        for invalid in invalid_cases:
            arguments = {} if invalid["bounds"] is None else {"bounds": invalid["bounds"], "patient_id": str(patients[0]["patient_id"])}
            body, latency, error = rpc(args.privacy_url, "request_proof", arguments, args.timeout)
            structured = body.get("result", {}).get("structuredContent", {})
            passed = bool(error or body.get("error") or body.get("result", {}).get("isError") or structured.get("error"))
            output_rows.append(result_row("privacy_invalid", invalid["name"], "clean_error", passed, latency, error or json.dumps(body.get("error", structured))))
        bounds = json.loads(RANGES.read_text(encoding="utf-8"))["ranges"][patients[0]["condition"]]
        body, latency, error = rpc(args.privacy_url, "request_proof", {"bounds": {key: bounds[key] for key in ("parameter", "min", "max")}, "patient_id": str(patients[0]["patient_id"]), "debug_sensor_values": False}, args.timeout)
        content = body.get("result", {}).get("structuredContent", {})
        passed = not error and not body.get("error") and isinstance(content, dict) and content.get("status") in {"NORMAL", "ALERT", "PROOF_FAILED"} and not has_sensitive_data(content)
        output_rows.append(result_row("privacy_normal", "debug_disabled_no_leak", "status_without_raw_value", passed, latency, "ok" if passed else error or json.dumps(content)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0])); writer.writeheader(); writer.writerows(output_rows)
    print(f"Wrote {len(output_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()