import os
from time import perf_counter
from typing import TypedDict
from cdss_rpc import call_tool
from rule_engine.policy_generator import normalize_policy

# Legacy variable names remain accepted for deployed clients.
EMR_MCP_URL = os.getenv("EMR_MCP_URL", os.getenv("PATIENT_MCP_URL", "http://127.0.0.1:8005"))
RULER_AGENT_URL = os.getenv("RULER_AGENT_URL", os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
DECISION_AGENT_URL = os.getenv("DECISION_AGENT_URL", os.getenv("DECISION_ENGINE_URL", "http://127.0.0.1:8002"))


class State(TypedDict):

    patient_id: str
    patient: dict
    policy: dict
    proof: dict
    decision: dict
    use_rag: bool
    timings: dict


def _eval_enabled():
    return os.getenv("CDSS_EVAL") == "1"


def _finish_timing(state, key, started, value):
    """Attach an already measured node duration only during evaluation."""
    if not _eval_enabled():
        return value
    timings = dict(state.get("timings", {}))
    timings[f"{key}_ms"] = (perf_counter() - started) * 1000
    value["timings"] = timings
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
    policy = call_tool(RULER_AGENT_URL, "generate_policy", {"patient": state["patient"], "use_rag": use_rag}, timeout=120)

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
    print("DECISION AGENT -> ZKP VALIDATION NODE")
    print("=" * 70)



    bounds = {

        "min": normalize_policy(state["policy"])["min"],

        "max": normalize_policy(state["policy"])["max"]

    }



    print("Sending ONLY bounds to the Decision Agent for ZKP validation:")

    print(bounds)



    print(
        "Sensor value is NOT included 🔒"
    )



    # The Decision Agent owns range-to-ZKP routing; the coordinator sends no sensor data.
    proof = call_tool(DECISION_AGENT_URL, "validate_safe_range", {"bounds": bounds, "patient_id": state["patient_id"]}, timeout=120)



    print("\nProof received:")

    print(proof)



    return _finish_timing(state, "proof", started, {"proof": proof})





def complete_clinical_decision(state):

    started = perf_counter()


    print("\n")
    print("=" * 70)
    print("DECISION AGENT FINAL STATUS NODE")
    print("=" * 70)



    print("Sending proof status:")

    print(
        state["proof"]["status"]
    )



    decision = call_tool(DECISION_AGENT_URL, "evaluate_decision", {"status": state["proof"]["status"]}, timeout=10)



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
