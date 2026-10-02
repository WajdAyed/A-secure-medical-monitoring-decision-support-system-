"""Server-side verifier. It never reads or receives the sensor value."""
import json
import os
import subprocess
import secrets
from pathlib import Path
from time import perf_counter

from cdss_rpc import call_tool

ENGINE = Path(os.getenv("ZKP_ENGINE_PATH", Path(__file__).resolve().parent.parent / "zkp_engine" / "target" / "release" / ("zkp_engine.exe" if os.name == "nt" else "zkp_engine")))
DEVICE_AGENT_URL = os.getenv("DEVICE_AGENT_URL", "http://127.0.0.1:8006")


def generate_and_verify_proof(bounds, patient_id=None, debug_sensor_values=False):
    if os.getenv("CDSS_REQUIRE_TLS") == "1" and not DEVICE_AGENT_URL.startswith("https://"):
        raise ValueError("DEVICE_AGENT_URL must use HTTPS when CDSS_REQUIRE_TLS=1")
    min_value, max_value = bounds["min"], bounds["max"]
    parameter = bounds.get("parameter")
    if not isinstance(parameter, str) or not parameter.strip():
        raise ValueError("bounds must include a sensor parameter")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (min_value, max_value)) or not (0 <= min_value <= max_value < 2**64):
        raise ValueError("bounds must be ordered unsigned 64-bit integers")
    started = perf_counter()
    nonce = secrets.token_hex(32)
    args = {"min": min_value, "max": max_value, "nonce": nonce, "parameter": parameter}
    args["debug_sensor_values"] = debug_sensor_values
    if patient_id is not None:
        args["patient_id"] = patient_id
    device = call_tool(DEVICE_AGENT_URL, "prove", args, timeout=120)
    if not isinstance(device, dict):
        return {"status": "PROOF_FAILED", "verified": False, "error": "invalid device response"}
    if device.get("status") == "ALERT" and device.get("package") is None:
        response = {"status": "ALERT", "verified": False, "proof_type": "Bulletproofs", "public_bounds": bounds, "reason": "device reports reading outside range; no range proof was produced"}
        if "sensor_value_for_debug" in device:
            response["sensor_value_for_debug"] = device["sensor_value_for_debug"]
        return response
    package = device.get("package")
    if not isinstance(package, dict) or package.get("min") != min_value or package.get("max") != max_value or package.get("nonce") != nonce:
        return {"status": "PROOF_FAILED", "verified": False, "error": "missing proof or bounds mismatch"}
    result = subprocess.run([str(ENGINE)], input=json.dumps({"action": "verify", "package": package, "expected_nonce": nonce}), capture_output=True, text=True, check=True)
    verdict = json.loads(result.stdout)
    proof_hex = package.get("proof")
    response = {"status": verdict["status"], "verified": verdict["verified"], "proof_type": "Bulletproofs", "public_bounds": bounds, "proof_size_bytes": len(proof_hex) // 2 + 64 if isinstance(proof_hex, str) else None, "prove_ms": device.get("elapsed_ms"), "verify_ms": verdict.get("elapsed_ms")}
    if "sensor_value_for_debug" in device:
        response["sensor_value_for_debug"] = device["sensor_value_for_debug"]
    if os.getenv("CDSS_EVAL") == "1":
        response["zkp_process_ms"] = (perf_counter() - started) * 1000
        response["zkp_prove_ms"] = response["prove_ms"]
        response["zkp_verify_ms"] = response["verify_ms"]
    return response
