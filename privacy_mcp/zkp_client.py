import json
import math
import os
import secrets
import subprocess
from time import perf_counter
from pathlib import Path


DEFAULT_ENGINE_NAME = "zkp_engine.exe" if os.name == "nt" else "zkp_engine"
ENGINE_PATH_OVERRIDE = os.getenv("ZKP_ENGINE_PATH")

if ENGINE_PATH_OVERRIDE:
    ENGINE = Path(ENGINE_PATH_OVERRIDE).expanduser().resolve()
else:
    ENGINE = (
        Path(__file__).resolve().parent.parent
        / "zkp_engine"
        / "target"
        / "release"
        / DEFAULT_ENGINE_NAME
    )



def generate_and_verify_proof(bounds, patient_id=None):

    min_value = bounds["min"]
    max_value = bounds["max"]

    if isinstance(min_value, float) and not min_value.is_integer():
        min_value = math.floor(min_value)
    if isinstance(max_value, float) and not max_value.is_integer():
        max_value = math.ceil(max_value)

    min_value = int(min_value)
    max_value = int(max_value)


    print("\n" + "=" * 70)
    print("DEVICE ZKP CLIENT")
    print("=" * 70)



    print("\nRust ZKP Engine:")

    print(
        ENGINE
    )



    if not ENGINE.exists():

        print("\n❌ Rust engine not found")

        raise FileNotFoundError(
            ENGINE
        )


    print("✓ Rust engine found")



    # ==================================================
    # Device side sensor simulation
    # ==================================================

    print("\nDEVICE SENSOR")


    print(
        "Reading sensor value locally..."
    )


    # The actual value remains process-local.  Evaluation uses a repeatable
    # patient-specific simulator solely for independently computed labels.
    if os.getenv("CDSS_EVAL") == "1" and patient_id is not None:
        from device_agent.sensor import evaluation_sensor_value
        device_value = evaluation_sensor_value(str(patient_id))
    else:
        # Demo sensor: sample locally around the Ruler-generated bounds.
        # The interval deliberately includes safe and unsafe readings.
        device_value = secrets.SystemRandom().randint(
            max(0, min_value - 30),
            max_value + 30,
        )

    print("Sensor acquired inside the local ZKP boundary.")



    print(
        "\nPrivacy boundary:"
    )


    print(
        "✓ This value never leaves the device"
    )



    # ==================================================
    # ZKP generation
    # ==================================================


    print("\nPreparing Zero-Knowledge proof...")


    request = {

        "value": device_value,

        "min": min_value,

        "max": max_value

    }



    print("\nProof parameters:")

    print({

        "min": min_value,

        "max": max_value

    })


    print(
        "Sensor value hidden from external components 🔒"
    )



    print("\nCalling Rust Bulletproof Engine...")



    try:


        started = perf_counter()
        result = subprocess.run(

            [str(ENGINE)],

            input=json.dumps(request),

            capture_output=True,

            text=True,

            check=True,

        )


    except subprocess.CalledProcessError as e:


        print("\n❌ Rust execution failed")

        print(e.stderr)

        raise e



    print("\nRust response:")

    print(
        result.stdout
    )



    proof = json.loads(result.stdout)
    # Local Doctor Console demo: expose the exact sampled value alongside the
    # independent ZKP outcome. Do not use this response shape in deployment.
    proof["sensor_value_for_console"] = device_value
    if os.getenv("CDSS_EVAL") == "1":
        proof["zkp_process_ms"] = (perf_counter() - started) * 1000
        # Rust reports these separately around RangeProof::prove_single and
        # RangeProof::verify_single; retain unprefixed names for the evaluator.
        proof["zkp_prove_ms"] = proof.get("prove_ms")
        proof["zkp_verify_ms"] = proof.get("verify_ms")



    print("\n✅ Proof generated")


    print(proof)


    print("=" * 70)



    return proof
