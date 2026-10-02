"""Analyse paired RAG/no-RAG EMR measurements and write thesis-ready summaries."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation 2"
DEFAULT_INPUT = ROOT / "evaluation" / "results" / "rag_vs_norag.jsonl"
REFERENCE = ROOT / "evaluation" / "reference_ranges.json"


def read_jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if "error" not in row and isinstance(row.get("result"), dict)]


def references() -> dict[str, dict]:
    if REFERENCE.exists():
        data = json.loads(REFERENCE.read_text(encoding="utf-8"))
        if data.get("ranges"):
            return data["ranges"]
    return {}


def iou(low: float, high: float, ref_low: float, ref_high: float) -> float:
    overlap = max(0.0, min(high, ref_high) - max(low, ref_low))
    union = max(high, ref_high) - min(low, ref_low)
    return overlap / union if union else 0.0


def number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="JSONL input; default uses live output if present, otherwise existing evaluation")
    args = parser.parse_args()
    source = args.input or (EVAL / "results" / "rag_vs_norag_live.jsonl")
    if not source.exists():
        source = DEFAULT_INPUT
    raw_rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = read_jsonl(source)
    if not rows:
        raise SystemExit(f"No successful measurements found in {source}")
    refs = references()
    measurements = []
    for row in rows:
        result = row["result"]
        patient = result.get("patient", {})
        policy = result.get("policy", {})
        condition = patient.get("condition", "unknown")
        reference = refs.get(condition, {})
        low, high = policy.get("min"), policy.get("max")
        valid = number(low) and number(high) and low < high
        ref_valid = number(reference.get("min")) and number(reference.get("max"))
        measurements.append({
            "patient_id": row.get("patient_id", ""),
            "condition": condition,
            "mode": "with_rag" if row.get("use_rag") else "without_rag",
            "run_order": row.get("run_order", ""),
            "policy_latency_ms": result.get("timings", {}).get("policy_ms", ""),
            "total_ms": result.get("timings", {}).get("total_ms", result.get("client_total_ms", "")),
            "patient_ms": result.get("timings", {}).get("patient_ms", ""),
            "proof_ms": result.get("timings", {}).get("proof_ms", ""),
            "decision_ms": result.get("timings", {}).get("decision_ms", ""),
            "policy_parameter": policy.get("parameter", ""),
            "policy_min": low if valid else "",
            "policy_max": high if valid else "",
            "valid_policy": valid,
            "parameter_match": bool(valid and ref_valid and policy.get("parameter") == reference.get("parameter")),
            "interval_iou": round(iou(low, high, reference["min"], reference["max"]), 6) if valid and ref_valid else "",
            "inside_reference": bool(valid and ref_valid and reference["min"] <= low and high <= reference["max"]),
            "exact_reference": bool(valid and ref_valid and policy.get("parameter") == reference.get("parameter") and low == reference["min"] and high == reference["max"]),
            "proof_verified": result.get("proof", {}).get("verified", ""),
            "decision_status": result.get("decision", {}).get("message", ""),
        })
    result_dir = EVAL / "results"
    write_csv(result_dir / "rag_emr_measurements.csv", measurements)

    successful_ids = {
        mode: {row["patient_id"] for row in measurements if row["mode"] == mode}
        for mode in ("without_rag", "with_rag")
    }
    matched_ids = successful_ids["without_rag"] & successful_ids["with_rag"]
    summaries = []
    for mode in ("without_rag", "with_rag"):
        group = [row for row in measurements if row["mode"] == mode and row["patient_id"] in matched_ids]
        quality = [row for row in group if row["interval_iou"] != ""]
        latencies = [float(row["policy_latency_ms"]) for row in group if row["policy_latency_ms"] != ""]
        totals = [float(row["total_ms"]) for row in group if row["total_ms"] != ""]
        summaries.append({
            "mode": mode, "n": len(group), "valid_policy_rate": sum(row["valid_policy"] for row in group) / len(group),
            "parameter_match_rate": sum(row["parameter_match"] for row in group) / len(group),
            "inside_reference_rate": sum(row["inside_reference"] for row in group) / len(group),
            "exact_reference_rate": sum(row["exact_reference"] for row in group) / len(group),
            "mean_interval_iou": statistics.mean(float(row["interval_iou"]) for row in quality) if quality else "",
            "mean_policy_ms": statistics.mean(latencies) if latencies else "",
            "median_policy_ms": statistics.median(latencies) if latencies else "",
            "p95_policy_ms": sorted(latencies)[max(0, math.ceil(.95 * len(latencies)) - 1)] if latencies else "",
            "mean_total_ms": statistics.mean(totals) if totals else "",
            "median_total_ms": statistics.median(totals) if totals else "",
            "p95_total_ms": sorted(totals)[max(0, math.ceil(.95 * len(totals)) - 1)] if totals else "",
            "proof_verified_rate": sum(str(row["proof_verified"]).lower() == "true" for row in group) / len(group),
        })
    write_csv(result_dir / "rag_summary.csv", summaries)

    stage_rows = []
    for mode in ("without_rag", "with_rag"):
        group = [row for row in measurements if row["mode"] == mode and row["patient_id"] in matched_ids]
        for stage, field in (("EMR retrieval", "patient_ms"), ("Policy generation", "policy_latency_ms"), ("ZKP validation", "proof_ms"), ("Decision", "decision_ms"), ("Total", "total_ms")):
            values = [float(row[field]) for row in group if row[field] != ""]
            stage_rows.append({"mode": mode, "stage": stage, "n": len(values), "mean_ms": statistics.mean(values) if values else "", "median_ms": statistics.median(values) if values else "", "p95_ms": sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)] if values else ""})
    write_csv(result_dir / "process_summary.csv", stage_rows)
    zkp_rows = [{"patient_id": row["patient_id"], "mode": row["mode"], "proof_ms": row["proof_ms"], "total_ms": row["total_ms"], "proof_share_pct": 100 * float(row["proof_ms"]) / float(row["total_ms"]) if row["proof_ms"] and row["total_ms"] else "", "verified": row["proof_verified"]} for row in measurements]
    write_csv(result_dir / "zkp_measurements.csv", zkp_rows)
    zkp_summary = []
    for mode in ("without_rag", "with_rag"):
        group = [row for row in zkp_rows if row["mode"] == mode and row["patient_id"] in matched_ids]
        values = [float(row["proof_ms"]) for row in group if row["proof_ms"] != ""]
        shares = [float(row["proof_share_pct"]) for row in group if row["proof_share_pct"] != ""]
        zkp_summary.append({"mode": mode, "n": len(values), "mean_zkp_ms": statistics.mean(values), "median_zkp_ms": statistics.median(values), "p95_zkp_ms": sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)], "mean_zkp_share_pct": statistics.mean(shares), "verified_rate": sum(str(row["verified"]).lower() == "true" for row in group) / len(group)})
    write_csv(result_dir / "zkp_summary.csv", zkp_summary)

    no_rag = {row["patient_id"]: row for row in measurements if row["mode"] == "without_rag"}
    rag = {row["patient_id"]: row for row in measurements if row["mode"] == "with_rag"}
    pairs = [patient_id for patient_id in no_rag.keys() & rag.keys()]
    agreements = sum(no_rag[patient_id]["decision_status"] == rag[patient_id]["decision_status"] for patient_id in pairs)
    delta = summaries[1]["mean_total_ms"] - summaries[0]["mean_total_ms"]
    failed_rows = len(raw_rows) - len(rows)
    report = ["# Evaluation 2 results", "", f"Source: `{source}`; successful paired measurements: {len(pairs)}; discarded failed rows: {failed_rows}.", "", "## Main result", "", f"Mean end-to-end time without RAG: **{summaries[0]['mean_total_ms']:.2f} ms**.", f"Mean end-to-end time with RAG: **{summaries[1]['mean_total_ms']:.2f} ms**.", f"RAG minus no-RAG: **{delta:.2f} ms** ({delta / summaries[0]['mean_total_ms']:.1%}).", f"Decision agreement for paired EMRs: **{agreements / len(pairs):.1%}**.", "", "## Interpretation", "", f"RAG policy accuracy by interval IoU was {summaries[1]['mean_interval_iou']:.3f} versus {summaries[0]['mean_interval_iou']:.3f} without RAG.", f"The measured ZKP stage averaged {zkp_summary[1]['mean_zkp_ms']:.2f} ms with RAG and {zkp_summary[0]['mean_zkp_ms']:.2f} ms without RAG; its share of total processing was {zkp_summary[1]['mean_zkp_share_pct']:.2f}% and {zkp_summary[0]['mean_zkp_share_pct']:.2f}%, respectively.", "", "The current measurements do not support the claim that RAG is faster or more accurate: RAG is slower and has lower IoU on these fallback references. These are software/system evaluation results, not clinical validation. The reference ranges in this repository are documented as fallback ranges and require clinician review before thesis claims about clinical accuracy. ZKP timing includes the privacy service, device call, process startup/IPC, proving, and verification; it is not a pure cryptographic microbenchmark."]
    (result_dir / "evaluation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Analysed {len(measurements)} successful rows from {source}")
    print(f"Mean total ms: no-RAG={summaries[0]['mean_total_ms']:.2f}, RAG={summaries[1]['mean_total_ms']:.2f}")


if __name__ == "__main__":
    main()
