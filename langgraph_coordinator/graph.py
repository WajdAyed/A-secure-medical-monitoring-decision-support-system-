import os
from time import perf_counter
from typing import TypedDict
from cdss_rpc import call_tool
from rule_engine.policy_generator import normalize_policy

# Legacy variable names remain accepted for deployed clients.
EMR_MCP_URL = os.getenv("EMR_MCP_URL", os.getenv("PATIENT_MCP_URL", "http://127.0.0.1:8005"))
RULER_AGENT_URL = os.getenv("RULER_AGENT_URL", os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
PRIVACY_MCP_URL = os.getenv("ZKP_MCP_URL", os.getenv("PRIVACY_MCP_URL", "http://127.0.0.1:8003"))
EVALUATION_OBSERVER = None


class State(TypedDict):

    patient_id: str
    patient: dict
    policy: dict
    proof: dict
    decision: dict
    use_rag: bool
    timings: dict
    debug_sensor_values: bool


def _eval_enabled():
    return os.getenv("CDSS_EVAL") == "1"


def _finish_timing(state, key, started, value):
    """Attach an already measured node duration only during evaluation."""
    if not _eval_enabled():
        return value
    timings = dict(state.get("timings", {}))
    timings[f"{key}_ms"] = (perf_counter() - started) * 1000
    value["timings"] = timings
    if EVALUATION_OBSERVER is not None:
        EVALUATION_OBSERVER(key, value)
    return value




def retrieve_emr_record(state):

    started = perf_counter()


    print("\n")
    print("=" * 70)
    print("EMR PATIENT RETRIEVAL NODE")
    print("=" * 70)



    print("Requesting the minimum EMR record from the single EMR layer")


    print("JSON-RPC endpoint:")
    print(f"{EMR_MCP_URL}/rpc")
    patient = call_tool(EMR_MCP_URL, "get_patient", {"patient_id": state["patient_id"]}, timeout=10)



    print("\nPatient received:")

    print(patient)



    return _finish_timing(state, "patient", started, {"patient": patient})




def generate_safe_range(state):

    started = perf_counter()


    print("\n")
    print("=" * 70)
    print("RULER AGENT SAFE-RANGE GENERATION NODE")
    print("=" * 70)



    print("Sending EMR context to the Ruler Agent")


    print(state["patient"])



    requested_rag = state.get("use_rag", True)
    env_rag = os.getenv("CDSS_RAG")
    use_rag = requested_rag if env_rag not in {"0", "1"} else env_rag == "1"
    demo_conditions = os.getenv("CDSS_DEMO_CONDITIONS", "")
    if demo_conditions.strip():
        conditions = [item.strip() for item in demo_conditions.split(",") if item.strip()]
    else:
        conditions = state["patient"].get("conditions") or [state["patient"]["condition"]]
    if len(conditions) > 1:
        policies = []
        for condition in conditions:
            context = dict(state["patient"], condition=condition)
            policies.append(normalize_policy(call_tool(RULER_AGENT_URL, "generate_policy", {"patient": context, "use_rag": use_rag}, timeout=120)))
        policy = {"policies": policies}
    else:
        policy = call_tool(RULER_AGENT_URL, "generate_policy", {"patient": state["patient"], "use_rag": use_rag}, timeout=120)

    if "policies" not in policy:
        try:
            policy = normalize_policy(policy)
        except Exception as exc:
            raise ValueError(f"Invalid policy contract from Ruler Agent: {policy!r}") from exc



    print("\nPersonalized safe clinical range received:")

    print(policy)



    return _finish_timing(state, "policy", started, {"policy": policy})





def submit_range_for_zkp_validation(state):

    started = perf_counter()


    print("\n")
    print("=" * 70)
    print("COORDINATOR -> ZKP VALIDATION NODE")
    print("=" * 70)



    if "policies" in state["policy"]:
        ranges = [{"parameter": normalize_policy(p).get("parameter"), "min": normalize_policy(p)["min"], "max": normalize_policy(p)["max"]} for p in state["policy"]["policies"]]
        proof = call_tool(PRIVACY_MCP_URL, "request_proofs", {"ranges": ranges, "patient_id": state["patient_id"], "debug_sensor_values": state.get("debug_sensor_values", False)}, timeout=120)
        return _finish_timing(state, "proof", started, {"proof": proof})

    bounds = {

        "min": normalize_policy(state["policy"])["min"],

        "max": normalize_policy(state["policy"])["max"],

        "parameter": normalize_policy(state["policy"]).get("parameter", "systolic_bp")

    }



    print("Sending public bounds to the hospital ZKP verifier:")

    print(bounds)



    print(
        "Sensor value is NOT included 🔒"
    )



    proof = call_tool(PRIVACY_MCP_URL, "request_proof", {"bounds": bounds, "patient_id": state["patient_id"], "debug_sensor_values": state.get("debug_sensor_values", False)}, timeout=120)



    print("\nProof received:")

    print(proof)



    return _finish_timing(state, "proof", started, {"proof": proof})





def summarize_proof(proof: dict) -> dict:
    """Map verifier results to a report without claiming overall clinical stability."""
    if not isinstance(proof, dict):
        proof = {}
    measurements = proof.get("measurements")
    if measurements is not None:
        if not isinstance(measurements, list) or not measurements:
            results = [{}]
        else:
            results = [item.get("result", {}) if isinstance(item, dict) else {} for item in measurements]
    else:
        results = [proof]

    if all(isinstance(item, dict) and item.get("status") == "NORMAL" and item.get("verified") is True for item in results):
        return {"status": "IN_RANGE", "message": "Verified reading(s) are within the selected range(s)."}
    if any(not isinstance(item, dict) or item.get("status") not in ("NORMAL", "ALERT") or (item.get("status") == "NORMAL" and item.get("verified") is not True) for item in results):
        return {"status": "UNABLE_TO_ASSESS", "message": "A proof failed or is missing. Check the device or connection before assessing the reading."}
    return {"status": "OUT_OF_RANGE", "message": "Device reported a reading outside the selected range; clinical review is needed."}


def complete_clinical_decision(state):

    started = perf_counter()


    print("\n")
    print("=" * 70)
    print("COORDINATOR FINAL STATUS NODE")
    print("=" * 70)



    print("Sending proof status:")

    print(
        state["proof"].get("status", "MISSING")
    )



    decision = summarize_proof(state["proof"])



    print("\nDecision received:")

    print(decision)



    result = _finish_timing(state, "decision", started, {"decision": decision})
    if _eval_enabled():
        timings = result["timings"]
        timings["total_ms"] = sum(timings.get(f"{stage}_ms", 0.0) for stage in ("patient", "policy", "proof", "decision"))
    return result


# Compatibility aliases for code that imported the original coordinator nodes.
get_patient = retrieve_emr_record
get_policy = generate_safe_range
get_proof = submit_range_for_zkp_validation
get_decision = complete_clinical_decision
