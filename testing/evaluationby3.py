"""Evaluate the real CDSS pipeline on the fixed 200-patient EMR dataset.

The evaluator uses the deployed coordinator for both modes.  RAG mode calls
``run_cdss(use_rag=True)``; the project's no-RAG branch calls the same tool with
``use_rag=False`` and therefore bypasses ChromaDB while reading the complete
matching project guideline PDF for every patient.  Conditions without a local
guideline PDF are recorded as errors rather than assigned invented ranges.

Examples (from the repository root)::

    python Testing/evaluationby3.py --skip-scalability
    python Testing/evaluationby3.py --scalability-sample-size 20 --scalability-repeats 2

Startup time is never included.  A measured patient time is the client-side
wall-clock duration of one HTTP request to the coordinator, including EMR
lookup, policy generation, proof validation, final decision, and request/
response transport.  Concurrent runs share the configured coordinator,
rule-engine, ChromaDB, Ollama model instances, and their caches.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "clean" / "patients_200.json"
DEFAULT_OUTPUT = ROOT / "Testing" / "evaluationby3_results"
EXPECTED_PATIENTS = 200
DEFAULT_CONCURRENCY = (1, 2, 4, 8)

# Vital-sign aliases are only naming normalization. Bounds are not converted
# between clinical units because the policy contract does not return units.
PARAMETER_ALIASES = {
    "systolic blood pressure": "systolic_bp",
    "systolic-bp": "systolic_bp",
    "blood pressure systolic": "systolic_bp",
    "blood glucose": "blood_glucose",
    "glucose": "blood_glucose",
    "oxygen saturation": "oxygen_saturation",
    "spo2": "oxygen_saturation",
    "heart rate": "heart_rate",
    "peak flow": "peak_flow_percent",
    "peak flow percent": "peak_flow_percent",
    "weight": "weight_kg",
}


@dataclass
class PatientMeasurement:
    patient_id: str
    mode: str
    elapsed_seconds: float
    ranges: list[dict[str, Any]]
    error: str = ""


@dataclass
class Comparison:
    patient_id: str
    classification: str
    reason: str
    details: list[dict[str, Any]]


def checkpoint(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_patient_ids(path: Path, exclude_patient: str) -> list[str]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"Dataset must contain a JSON list: {path}")
    if len(records) != EXPECTED_PATIENTS:
        raise ValueError(f"Expected {EXPECTED_PATIENTS} patients, found {len(records)}")
    patient_ids = []
    for record in records:
        try:
            patient_ids.append(str(record["identifier"][0]["value"]))
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Patient lacks identifier: {record!r}") from exc
    patient_ids.sort()
    if len(set(patient_ids)) != EXPECTED_PATIENTS:
        raise ValueError("Patient identifiers are not unique")

    # "#155" means the 155th patient in the fixed sorted order.  An explicit
    # EMR ID can also be supplied for reproducibility.
    if exclude_patient.isdigit() and 1 <= int(exclude_patient) <= len(patient_ids):
        removed = patient_ids.pop(int(exclude_patient) - 1)
        checkpoint(f"Excluded patient #{exclude_patient} (EMR ID {removed})")
    elif exclude_patient:
        if exclude_patient not in patient_ids:
            raise ValueError(f"Excluded patient ID not found: {exclude_patient}")
        patient_ids.remove(exclude_patient)
        checkpoint(f"Excluded patient ID {exclude_patient}")
    return patient_ids


def rpc_run(coordinator_url: str, patient_id: str, use_rag: bool, timeout: float) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": f"evaluationby3-{patient_id}-{int(use_rag)}",
        "method": "tools/call",
        "params": {
            "name": "run_cdss",
            "arguments": {"patient_id": patient_id, "use_rag": use_rag},
        },
    }
    response = requests.post(f"{coordinator_url.rstrip('/')}/rpc", json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise RuntimeError(f"JSON-RPC error: {body['error']}")
    result = body.get("result", {}).get("structuredContent")
    if not isinstance(result, dict):
        raise RuntimeError(f"Coordinator returned no structured result: {body!r}")
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def extract_ranges(result: dict[str, Any]) -> list[dict[str, Any]]:
    policy = result.get("policy")
    policies = policy.get("policies") if isinstance(policy, dict) else None
    candidates = policies if isinstance(policies, list) else [policy]
    ranges = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        parameter = candidate.get("parameter", candidate.get("vital_sign", ""))
        minimum = _number(candidate.get("min", candidate.get("lower")))
        maximum = _number(candidate.get("max", candidate.get("upper")))
        if parameter and minimum is not None and maximum is not None:
            ranges.append({
                "vital_sign": canonical_parameter(str(parameter)),
                "parameter_raw": str(parameter),
                "lower": minimum,
                "upper": maximum,
            })
    return ranges


def canonical_parameter(value: str) -> str:
    normalized = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return PARAMETER_ALIASES.get(normalized, normalized.replace(" ", "_"))


def measure_patient(coordinator_url: str, patient_id: str, use_rag: bool, timeout: float) -> PatientMeasurement:
    mode = "rag" if use_rag else "no_rag"
    started = time.perf_counter()
    try:
        result = rpc_run(coordinator_url, patient_id, use_rag, timeout)
        elapsed = time.perf_counter() - started
        ranges = extract_ranges(result)
        if not ranges:
            raise ValueError(f"No valid clinical ranges in coordinator result: {result!r}")
        return PatientMeasurement(patient_id, mode, elapsed, ranges)
    except Exception as exc:
        return PatientMeasurement(patient_id, mode, time.perf_counter() - started, [], str(exc))


def run_sequential(coordinator_url: str, patient_ids: list[str], use_rag: bool, timeout: float) -> list[PatientMeasurement]:
    measurements = []
    warmup = measure_patient(coordinator_url, patient_ids[0], use_rag, timeout)
    checkpoint(f"{('RAG' if use_rag else 'no-RAG')} warm-up {warmup.patient_id}: " + ("OK" if not warmup.error else warmup.error))
    for index, patient_id in enumerate(patient_ids[1:], start=1):
        measurement = measure_patient(coordinator_url, patient_id, use_rag, timeout)
        measurements.append(measurement)
        if measurement.error:
            checkpoint(f"{('RAG' if use_rag else 'no-RAG')} {patient_id}: FAILED: {measurement.error}")
        elif index % 10 == 0 or index == len(patient_ids) - 1:
            checkpoint(f"{('RAG' if use_rag else 'no-RAG')} processed {index}/{len(patient_ids) - 1}")
    return measurements


def summarize_measurements(measurements: list[PatientMeasurement]) -> dict[str, Any]:
    successful = [item for item in measurements if not item.error]
    return {
        "measured_patient_count": len(measurements),
        "successful_patient_count": len(successful),
        "failed_patient_count": len(measurements) - len(successful),
        "T_seconds": sum(item.elapsed_seconds for item in measurements),
        "M_seconds_successful": statistics.mean(item.elapsed_seconds for item in successful) if successful else None,
        "startup_included": False,
        "timed_scope": "One client-side coordinator HTTP request per patient, including EMR, policy, proof, decision, and transport; process/service startup excluded.",
    }


def range_rows(measurements: list[PatientMeasurement]) -> list[dict[str, Any]]:
    rows = []
    for measurement in measurements:
        if measurement.error:
            rows.append({"patient_id": measurement.patient_id, "mode": measurement.mode, "vital_sign": "", "lower": "", "upper": "", "processing_seconds": measurement.elapsed_seconds, "error": measurement.error})
        else:
            for item in measurement.ranges:
                rows.append({"patient_id": measurement.patient_id, "mode": measurement.mode, **item, "processing_seconds": measurement.elapsed_seconds, "error": ""})
    return rows


def normalized_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError, TypeError):
        return None


def compare_measurements(rag: list[PatientMeasurement], no_rag: list[PatientMeasurement], tolerance: float) -> list[Comparison]:
    rag_map = {item.patient_id: {row["vital_sign"]: row for row in item.ranges} for item in rag}
    no_rag_map = {item.patient_id: {row["vital_sign"]: row for row in item.ranges} for item in no_rag}
    rag_errors = {item.patient_id: item.error for item in rag if item.error}
    no_rag_errors = {item.patient_id: item.error for item in no_rag if item.error}
    patient_ids = sorted(set(rag_map) | set(no_rag_map) | set(rag_errors) | set(no_rag_errors))
    comparisons = []
    tolerance_decimal = Decimal(str(tolerance))
    for patient_id in patient_ids:
        details = []
        reasons = []
        if patient_id in rag_errors or patient_id in no_rag_errors:
            reasons.append("error: " + "; ".join(filter(None, [rag_errors.get(patient_id), no_rag_errors.get(patient_id)])))
        vital_signs = sorted(set(rag_map.get(patient_id, {})) | set(no_rag_map.get(patient_id, {})))
        for vital_sign in vital_signs:
            left, right = rag_map.get(patient_id, {}).get(vital_sign), no_rag_map.get(patient_id, {}).get(vital_sign)
            detail = {"patient_id": patient_id, "vital_sign": vital_sign, "rag_lower": "", "rag_upper": "", "no_rag_lower": "", "no_rag_upper": "", "reason": ""}
            if left:
                detail.update(rag_lower=left["lower"], rag_upper=left["upper"])
            if right:
                detail.update(no_rag_lower=right["lower"], no_rag_upper=right["upper"])
            if not left or not right:
                detail["reason"] = "missing range in " + ("RAG" if not left else "no-RAG")
                reasons.append(detail["reason"])
            else:
                mismatches = []
                for label in ("lower", "upper"):
                    left_value = normalized_decimal(left[label])
                    right_value = normalized_decimal(right[label])
                    if left_value is None or right_value is None:
                        mismatches.append(f"{label} is non-numeric")
                    elif left_value != right_value:
                        mismatches.append(f"{label} differs")
                    detail[f"{label}_compatible_exact"] = left_value == right_value
                    detail[f"{label}_compatible_tolerance"] = abs(left_value - right_value) <= tolerance_decimal
                if mismatches:
                    detail["reason"] = "; ".join(mismatches)
                    reasons.append(detail["reason"])
            details.append(detail)
        if reasons and any(reason.startswith("missing range") or reason.startswith("error:") for reason in reasons):
            classification = "not_comparable"
        elif reasons:
            classification = "incompatible"
        else:
            classification = "compatible"
        comparisons.append(Comparison(patient_id, classification, "; ".join(reasons), details))
    return comparisons


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_scalability(coordinator_url: str, patient_ids: list[str], timeout: float, levels: tuple[int, ...], repeats: int, sample_size: int, use_rag: bool) -> list[dict[str, Any]]:
    workload = patient_ids[:sample_size]
    rows = []
    mode = "rag" if use_rag else "no_rag"
    for concurrency in levels:
        for repeat in range(1, repeats + 1):
            started = time.perf_counter()
            measurements = []
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(measure_patient, coordinator_url, patient_id, use_rag, timeout) for patient_id in workload]
                for future in as_completed(futures):
                    measurements.append(future.result())
            wall = time.perf_counter() - started
            successful = [item for item in measurements if not item.error]
            latencies = [item.elapsed_seconds for item in measurements]
            row = {
                "mode": mode, "concurrency": concurrency, "repeat": repeat,
                "workload_patients": len(workload), "successful_requests": len(successful),
                "failed_requests": len(measurements) - len(successful),
                "mean_latency_seconds": statistics.mean(latencies) if latencies else None,
                "latency_stdev_seconds": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
                "batch_wall_seconds": wall,
                "throughput_patients_per_second": len(successful) / wall if wall else 0.0,
                "shared_services_caches_model_instances": True,
            }
            rows.append(row)
            checkpoint(f"scalability {mode} concurrency={concurrency} repeat={repeat}: mean={row['mean_latency_seconds']:.3f}s throughput={row['throughput_patients_per_second']:.2f}/s failed={row['failed_requests']}")
    return rows


def save_figures(output: Path, summary: dict[str, Any], comparisons: list[Comparison], scalability: list[dict[str, Any]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        checkpoint(f"Figures skipped; install matplotlib: {exc}")
        return
    output.mkdir(parents=True, exist_ok=True)
    labels = ["RAG", "No RAG"]
    means = [summary["rag"]["M_seconds_successful"] or 0, summary["no_rag"]["M_seconds_successful"] or 0]
    totals = [summary["rag"]["T_seconds"], summary["no_rag"]["T_seconds"]]
    counts = [sum(item.classification == "compatible" for item in comparisons), sum(item.classification == "incompatible" for item in comparisons), sum(item.classification == "not_comparable" for item in comparisons)]
    for values, title, ylabel, filename in ((means, "Mean patient processing time", "Seconds", "mean_processing_time.png"), (totals, "Total measured patient processing time", "Seconds", "total_processing_time.png")):
        figure, axis = plt.subplots(figsize=(7, 4)); axis.bar(labels, values, color=["#0072B2", "#D55E00"]); axis.set_title(title); axis.set_ylabel(ylabel); axis.set_xlabel("Pipeline mode"); axis.text(0.99, 0.98, f"Successful patients: RAG n={summary['rag']['successful_patient_count']}; no-RAG n={summary['no_rag']['successful_patient_count']}", transform=axis.transAxes, ha="right", va="top"); figure.tight_layout(); figure.savefig(output / filename, dpi=300); plt.close(figure)
    figure, axis = plt.subplots(figsize=(7, 4)); axis.bar(["Compatible", "Incompatible", "Not comparable"], counts, color=["#009E73", "#D55E00", "#999999"]); axis.set_title("Patient range comparison"); axis.set_ylabel("Patients (n=198)"); figure.tight_layout(); figure.savefig(output / "patient_comparison_counts.png", dpi=300); plt.close(figure)
    for mode in sorted({row["mode"] for row in scalability}):
        mode_rows = [row for row in scalability if row["mode"] == mode]
        grouped = []
        for level in sorted({row["concurrency"] for row in mode_rows}):
            values = [row["mean_latency_seconds"] for row in mode_rows if row["concurrency"] == level]
            grouped.append((level, statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0))
        if not grouped:
            continue
        figure, axis = plt.subplots(figsize=(7, 4)); axis.errorbar([item[0] for item in grouped], [item[1] for item in grouped], yerr=[item[2] for item in grouped], marker="o", capsize=4); axis.set_xticks([1, 2, 4, 8]); axis.set_xlabel("Concurrent clients"); axis.set_ylabel("Mean latency (seconds)"); axis.set_title(f"{mode.upper()} pipeline scalability"); axis.grid(axis="y", alpha=0.3); figure.tight_layout(); figure.savefig(output / f"scalability_{mode}.png", dpi=300); plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--coordinator-url", default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--exclude-patient", default="155", help="1-based ordered patient number, or exact EMR ID")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--tolerance", type=float, default=0.0, help="Optional absolute bound tolerance; exact agreement remains primary")
    parser.add_argument("--scalability-concurrency", nargs="+", type=int, default=list(DEFAULT_CONCURRENCY))
    parser.add_argument("--scalability-repeats", type=int, default=2)
    parser.add_argument("--scalability-sample-size", type=int, default=None, help="Defaults to every measured patient")
    parser.add_argument("--skip-scalability", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or args.tolerance < 0 or args.scalability_repeats < 1 or any(level < 1 for level in args.scalability_concurrency):
        parser.error("timeout/tolerance/repeats/concurrency values are invalid")

    patient_ids = load_patient_ids(args.dataset, args.exclude_patient)
    if len(patient_ids) < 2:
        raise SystemExit("At least two patients are required so one can be warm-up")
    measured_count = len(patient_ids) - 1
    sample_size = measured_count if args.scalability_sample_size is None else args.scalability_sample_size
    if not 1 <= sample_size <= measured_count:
        parser.error(f"--scalability-sample-size must be between 1 and {measured_count}")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        requests.get(f"{args.coordinator_url.rstrip('/')}/docs", timeout=5).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Coordinator unavailable at {args.coordinator_url}: {exc}") from exc

    os.environ.setdefault("CDSS_EVAL", "1")
    checkpoint(f"Fixed order contains {len(patient_ids)} patients after exclusion; first patient is warm-up; {measured_count} measured")
    rag = run_sequential(args.coordinator_url, patient_ids, True, args.timeout)
    no_rag = run_sequential(args.coordinator_url, patient_ids, False, args.timeout)
    comparisons = compare_measurements(rag, no_rag, args.tolerance)
    scalability = []
    if not args.skip_scalability:
        scalability.extend(run_scalability(args.coordinator_url, patient_ids[1:], args.timeout, tuple(args.scalability_concurrency), args.scalability_repeats, sample_size, True))
        scalability.extend(run_scalability(args.coordinator_url, patient_ids[1:], args.timeout, tuple(args.scalability_concurrency), args.scalability_repeats, sample_size, False))

    summary = {"rag": summarize_measurements(rag), "no_rag": summarize_measurements(no_rag), "comparison": {name: sum(item.classification == name for item in comparisons) for name in ("compatible", "incompatible", "not_comparable")}, "definitions": {"primary_compatibility": "Exact lower-bound and upper-bound agreement after canonical vital-sign naming and numeric normalization.", "tolerance_compatibility": f"Absolute bound difference <= {args.tolerance}; reported per bound in comparison details, never substituted for exact counts.", "no_rag_source": "The project's generate_policy_without_rag branch; it does not query ChromaDB or create embeddings, and loads the complete matching PDF from RAG/guidelines for every supported condition. Missing project PDFs remain errors.", "excluded_patient": args.exclude_patient, "warmup_patient_id": patient_ids[0], "shared_concurrency_resources": "Concurrent requests share the coordinator, EMR, rule engine, ChromaDB, Ollama model instances, and caches."}}
    (args.output / "results.json").write_text(json.dumps({"summary": summary, "scalability": scalability, "comparison_details": [item.__dict__ for item in comparisons]}, indent=2, default=str), encoding="utf-8")
    write_csv(args.output / "ranges.csv", range_rows(rag) + range_rows(no_rag))
    comparison_rows = [detail for item in comparisons for detail in item.details]
    for item in comparisons:
        if not item.details:
            comparison_rows.append({"patient_id": item.patient_id, "vital_sign": "", "reason": item.reason})
    write_csv(args.output / "comparison_details.csv", comparison_rows)
    write_csv(args.output / "scalability.csv", scalability)
    save_figures(args.output, summary, comparisons, scalability)

    print("\nEvaluation summary")
    print(f"T_rag={summary['rag']['T_seconds']:.6f}s; M_rag={summary['rag']['M_seconds_successful']!s}s; errors={summary['rag']['failed_patient_count']}")
    print(f"T_no_rag={summary['no_rag']['T_seconds']:.6f}s; M_no_rag={summary['no_rag']['M_seconds_successful']!s}s; errors={summary['no_rag']['failed_patient_count']}")
    print("Comparison counts: " + ", ".join(f"{key}={value}" for key, value in summary["comparison"].items()))
    print(f"Startup included: no. Results: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Evaluation interrupted", file=sys.stderr)
        raise SystemExit(130)
