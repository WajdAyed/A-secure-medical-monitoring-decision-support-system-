"""Benchmark the complete patient-to-decision workflow at different concurrency levels."""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parent
PATIENTS_FILE = ROOT / "datasets" / "clean" / "patients_200.json"
OUTPUT_DIR = ROOT / "evaluation 2" / "results" / "testing_scalability"
PHASES = {
    "patient_ms": "Patient retrieval",
    "policy_ms": "Policy / RAG",
    "proof_ms": "Proof validation",
    "decision_ms": "Final decision",
}


def load_patient_ids() -> list[str]:
    records = json.loads(PATIENTS_FILE.read_text(encoding="utf-8"))
    identifiers = [str(record["identifier"][0]["value"]) for record in records]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Patient dataset must contain unique identifiers")
    return sorted(identifiers)


def call_workflow(url: str, patient_id: str, timeout: float, use_rag: bool) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "tools/call",
        "params": {
            "name": "run_cdss",
            "arguments": {"patient_id": patient_id, "use_rag": use_rag},
        },
    }
    started = time.perf_counter()
    status_code = ""
    try:
        response = requests.post(f"{url.rstrip('/')}/rpc", json=payload, timeout=timeout)
        status_code = response.status_code
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(str(body["error"]))
        tool_result = body["result"]
        result = tool_result["structuredContent"]
        if tool_result.get("isError") or "error" in result:
            raise RuntimeError(str(result.get("error", "Workflow returned an error")))
        if "decision" not in result:
            raise RuntimeError("Workflow response did not include a final decision")
        decision = result["decision"]
        if isinstance(decision, dict):
            decision = decision.get("status", decision.get("message", str(decision)))
        timings = result.get("timings", {})
        phase_times = {
            key: float(timings[key]) / 1000
            if isinstance(timings.get(key), (int, float))
            else ""
            for key in PHASES
        }
        return {
            "patient_id": patient_id,
            "success": True,
            "status_code": status_code,
            "case_time_s": time.perf_counter() - started,
            "decision": str(decision),
            "error": "",
            **phase_times,
        }
    except Exception as exc:
        return {
            "patient_id": patient_id,
            "success": False,
            "status_code": status_code,
            "case_time_s": time.perf_counter() - started,
            "decision": "",
            "error": str(exc),
            **{key: "" for key in PHASES},
        }


def run_batch(
    url: str,
    patient_ids: list[str],
    concurrency: int,
    repeat_number: int,
    timeout: float,
    use_rag: bool,
) -> tuple[dict, list[dict]]:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(call_workflow, url, patient_id, timeout, use_rag)
            for patient_id in patient_ids
        ]
        request_results = [future.result() for future in as_completed(futures)]
    successes = sum(row["success"] for row in request_results)
    summary = {
        "concurrency": concurrency,
        "repeat": repeat_number,
        "requested": len(patient_ids),
        "successes": successes,
        "failures": len(patient_ids) - successes,
    }
    return summary, request_results


def aggregate_results(batch_summaries: list[dict], request_rows: list[dict]) -> list[dict]:
    levels = sorted({row["concurrency"] for row in batch_summaries})
    aggregates = []
    for concurrency in levels:
        batches = [row for row in batch_summaries if row["concurrency"] == concurrency]
        requests_at_level = [row for row in request_rows if row["concurrency"] == concurrency]
        successful = [row for row in requests_at_level if row["success"]]
        aggregate = {
            "concurrency": concurrency,
            "repetitions": len(batches),
            "requested": len(requests_at_level),
            "successes": len(successful),
            "failures": len(requests_at_level) - len(successful),
        }
        for phase in PHASES:
            values = [float(row[phase]) for row in successful if row.get(phase) not in ("", None)]
            aggregate[f"mean_{phase}"] = statistics.mean(values) if values else ""
        aggregates.append(aggregate)
    return aggregates


