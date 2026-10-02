import requests
import time
import threading
import itertools
import re
import os
import json
from pathlib import Path


LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://127.0.0.1:8007")
LANGGRAPH_TIMEOUT = float(os.getenv("LANGGRAPH_TIMEOUT", "90"))
DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "clean" / "patients_200.json"


# Timings include automated work only; time spent waiting for doctor input is not
# part of the total process time.
ACTION_TIMES = []


def record_action(action, start_time):
    """Record and return an action's elapsed time in seconds."""
    elapsed = time.perf_counter() - start_time
    ACTION_TIMES.append((action, elapsed))
    return elapsed


def print_timing_summary():
    """Display all recorded timings and their active processing total."""
    if not ACTION_TIMES:
        return

    total_time = sum(elapsed for _, elapsed in ACTION_TIMES)

    print("\n====================================================")
    print(" PROCESS TIMING")
    print("====================================================")
    for action, elapsed in ACTION_TIMES:
        print(f"{action}: {elapsed:.3f} seconds")
    print("----------------------------------------------------")
    print(f"Total process time: {total_time:.3f} seconds")
    print("====================================================")


# ====================================================
# Spinner
# ====================================================

def spinner(message, stop_event):

    for c in itertools.cycle(["|", "/", "-", "\\"]):

        if stop_event.is_set():
            break

        print(
            f"\r[{c}] {message}",
            end="",
            flush=True
        )

        time.sleep(0.1)

    print("\r", end="")


def process_stage(message, duration=1.2):

    start_time = time.perf_counter()

    stop = threading.Event()

    t = threading.Thread(
        target=spinner,
        args=(message, stop)
    )

    t.start()

    time.sleep(duration)

    stop.set()
    t.join()

    record_action(message, start_time)

    print(f"[OK] {message}")


# ====================================================
# Get Patients
# ====================================================

def get_patients():

    start_time = time.perf_counter()

    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Patient dataset not found: {DATASET_PATH}")

    patients_data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    patients = [
        str(identifier.get("value", "")).strip()
        for patient in patients_data
        for identifier in patient.get("identifier", [])
        if str(identifier.get("value", "")).strip()
    ]

    if len(patients) != len(set(patients)):
        raise ValueError(f"Duplicate patient identifiers found in {DATASET_PATH}")

    record_action("Loading available patients", start_time)
    return patients


# ====================================================
# Main
# ====================================================

def main():

    ACTION_TIMES.clear()

    os.system(
        "cls" if os.name == "nt"
        else "clear"
    )

    print("""
====================================================
 Privacy Preserving CDSS - Doctor Console
====================================================
""")

    process_stage(
        "Connecting to hospital system..."
    )

    patients = get_patients()

    print("\nAvailable Patients:")
    print("-----------------------------")

    for p in patients:
        print("-", p)

    print("-----------------------------")

    try:
        query = input(
            "\nDoctor query:\n> "
        )
    except EOFError:
        print("\nNo query entered.")
        return

    # extract patient id
    patient_id_start_time = time.perf_counter()
    match = re.search(
        r"\d+",
        query
    )
    record_action("Extracting patient ID", patient_id_start_time)

    if not match:

        print(
            "\nNo patient ID detected."
        )

        return

    patient_id = match.group()

    if patient_id not in patients:
        print(f"\nPatient ID {patient_id} is not in the available patient list.")
        return

    print()

    # ====================================================
    # Visual pipeline
    # ====================================================

    process_stage(
        "Checking EMR record..."
    )

    process_stage(
        "Ruler Agent: searching ChromaDB guideline knowledge..."
    )

    process_stage(
        "Ruler Agent: generating personalized clinical ranges..."
    )

    process_stage(
        "Coordinator: sending safe range to ZKP layer..."
    )

    process_stage(
        "ZKP layer: generating Zero-Knowledge Proof..."
    )

    process_stage(
        "ZKP layer: validating Bulletproof proof..."
    )

    process_stage(
        "Coordinator: summarizing proof result..."
    )

