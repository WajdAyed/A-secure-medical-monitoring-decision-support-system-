from fastapi import FastAPI, Request
from langgraph.graph import StateGraph, END
from cdss_rpc import MCPJsonRpcServer

from .graph import (
    State,
    get_patient,
    get_policy,
    get_proof,
    get_decision
)


app = FastAPI(
    title="LangGraph Coordinator"
)
rpc = MCPJsonRpcServer("langgraph-coordinator")



print("\n" + "=" * 70)
print("INITIALIZING LANGGRAPH COORDINATOR")
print("=" * 70)


builder = StateGraph(State)


builder.add_node(
    "patient",
    get_patient
)

builder.add_node(
    "policy",
    get_policy
)

builder.add_node(
    "proof",
    get_proof
)

builder.add_node(
    "decision",
    get_decision
)



builder.set_entry_point(
    "patient"
)


builder.add_edge(
    "patient",
    "policy"
)

builder.add_edge(
    "policy",
    "proof"
)

builder.add_edge(
    "proof",
    "decision"
)

builder.add_edge(
    "decision",
    END
)



graph = builder.compile()


print("✅ LangGraph workflow ready")

print(
"""
patient
   ↓
policy
   ↓
proof
   ↓
decision
"""
)

print("=" * 70)




@rpc.tool("run_cdss", "Run the privacy-preserving CDSS workflow for a patient.", {
    "type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"],
})
def run(patient_id: str):


    print("\n" + "=" * 70)
    print("LANGGRAPH EXECUTION START")
    print("=" * 70)


    print("Patient requested:")
    print(patient_id)



    initial_state: State = {

        "patient_id": patient_id,

        "patient": {},

        "policy": {},

        "proof": {},

        "decision": {}

    }


    try:


        result = graph.invoke(
            initial_state
        )


        print("\n" + "=" * 70)
        print("LANGGRAPH EXECUTION COMPLETE")
        print("=" * 70)


        print("Final state:")
        print(result)


        print("=" * 70)



        return result



    except Exception as e:


        import traceback


        print("\n" + "=" * 70)

        print("❌ LANGGRAPH ERROR")

        print("=" * 70)


        traceback.print_exc()


        return {

            "error": str(e)

        }


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