def save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plot(aggregate: list[dict]) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Matplotlib is unavailable; CSV results were saved without plots.")
        return False

    levels = [row["concurrency"] for row in aggregate]
    positions = list(range(len(levels)))
    width = 0.18
    fig, axis = plt.subplots(figsize=(9, 5))
    for index, (phase, label) in enumerate(PHASES.items()):
        values = [
            float(row[f"mean_{phase}"]) if row[f"mean_{phase}"] != "" else float("nan")
            for row in aggregate
        ]
        offsets = [position + (index - (len(PHASES) - 1) / 2) * width for position in positions]
        bars = axis.bar(offsets, values, width, label=label)
        axis.bar_label(bars, fmt="%.2f", padding=2, fontsize=7)
    axis.set_xticks(positions, [str(level) for level in levels])
    axis.set_xlabel("Patients processed concurrently")
    axis.set_ylabel("Mean phase duration (s)")
    axis.set_title("Mean time spent in each workflow phase")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    axis.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "01_mean_phase_times.png", dpi=250)
    plt.close(fig)
    return True


def print_aggregate_table(aggregate: list[dict]) -> None:
    print("\nMean phase duration by concurrency (seconds)")
    for row in aggregate:
        means = ", ".join(
            f"{label}={row[f'mean_{phase}'] or 'n/a'}"
            for phase, label in PHASES.items()
        )
        print(
            f"{row['concurrency']} concurrent patients: {means}; "
            f"decisions={row['successes']}/{row['requested']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007"))
    parser.add_argument("--clients", "--concurrency", dest="clients", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--use-rag", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.repetitions < 1 or any(count < 1 for count in args.clients):
        parser.error("client counts and repetitions must be positive")

    patient_ids = load_patient_ids()
    if max(args.clients) > len(patient_ids):
        parser.error(f"client count cannot exceed the {len(patient_ids)} available patients")
    try:
        requests.get(f"{args.url.rstrip('/')}/docs", timeout=3).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Coordinator unavailable at {args.url}: {exc}") from exc

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_summaries = []
    request_rows = []
    patient_cursor = 0
    print("Benchmarking the complete doctor request-to-decision workflow.")
    print(f"URL: {args.url}; RAG={args.use_rag}; repetitions={args.repetitions}")

    for concurrency in args.clients:
        for repeat in range(1, args.repetitions + 1):
            selected = [
                patient_ids[(patient_cursor + offset) % len(patient_ids)]
                for offset in range(concurrency)
            ]
            patient_cursor = (patient_cursor + concurrency) % len(patient_ids)
            print(f"\nRun {repeat:02d}/{args.repetitions} | clients={concurrency} | patients={selected}")
            batch_summary, request_results = run_batch(
                url=args.url,
                patient_ids=selected,
                concurrency=concurrency,
                repeat_number=repeat,
                timeout=args.timeout,
                use_rag=args.use_rag,
            )
            batch_summaries.append(batch_summary)
            for row in request_results:
                request_rows.append({
                    "concurrency": concurrency,
                    "repeat": repeat,
                    "use_rag": args.use_rag,
                    **row,
                })
            print(f"Success     : {batch_summary['successes']}/{concurrency}")
            for failure in (row for row in request_results if not row["success"]):
                print(f"[FAILED] patient={failure['patient_id']} | {failure['error']}")

    aggregate = aggregate_results(batch_summaries, request_rows)
    save_csv(OUTPUT_DIR / "scalability_batches.csv", batch_summaries)
    save_csv(OUTPUT_DIR / "scalability_requests.csv", request_rows)
    save_csv(OUTPUT_DIR / "scalability_summary.csv", aggregate)
    if not any(row[f"mean_{phase}"] != "" for row in aggregate for phase in PHASES):
        raise SystemExit(
            "The coordinator returned no phase timings. Restart it with CDSS_EVAL=1, "
            "then rerun this benchmark."
        )
    plot_created = make_plot(aggregate)
    print_aggregate_table(aggregate)
    print("\nGenerated files:")
    print(f"  {OUTPUT_DIR / 'scalability_batches.csv'}")
    print(f"  {OUTPUT_DIR / 'scalability_requests.csv'}")
    print(f"  {OUTPUT_DIR / 'scalability_summary.csv'}")
    if plot_created:
        print(f"  {OUTPUT_DIR / '01_mean_phase_times.png'}")
    print("\nBenchmark finished.")


if __name__ == "__main__":
    main()
