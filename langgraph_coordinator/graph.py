import os
from typing import TypedDict
from cdss_rpc import call_tool

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




def retrieve_emr_record(state):


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



    return {

        "patient": patient

    }




def generate_safe_range(state):


    print("\n")
    print("=" * 70)
    print("RULER AGENT SAFE-RANGE GENERATION NODE")
    print("=" * 70)



    print("Sending EMR context to the Ruler Agent")


    print(state["patient"])



    policy = call_tool(RULER_AGENT_URL, "generate_policy", {"patient": state["patient"]}, timeout=60)



    print("\nPersonalized safe clinical range received:")

    print(policy)



    return {

        "policy": policy

    }





def submit_range_for_zkp_validation(state):


    print("\n")
    print("=" * 70)
    print("DECISION AGENT -> ZKP VALIDATION NODE")
    print("=" * 70)



    bounds = {

        "min": state["policy"]["min"],

        "max": state["policy"]["max"]

    }



    print("Sending ONLY bounds to the Decision Agent for ZKP validation:")

    print(bounds)



    print(
        "Sensor value is NOT included 🔒"
    )



    # The Decision Agent owns range-to-ZKP routing; the coordinator sends no sensor data.
    proof = call_tool(DECISION_AGENT_URL, "validate_safe_range", {"bounds": bounds}, timeout=30)



    print("\nProof received:")

    print(proof)



    return {

        "proof": proof

    }





def complete_clinical_decision(state):


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



    return {

        "decision": decision

    }


# Compatibility aliases for code that imported the original coordinator nodes.
get_patient = retrieve_emr_record
get_policy = generate_safe_range
get_proof = submit_range_for_zkp_validation
get_decision = complete_clinical_decision
