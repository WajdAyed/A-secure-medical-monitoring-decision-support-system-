from fastapi import FastAPI, Request
import subprocess
import json

from .sensor import read_systolic_bp
from cdss_rpc import MCPJsonRpcServer

app = FastAPI()
rpc = MCPJsonRpcServer("device-agent")


@rpc.tool("prove", "Generate a device-local proof for the supplied bounds.", {
    "type": "object", "properties": {"min": {"type": "integer"}, "max": {"type": "integer"}}, "required": ["min", "max"],
})
def prove(min: int, max: int):

    value = read_systolic_bp()

    payload = {
        "value": value,
        "min": min,
        "max": max
    }

    print("Sensor value acquired locally.")
    print("Generating ZKP proof locally.")

    result = subprocess.run(
        [
            r"D:\9raya\memoire 2026\Privacy-Preserving-CDSS\zkp_engine\target\debug\zkp_engine.exe"
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True
    )

    print("RETURN CODE:", result.returncode)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    return json.loads(result.stdout)


@app.post("/rpc")
async def handle_rpc(request: Request):
    return await rpc.handle(request)
