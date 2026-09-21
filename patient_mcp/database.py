import json
from pathlib import Path
from datetime import date


DATA = (
    Path(__file__).parent.parent
    / "datasets"
    / "clean"
    / "patients_200.json"
)


def calculate_age(birth_date):
    """Calculate a valid age from a FHIR birthDate."""

    if not birth_date:
        return None

    try:
        birth = date.fromisoformat(birth_date)
        today = date.today()

        if birth > today:
            return None

        age = today.year - birth.year

        if (today.month, today.day) < (birth.month, birth.day):
            age -= 1

        return age

    except Exception:
        return None


def get_patient_by_id(patient_id):

    print("\n" + "=" * 70)
    print("PATIENT DATABASE")
    print("=" * 70)

    print("Requested patient ID:")
    print(patient_id)

    print("\nDataset:")
    print(DATA)

    # ------------------------------------------------
    # Check dataset
    # ------------------------------------------------

    if not DATA.exists():

        print("\n❌ DATASET NOT FOUND")
        print(DATA)

        return None

    print("\n✓ Dataset found")

    # ------------------------------------------------
    # Load FHIR dataset
    # ------------------------------------------------

    try:

        with open(DATA, encoding="utf-8") as f:
            patients = json.load(f)

    except Exception as e:

        print("\n❌ DATASET READ ERROR")
        print(e)

        return None

    print("Number of FHIR patients:")
    print(len(patients))

    # ------------------------------------------------
    # Search patient
    # ------------------------------------------------

    for p in patients:

        identifiers = p.get("identifier", [])

        for identifier in identifiers:

            identifier_value = str(
                identifier.get("value", "")
            )

            if identifier_value == str(patient_id):

                print("\n✓ PATIENT FOUND")

                gender = p.get("gender")

                birth_date = p.get("birthDate")

                age = calculate_age(birth_date)

                if age is None:
                    print("\n⚠️ Skipping patient with invalid future birth date")
                    continue

                condition = p.get("condition", "hypertension")
                conditions = p.get("conditions")
                if isinstance(conditions, list) and conditions:
                    conditions = [str(item) for item in conditions]
                    condition = conditions[0]

                patient = {
                    "id": identifier_value,
                    "gender": gender,
                    "age": age,
                    "condition": condition
                }
                if conditions and len(conditions) > 1:
                    patient["conditions"] = conditions

                print("\nPatient information:")

                print(patient)

                print("=" * 70)

                return patient

    # ------------------------------------------------
    # Patient not found
    # ------------------------------------------------

    print("\n❌ PATIENT NOT FOUND")

    print("Requested ID:")
    print(patient_id)

    print("=" * 70)

    return None
