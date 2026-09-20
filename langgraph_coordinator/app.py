import os
from fastapi import FastAPI, Request
from langgraph.graph import StateGraph, END
from cdss_rpc import MCPJsonRpcServer

from .graph import (
    State,
    retrieve_emr_record,
    generate_safe_range,
    submit_range_for_zkp_validation,
    complete_clinical_decision
)


app = FastAPI(
    title="Clinical Workflow Coordinator"
)
rpc = MCPJsonRpcServer("clinical-workflow-coordinator")



print("\n" + "=" * 70)
print("INITIALIZING LANGGRAPH COORDINATOR")
print("=" * 70)


builder = StateGraph(State)


builder.add_node(
    "emr_record_retrieval",
    retrieve_emr_record
)

builder.add_node(
    "ruler_range_generation",
    generate_safe_range
)

builder.add_node(
    "decision_zkp_validation",
    submit_range_for_zkp_validation
)

builder.add_node(
    "decision_final_status",
    complete_clinical_decision
)



builder.set_entry_point(
    "emr_record_retrieval"
)


builder.add_edge(
    "emr_record_retrieval",
    "ruler_range_generation"
)

builder.add_edge(
    "ruler_range_generation",
    "decision_zkp_validation"
)

builder.add_edge(
    "decision_zkp_validation",
    "decision_final_status"
)

builder.add_edge(
    "decision_final_status",
    END
)



graph = builder.compile()


print("✅ LangGraph workflow ready")

print(
"""
EMR record retrieval
   ↓
Ruler Agent safe-range generation
   ↓
Decision Agent -> ZKP validation
   ↓
Decision Agent final patient status
"""
)

print("=" * 70)




@rpc.tool("run_cdss", "Coordinate EMR retrieval, Ruler safe-range generation, ZKP validation, and final patient status.", {
    "type": "object", "properties": {"patient_id": {"type": "string"}, "use_rag": {"type": "boolean"}}, "required": ["patient_id"],
})
def run(patient_id: str, use_rag: bool = True):


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
        ,"use_rag": use_rag
        ,"timings": {}
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



        # Timings are evaluation-only metadata; production responses preserve
        # their original clinical wire fields.
        if os.getenv("CDSS_EVAL") != "1":
            result.pop("timings", None)
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
