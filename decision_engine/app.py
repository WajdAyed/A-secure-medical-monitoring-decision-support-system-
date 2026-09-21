import os

from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer, call_tool

from .engine import evaluate


PRIVACY_MCP_URL = os.getenv("ZKP_MCP_URL", os.getenv("PRIVACY_MCP_URL", "http://127.0.0.1:8003"))

app = FastAPI(
    title="Decision Agent"
)
rpc = MCPJsonRpcServer("decision-agent")


@rpc.tool("validate_safe_range", "Send the Ruler-generated safe range to the ZKP layer and return its privacy-preserving validation result.", {
    "type": "object", "properties": {"bounds": {"type": "object"}, "patient_id": {"type": "string"}}, "required": ["bounds"],
})
def validate_safe_range(bounds: dict, patient_id: str | None = None):
    """Route bounds to ZKP; raw sensor values never enter the Decision Agent."""
    print("\n" + "=" * 70)
    print("DECISION AGENT - ZKP ROUTING")
    print("=" * 70)
    print("Forwarding only safe-range bounds to the ZKP layer.")
    arguments = {"bounds": bounds}
    if patient_id is not None:
        arguments["patient_id"] = patient_id
    return call_tool(PRIVACY_MCP_URL, "request_proof", arguments, timeout=120)


@rpc.tool("validate_safe_ranges", "Validate multiple independent private sensor ranges; no raw values leave the ZKP layer.", {
    "type": "object", "properties": {"ranges": {"type": "array"}, "patient_id": {"type": "string"}}, "required": ["ranges"],
})
def validate_safe_ranges(ranges: list[dict], patient_id: str | None = None):
    """One Bulletproof range proof per measurement, aggregated only as statuses."""
    results = []
    for item in ranges:
        arguments = {"bounds": {"min": item["min"], "max": item["max"]}, "patient_id": patient_id}
        results.append({"parameter": item.get("parameter"), "result": call_tool(PRIVACY_MCP_URL, "request_proof", arguments, timeout=120)})
    all_normal = all(item["result"].get("status") == "NORMAL" for item in results)
    return {"status": "NORMAL" if all_normal else "ALERT", "verified": all_normal, "proof_type": "Bulletproofs (one proof per measurement)", "measurements": results}



@rpc.tool("evaluate_decision", "Evaluate the ZKP-attested range status and return the final patient status without receiving raw sensor data.", {
    "type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"],
})
def decision(status: str):


    print("\n" + "=" * 70)
    print("DECISION AGENT - FINAL STATUS")
    print("=" * 70)



    print("\nDecision request received")


    print("Proof status:")

    print(
        status
    )



    print("\nPrivacy check:")

    print(
        "✓ No sensor value received"
    )

    print(
        "✓ Decision based only on ZKP result"
    )



    print("\nEvaluating clinical status...")



    try:


        result = evaluate(
            status
        )


    except Exception as e:


        print("\n❌ DECISION ENGINE ERROR")

        print(e)


        return {
            "error": str(e)
        }



    print("\n✅ Clinical decision generated")


    print(result)



    print("=" * 70)



    return result


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