# ====================================================
# Call LangGraph
# ====================================================

    try:

        print("\n[DEBUG] Sending request to LangGraph...")
        print(
            f"[DEBUG] URL: "
            f"{LANGGRAPH_URL}/rpc (tools/call: run_cdss)"
        )

        request_start_time = time.perf_counter()
        try:
            response = requests.post(
                f"{LANGGRAPH_URL}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "id": "doctor-console",
                    "method": "tools/call",
                    "params": {"name": "run_cdss", "arguments": {"patient_id": patient_id, "debug_sensor_values": True}},
                },
                timeout=LANGGRAPH_TIMEOUT,
            )
        finally:
            record_action("LangGraph request", request_start_time)

        print("\n==============================")
        print("LANGGRAPH RESPONSE")
        print("==============================")

        print("Status Code:")
        print(response.status_code)

        print("\nHeaders:")
        print(response.headers)

        print("\nRaw Content:")
        print(response.text)

        if response.status_code != 200:

            print("\n[ERROR] LANGGRAPH FAILED")

            print(
                "\nGo check these terminals:"
            )

            print(
                "1) LangGraph Coordinator :8007"
            )

            print(
                "2) EMR Layer :8005"
            )

            print(
                "3) Ruler Agent :8004"
            )

            print(
                "4) Knowledge MCP :8010"
            )

            print(
                "5) ZKP Layer :8003"
            )

            return

        try:

            response_parse_start_time = time.perf_counter()
            rpc_response = response.json()
            result = rpc_response["result"]["structuredContent"]
            record_action(
                "Parsing LangGraph response",
                response_parse_start_time
            )

            if rpc_response.get("result", {}).get("isError") or "error" in result:
                print("\n[ERROR] LANGGRAPH TOOL FAILED")
                print(result.get("error", "The coordinator returned an error."))
                return

        except Exception as json_error:

            record_action(
                "Parsing LangGraph response",
                response_parse_start_time
            )

            print(
                "\n[ERROR] JSON PARSE ERROR"
            )

            print(
                "Exception:"
            )

            print(json_error)

            print(
                "\nResponse text:"
            )

            print(response.text)

            return

    except requests.exceptions.ConnectionError as e:

        print(
            "\n[ERROR] CONNECTION ERROR"
        )

        print(e)

        print(
            "\nLangGraph service may not be running."
        )

        return


    except requests.exceptions.Timeout as e:

        print(
            "\n[ERROR] REQUEST TIMEOUT"
        )

        print(e)

        return


    except Exception as e:

        print(
            "\n[ERROR] UNKNOWN ERROR"
        )

        print(type(e))

        print(e)

        return
    # ====================================================
    # Final Report
    # ====================================================

    report_start_time = time.perf_counter()

    patient = result.get(
        "patient",
        {}
    )

    policy = result.get(
        "policy",
        {}
    )

    proof = result.get(
        "proof",
        {}
    )

    decision = result.get(
        "decision",
        {}
    )

    print("""

====================================================
 CLINICAL DECISION REPORT
====================================================
""")

    print(
        "Patient ID:",
        result.get("patient_id")
    )

    print(
        "Gender:",
        patient.get("gender")
    )

    print(
        "Age:",
        patient.get("age")
    )

    print(
        "Condition:",
        patient.get("condition")
    )

    print("\nPersonalized Range(s):")
    policies = policy.get("policies") if isinstance(policy, dict) else None
    if policies:
        for item in policies:
            print(f"- {item.get('min')} - {item.get('max')} {item.get('parameter', '')}")
    else:
        print(f"{policy.get('min')} - {policy.get('max')} {policy.get('parameter', '')}")

    measurements = proof.get("measurements") if isinstance(proof, dict) else None
    debug_value = proof.get("sensor_value_for_debug") if isinstance(proof, dict) else None
    if debug_value is None and measurements:
        debug_values = [
            item.get("result", {}).get("sensor_value_for_debug")
            for item in measurements
            if isinstance(item, dict) and isinstance(item.get("result"), dict)
        ]
        debug_values = [value for value in debug_values if value is not None]
        if debug_values:
            debug_value = ", ".join(str(value) for value in debug_values)
    if debug_value is None:
        print("\nSensor Value: hidden on device")
    else:
        print(f"\nSensor Value [DEBUG ONLY]: {debug_value}")

    print("\nZKP Range-Proof Result:")
    if measurements:
        for measurement in measurements:
            item = measurement.get("result", {})
            print(
                f"- {measurement.get('parameter', 'measurement')}: "
                f"{item.get('status', 'UNKNOWN')} "
                f"({'VALID' if item.get('verified') else 'NOT VALID'})"
            )
    elif proof.get("status") == "NORMAL" and proof.get("verified"):
        print("VALID  The ZKP attests range membership.")
    elif proof.get("status") == "ALERT":
        print("OUT OF RANGE  The ZKP did not attest membership.")
    else:
        print("PROOF FAILED  No clinical-safe result is issued.")

    print("\nFinal Range Assessment:")
    status = decision.get("status", "UNABLE_TO_ASSESS")
    print(f"{status}: {decision.get('message', 'No assessment available.')}")

    print("""
====================================================
""")

    record_action("Generating clinical decision report", report_start_time)


if __name__ == "__main__":
    try:
        main()
    finally:
        print_timing_summary()
