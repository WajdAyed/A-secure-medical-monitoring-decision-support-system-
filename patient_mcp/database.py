import json
from pathlib import Path


DATA = Path("datasets/processed/patients_db.json")


def get_patient_by_id(patient_id):

    print("\n" + "=" * 70)
    print("PATIENT DATABASE")
    print("=" * 70)

    print("Database file:")
    print(DATA)

    print("\nSearching for patient:")
    print(patient_id)


    try:

        with open(DATA, encoding="utf-8") as f:

            patients = json.load(f)


    except Exception as e:

        print("\n❌ DATABASE ERROR")
        print(e)

        print("=" * 70)

        return None


    print("\nDatabase loaded successfully")

    print(
        "Total patients loaded:",
        len(patients)
    )


    # temporary thesis patient
    if patient_id.lower() == "ahmed":

        print("\n⚠️ Using temporary thesis patient")

        patient = {
            "id": "ahmed",
            "age": 67,
            "condition": "hypertension"
        }

        print(patient)

        print("=" * 70)

        return patient



    for p in patients:


        if p["patient_id"] == patient_id:


            print("\n✅ Patient found in database")


            patient = {
                "id": p["patient_id"],
                "gender": p["gender"],
                "age": p["age"],
                "condition": p["condition"]
            }


            print("Returned patient:")
            print(patient)

            print("=" * 70)


            return patient



    print("\n❌ Patient not found")

    print("=" * 70)


    return None