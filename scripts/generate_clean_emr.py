from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = BASE_DIR / "datasets" / "clean" / "patients_200.json"

random.seed(42)

CONDITIONS = [
    "hypertension",
    "diabetes",
    "asthma",
    "heart_failure",
    "copd",
    "renal_failure",
    "obesity",
    "anemia",
    "arrhythmia",
    "stroke_risk",
    "depression",
    "arthritis",
]

RACES = [
    "White",
    "Black or African American",
    "Asian",
    "American Indian or Alaska Native",
    "Native Hawaiian or Other Pacific Islander",
    "Other",
]

ETHNICITIES = [
    "Not Hispanic or Latino",
    "Hispanic or Latino",
    "Unknown",
]


def random_birth_date(min_age: int = 18, max_age: int = 90) -> str:
    today = date.today()
    start_year = today.year - max_age
    end_year = today.year - min_age
    year = random.randint(start_year, end_year)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return date(year, month, day).isoformat()


def build_patient(patient_id: int, condition: str, gender: str) -> dict:
    birth_date = random_birth_date()
    return {
        "id": str(uuid4()),
        "resourceType": "Patient",
        "name": [{"use": "official", "family": f"Patient_{patient_id}"}],
        "gender": gender,
        "birthDate": birth_date,
        "condition": condition,
        "identifier": [{
            "value": str(patient_id),
            "system": "http://example.org/fhir/patient",
        }],
        "extension": [
            {
                "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
                "extension": [
                    {"url": "text", "valueString": random.choice(RACES)}
                ],
            },
            {
                "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
                "extension": [
                    {"url": "text", "valueString": random.choice(ETHNICITIES)}
                ],
            },
        ],
    }


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    patients = []
    used_ids = set()
    genders = ["female"] * 100 + ["male"] * 100
    random.shuffle(genders)

    for patient_id, gender in zip(range(100001, 100201), genders):
        condition = random.choice(CONDITIONS)
        while patient_id in used_ids:
            patient_id += 1
        used_ids.add(patient_id)
        patients.append(build_patient(patient_id, condition, gender))

    OUTPUT_FILE.write_text(json.dumps(patients, indent=2), encoding="utf-8")
    print(f"Generated {len(patients)} patients at {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
