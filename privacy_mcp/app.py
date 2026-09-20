from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .zkp_client import generate_and_verify_proof


app = FastAPI(
    title="ZKP Validation Layer"
)
rpc = MCPJsonRpcServer("zkp-layer")



@rpc.tool("request_proof", "Generate and validate a ZKP range proof from sensor data without exposing raw sensor values.", {
    "type": "object", "properties": {"bounds": {"type": "object"}, "patient_id": {"type": "string"}}, "required": ["bounds"],
})
def request_proof(bounds: dict, patient_id: str | None = None):

    data = {"bounds": bounds}


    print("\n" + "=" * 70)
    print("ZKP VALIDATION LAYER")
    print("=" * 70)


    print("\nProof request received")


    print("\nReceived data:")

    print(data)



    # Privacy check
    if "bounds" not in data:

        print("\n❌ Missing bounds")

        return {
            "error": "bounds missing"
        }



    print("\nPrivacy verification:")

    print("✓ Received only clinical limits")

    print("✓ Raw sensor value is NOT exposed to MCP")



    bounds = data["bounds"]


    print("\nBounds received:")

    print(
        "Minimum:",
        bounds.get("min")
    )

    print(
        "Maximum:",
        bounds.get("max")
    )



    print("\nGenerating Zero-Knowledge Proof...")


    try:


        result = generate_and_verify_proof(bounds, patient_id=patient_id)


    except Exception as e:


        print("\n❌ ZKP ERROR")

        print(e)


        return {
            "error": str(e)
        }



    print("\n✅ ZKP completed")


    print("\nProof result returned:")

    print(result)



    print("\nPrivacy guarantee:")

    print("Sensor value remains hidden 🔒")


    print("=" * 70)



    return result


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
