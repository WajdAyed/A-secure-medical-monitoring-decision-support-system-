from typing import TypedDict
import requests



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


    url = (
        f"http://127.0.0.1:8005/patient/{state['patient_id']}"
    )


    print("URL:")
    print(url)



    response = requests.get(
        url,
        timeout=10
    )


    patient = response.json()



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



    response = requests.post(

        "http://127.0.0.1:8004/policy",

        json=state["patient"],

        timeout=60

    )



    policy = response.json()



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



    response = requests.post(

        "http://127.0.0.1:8003/request-proof",

        json={

            "bounds": bounds

        },

        timeout=30

    )



    proof = response.json()



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



    response = requests.post(

        "http://127.0.0.1:8002/decision",

        json={

            "status": state["proof"]["status"]

        },

        timeout=10

    )



    decision = response.json()



    print("\nDecision received:")

    print(decision)



    return {

        "decision": decision

    }