"""Patient IDs come from the sole EMR FHIR representation, not a copy."""
import json
from pathlib import Path
from .config import ROOT, N_PATIENTS

def patient_ids():
    records = json.loads((ROOT / "datasets" / "clean" / "patients_200.json").read_text(encoding="utf-8"))
    ids = sorted(str(p["identifier"][0]["value"]) for p in records)
    if len(ids) != N_PATIENTS or len(set(ids)) != N_PATIENTS:
        raise RuntimeError(f"Expected exactly {N_PATIENTS} unique EMR patient IDs; found {len(ids)}.")
    return ids
