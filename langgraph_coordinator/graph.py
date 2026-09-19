import os
from typing import TypedDict
from cdss_rpc import call_tool

PATIENT_MCP_URL = os.getenv("PATIENT_MCP_URL", "http://127.0.0.1:8005")
RULE_ENGINE_URL = os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004")
PRIVACY_MCP_URL = os.getenv("PRIVACY_MCP_URL", "http://127.0.0.1:8003")
DECISION_ENGINE_URL = os.getenv("DECISION_ENGINE_URL", "http://127.0.0.1:8002")


class State(TypedDict):

    patient_id: str
    patient: dict
    policy: dict
    proof: dict
    decision: dict




def get_patient(state):


    print("\n")
    print("=" * 70)
    print("PATIENT NODE")
    print("=" * 70)



    print("Requesting patient data from Patient MCP")


    print("JSON-RPC endpoint:")
    print(f"{PATIENT_MCP_URL}/rpc")
    patient = call_tool(PATIENT_MCP_URL, "get_patient", {"patient_id": state["patient_id"]}, timeout=10)



    print("\nPatient received:")

    print(patient)



    return {

        "patient": patient

    }




def get_policy(state):


    print("\n")
    print("=" * 70)
    print("POLICY NODE")
    print("=" * 70)



    print("Sending patient to Rule Engine")


    print(state["patient"])



    policy = call_tool(RULE_ENGINE_URL, "generate_policy", {"patient": state["patient"]}, timeout=60)



    print("\nPersonalized policy received:")

    print(policy)



    return {

        "policy": policy

    }





def get_proof(state):


    print("\n")
    print("=" * 70)
    print("PROOF NODE")
    print("=" * 70)



    bounds = {

        "min": state["policy"]["min"],

        "max": state["policy"]["max"]

    }



    print("Sending ONLY bounds to Privacy MCP:")

    print(bounds)



    print(
        "Sensor value is NOT included 🔒"
    )



    proof = call_tool(PRIVACY_MCP_URL, "request_proof", {"bounds": bounds}, timeout=30)



    print("\nProof received:")

    print(proof)



    return {

        "proof": proof

    }





def get_decision(state):


    print("\n")
    print("=" * 70)
    print("DECISION NODE")
    print("=" * 70)



    print("Sending proof status:")

    print(
        state["proof"]["status"]
    )



    decision = call_tool(DECISION_ENGINE_URL, "evaluate_decision", {"status": state["proof"]["status"]}, timeout=10)



    print("\nDecision received:")

    print(decision)



    return {

        "decision": decision

    }
