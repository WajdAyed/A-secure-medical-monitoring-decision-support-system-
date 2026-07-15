from patient_mcp.database import get_patient_by_id
from RAG.rag import search_guidelines
from rule_engine.rules import (
    build_policy,
    validate_policy
)

patient = get_patient_by_id(
    "10009628"
)

if patient is None:
    raise ValueError(
        "Patient not found"
    )

guidelines = search_guidelines(
    patient["condition"]
)

policy = build_policy(
    patient,
    guidelines
)

policy = validate_policy(policy)

print(policy)