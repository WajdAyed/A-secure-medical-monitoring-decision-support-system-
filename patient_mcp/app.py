from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .database import get_patient_by_id

app = FastAPI(
    title="EMR Layer"
)
rpc = MCPJsonRpcServer("emr-layer")


@rpc.tool("get_patient", "Retrieve and check the minimum EMR record required for clinical range generation.", {
    "type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"],
})
def get_patient(patient_id: str):

    print("\n" + "=" * 70)
    print("EMR LAYER")
    print("=" * 70)

    print("EMR record request received:")
    print("EMR record ID:", patient_id)


    print("\nSearching EMR records...")

    patient = get_patient_by_id(patient_id)


    if patient is None:

        print("\n❌ Patient not found")

        print("=" * 70)

        return {
            "error": "patient not found"
        }


    print("\n✅ Patient found")

    print("Minimum EMR context:")
    print(patient)

    print("=" * 70)


    return patient


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
