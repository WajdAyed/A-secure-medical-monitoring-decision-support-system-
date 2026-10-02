"""Device-side proof endpoint. The sensor reading never enters an RPC response."""
import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from cdss_rpc import MCPJsonRpcServer
from .sensor import evaluation_sensor_value, read_measurement

app = FastAPI(title="Device proof agent")
rpc = MCPJsonRpcServer("device-agent")
ENGINE = Path(os.getenv("ZKP_ENGINE_PATH", Path(__file__).resolve().parent.parent / "zkp_engine" / "target" / "release" / ("zkp_engine.exe" if os.name == "nt" else "zkp_engine")))


@rpc.tool("prove", "Read a local sensor value and return a bound range proof or ALERT.", {
    "type": "object", "properties": {"min": {"type": "integer"}, "max": {"type": "integer"}, "nonce": {"type": "string"}, "patient_id": {"type": "string"}, "parameter": {"type": "string"}, "debug_sensor_values": {"type": "boolean"}}, "required": ["min", "max", "nonce", "parameter"],
})
def prove(min: int, max: int, nonce: str, parameter: str, patient_id: str | None = None, debug_sensor_values: bool = False):
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (min, max)) or not (0 <= min <= max < 2**64):
        return {"status": "PROOF_FAILED", "error": "invalid public bounds"}
    if not isinstance(nonce, str) or len(nonce) != 64 or any(c not in "0123456789abcdef" for c in nonce):
        return {"status": "PROOF_FAILED", "error": "invalid nonce"}
    value = evaluation_sensor_value(patient_id, parameter) if os.getenv("CDSS_EVAL") == "1" and patient_id is not None else read_measurement(parameter)
    result = subprocess.run([str(ENGINE)], input=json.dumps({"action": "prove", "value": value, "min": min, "max": max, "nonce": nonce}), capture_output=True, text=True, check=True)
    proof_result = json.loads(result.stdout)
    if proof_result.get("status") == "ALERT" and proof_result.get("package") is None:
        proof_result["reason"] = proof_result.pop("error", "value outside public bounds")
    if debug_sensor_values:
        proof_result["sensor_value_for_debug"] = value
    return proof_result


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
