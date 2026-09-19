from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .database import get_patient_by_id

app = FastAPI(
    title="Patient MCP"
)
rpc = MCPJsonRpcServer("patient-mcp")


@rpc.tool("get_patient", "Retrieve the minimum patient profile for a patient ID.", {
    "type": "object", "properties": {"patient_id": {"type": "string"}}, "required": ["patient_id"],
})
def get_patient(patient_id: str):

    print("\n" + "=" * 70)
    print("PATIENT MCP")
    print("=" * 70)

    print("Patient request received:")
    print("Patient ID:", patient_id)


    print("\nSearching patient database...")

    patient = get_patient_by_id(patient_id)


    if patient is None:

        print("\n❌ Patient not found")

        print("=" * 70)

        return {
            "error": "patient not found"
        }


    print("\n✅ Patient found")

    print("Patient information:")
    print(patient)

    print("=" * 70)


    return patient


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
