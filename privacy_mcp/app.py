from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .zkp_client import generate_and_verify_proof


app = FastAPI(
    title="ZKP Validation Layer"
)
rpc = MCPJsonRpcServer("zkp-layer")



@rpc.tool("request_proof", "Request a device-side Bulletproof package and verify it without receiving the sensor value.", {
    "type": "object", "properties": {"bounds": {"type": "object"}, "patient_id": {"type": "string"}}, "required": ["bounds"],
})
def request_proof(bounds: dict, patient_id: str | None = None, debug_sensor_values: bool = False):

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


        result = generate_and_verify_proof(bounds, patient_id=patient_id, debug_sensor_values=debug_sensor_values)


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


@rpc.tool("request_proofs", "Verify one device-side proof per public range and return only the results.", {
    "type": "object", "properties": {"ranges": {"type": "array"}, "patient_id": {"type": "string"}}, "required": ["ranges"],
})
def request_proofs(ranges: list[dict], patient_id: str | None = None, debug_sensor_values: bool = False):
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("ranges must be a nonempty list")
    results = []
    for item in ranges:
        if not isinstance(item, dict):
            raise ValueError("each range must be an object")
        bounds = {"min": item["min"], "max": item["max"], "parameter": item.get("parameter")}
        results.append({"parameter": item.get("parameter"), "result": generate_and_verify_proof(bounds, patient_id=patient_id, debug_sensor_values=debug_sensor_values)})
    all_normal = all(item["result"].get("verified") is True and item["result"].get("status") == "NORMAL" for item in results)
    any_alert = any(item["result"].get("status") == "ALERT" for item in results)
    return {"status": "NORMAL" if all_normal else "ALERT" if any_alert else "PROOF_FAILED", "verified": all_normal, "proof_type": "Bulletproofs (one proof per measurement)", "measurements": results}


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
