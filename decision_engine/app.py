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
