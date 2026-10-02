import os
import ollama
import json
import math
import re
from time import perf_counter
from pathlib import Path
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


def normalize_policy(policy):
    """Normalize LLM output into the contract expected by the ZKP layer."""
    if not isinstance(policy, dict):
        raise ValueError(f"Policy must be a dictionary, got {type(policy).__name__}")

    def recursive_bounds(candidate):
        if not isinstance(candidate, (dict, list, tuple)):
            return None
        if isinstance(candidate, dict):
            if "min" in candidate and "max" in candidate:
                return candidate.get("min"), candidate.get("max")
            for value in candidate.values():
                result = recursive_bounds(value)
                if result is not None:
                    return result
            if "lower_bound" in candidate and "upper_bound" in candidate:
                return candidate.get("lower_bound"), candidate.get("upper_bound")
            if "lower" in candidate and "upper" in candidate:
                return candidate.get("lower"), candidate.get("upper")
            return None
        for item in candidate:
            result = recursive_bounds(item)
            if result is not None:
                return result
        return None

    def to_bound(value, field_name, lower_bound):
        if isinstance(value, bool):
            raise ValueError(f"Policy field {field_name} must be numeric, got boolean")
        if isinstance(value, (int, float)):
            num = float(value)
        elif isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError(f"Policy field {field_name} is blank")
            try:
                num = float(stripped)
            except ValueError as exc:
                numeric_parts = re.findall(r"\d+(?:\.\d+)?", stripped)
                if not numeric_parts:
                    raise ValueError(f"Policy field {field_name} is not numeric: {value!r}") from exc
                endpoint = numeric_parts[0] if lower_bound or len(numeric_parts) == 1 else numeric_parts[-1]
                num = float(endpoint)
        else:
            raise ValueError(f"Policy field {field_name} must be numeric, got {type(value).__name__}")

        if not num.is_integer():
            num = math.floor(num) if lower_bound else math.ceil(num)
        return int(num)

    def to_number(value, field_name):
        if isinstance(value, bool):
            raise ValueError(f"Policy field {field_name} must be numeric, got boolean")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError(f"Policy field {field_name} is blank")
            try:
                return float(stripped)
            except ValueError as exc:
                raise ValueError(f"Policy field {field_name} is not numeric: {value!r}") from exc
        raise ValueError(f"Policy field {field_name} must be numeric, got {type(value).__name__}")

    def read_lower_upper(candidate):
        if not isinstance(candidate, dict):
            return None, None
        lower = candidate.get("min", candidate.get("lower", candidate.get("low", candidate.get("minimum"))))
        upper = candidate.get("max", candidate.get("upper", candidate.get("high", candidate.get("maximum"))))
        if lower is None and "lower_bound" in candidate:
            lower = candidate.get("lower_bound")
        if upper is None and "upper_bound" in candidate:
            upper = candidate.get("upper_bound")
        return lower, upper

    nested_pair = recursive_bounds(policy)
    if nested_pair is not None:
        lower, upper = nested_pair
        if lower is None or upper is None:
            raise ValueError(f"Policy missing a valid min/max bound: {policy}")
        lower = to_bound(lower, "min", True)
        upper = to_bound(upper, "max", False)
        if lower >= upper:
            raise ValueError(f"Policy bounds are invalid: min={lower}, max={upper}")
        normalized = dict(policy)
        normalized["min"] = lower
        normalized["max"] = upper
        return normalized

    if "min" in policy or "max" in policy:
        lower = to_bound(policy.get("min"), "min", True)
        upper = to_bound(policy.get("max"), "max", False)
        if lower >= upper:
            raise ValueError(f"Policy bounds are invalid: min={lower}, max={upper}")
        normalized = dict(policy)
        normalized["min"] = lower
        normalized["max"] = upper
        return normalized

    for nested_name in ("safe_range", "range", "bounds"):
        lower, upper = read_lower_upper(policy.get(nested_name))
        if lower is not None and upper is not None:
            lower = to_bound(lower, f"{nested_name}.min", True)
            upper = to_bound(upper, f"{nested_name}.max", False)
            if lower >= upper:
                raise ValueError(f"Policy bounds are invalid: min={lower}, max={upper}")
            normalized = dict(policy)
            normalized["min"] = lower
            normalized["max"] = upper
            return normalized

    if "lower_bound" in policy or "upper_bound" in policy:
        lower = to_bound(policy.get("lower_bound"), "lower_bound", True)
        upper = to_bound(policy.get("upper_bound"), "upper_bound", False)
        if lower >= upper:
            raise ValueError(f"Policy bounds are invalid: min={lower}, max={upper}")
        normalized = dict(policy)
        normalized["min"] = lower
        normalized["max"] = upper
        return normalized

    raise ValueError(f"Policy missing a valid min/max bound: {policy}")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", OLLAMA_HOST)
CHROMA_DB_DIR = Path(__file__).resolve().parent.parent / "knowledge_mcp" / "chroma_db"
GUIDELINE_PDF_DIR = Path(__file__).resolve().parent.parent / "RAG" / "guidelines"
GUIDELINE_PDFS = {
    "hypertension": "Hypertension guideline.pdf",
    "diabetes": "Diabetes guideline.pdf",
    "heart_failure": "Heart Failure guideline.pdf",
}


def search_guidelines(condition: str, k: int = 3) -> list[str]:
    """Retrieve clinical guideline passages directly from ChromaDB."""
    if not CHROMA_DB_DIR.exists():
        raise FileNotFoundError(f"Guideline database missing: {CHROMA_DB_DIR}. Run knowledge_mcp/build_vector_db.py first.")
    embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)
    db = Chroma(persist_directory=str(CHROMA_DB_DIR), embedding_function=embeddings)
    return [doc.page_content for doc in db.similarity_search(condition, k=k)]

FALLBACK_POLICIES = {
    "hypertension": ("systolic_bp", 110, 135),
    "diabetes": ("blood_glucose", 70, 140),
    "asthma": ("peak_flow_percent", 80, 100),
    "heart_failure": ("weight_kg", 60, 90),
    "copd": ("oxygen_saturation", 92, 100),
    "renal_failure": ("creatinine", 1, 2),
    "obesity": ("bmi", 18, 30),
    "anemia": ("hemoglobin", 12, 16),
    "arrhythmia": ("heart_rate", 60, 100),
    "stroke_risk": ("systolic_bp", 110, 135),
    "depression": ("sleep_hours", 7, 9),
    "arthritis": ("pain_score", 0, 4),
}
SUPPORTED_SENSOR_PARAMETERS = {
    "systolic_bp", "heart_rate", "oxygen_saturation", "temperature",
    "sleep_hours", "blood_glucose", "peak_flow_percent", "weight_kg",
    "creatinine", "bmi", "hemoglobin", "pain_score",
}


def fallback_policy(condition):
    """Return the documented integer fallback for conditions absent from the RAG corpus."""
    parameter, lower, upper = FALLBACK_POLICIES.get(
        str(condition).lower(),
        ("systolic_bp", 110, 135),
    )
    return {"parameter": parameter, "min": lower, "max": upper}


def generate_policy(patient, use_rag=True, *, retriever=None, strict=False, observer=None):


    print("\n" + "=" * 70)
    print("POLICY GENERATOR")
    print("=" * 70)


    condition = patient["condition"]
    age = patient["age"]

    rag_override = os.getenv("CDSS_RAG")
    if rag_override in {"0", "1"}:
        use_rag = rag_override == "1"
    if not use_rag:
        return generate_policy_without_rag(patient)


    print("\nPatient information:")
    print(patient)


    # ============================================
    # RAG retrieval
    # ============================================

    print("\nSearching clinical guidelines...")

    try:
        retrieval_start = perf_counter()
        docs = (retriever or search_guidelines)(condition)
        retrieval_ms = (perf_counter() - retrieval_start) * 1000

    except Exception as e:

        print("\n❌ RAG ERROR")
        print(e)

        raise e



    print("\n✅ Guidelines retrieved from RAG")

    print(
        "Number of documents:",
        len(docs)
    )


    for i, doc in enumerate(docs):

        print("\n-----------------------------")
        print(
            "Guideline",
            i + 1
        )

        print(
            doc[:300]
        )



    context = "\n\n".join(docs)



    # ============================================
    # Ollama prompt
    # ============================================

    prompt = f"""
Patient:

Age: {age}
Condition: {condition}

Medical Guidelines:

{context}


Based on the medical guidelines,
generate personalized safe limits.

Return ONLY JSON.

Example:

{{
   "parameter":"systolic_bp",
   "min":110,
   "max":135
}}
"""


    print("\n" + "=" * 70)
    print("SENDING REQUEST TO OLLAMA")
    print("=" * 70)


    print("Model:")
    print("llama3")


    print("\nPrompt:")
    print(prompt)



    # ============================================
    # Ollama call
    # ============================================

    try:

        client = ollama.Client(host=OLLAMA_HOST)

        llm_start = perf_counter()
        options = {"temperature": 0, "seed": 42} if os.getenv("CDSS_EVAL") == "1" else None
        response = client.chat(

            model="llama3",

            format="json",

            messages=[
                {
                    "role":"user",
                    "content":prompt
                }
            ],
            options=options,

        )


    except Exception as e:

        print("\n❌ OLLAMA ERROR")
        print(e)

        raise e



    llm_ms = (perf_counter() - llm_start) * 1000
    text = response["message"]["content"]
    if observer is not None:
        observer(text)



    print("\n" + "=" * 70)
    print("OLLAMA RESPONSE")
    print("=" * 70)

    print(text)



    # ============================================
    # JSON extraction
    # ============================================

    match = re.search(
        r"\{.*\}",
        text,
        re.S
    )


    if not match:

        print("\n❌ NO JSON FOUND")

        raise Exception(
            f"No JSON found:\n{text}"
        )


    json_parse_ok = True
    policy = json.loads(match.group())

    try:
        policy = normalize_policy(policy)
    except ValueError as exc:
        if strict:
            raise
        print(f"Invalid model policy ({exc}); using documented fallback for {condition}.")
        policy = fallback_policy(condition)
    if policy.get("parameter") not in SUPPORTED_SENSOR_PARAMETERS:
        if strict:
            raise ValueError(f"Unsupported model parameter: {policy.get('parameter')!r}")
        print(f"Unsupported model parameter {policy.get('parameter')!r}; using documented fallback for {condition}.")
        policy = fallback_policy(condition)


    print("\n" + "=" * 70)
    print("GENERATED PERSONALIZED POLICY")
    print("=" * 70)

    print(policy)

    print("=" * 70)



    if os.getenv("CDSS_EVAL") == "1":
        policy["evaluation"] = {
            "rag_retrieval_ms": retrieval_ms,
            "llm_ms": llm_ms,
            "prompt_chars": len(prompt),
            "retrieved_chunks": len(docs),
            "llm_raw_output": text,
            "json_parse_ok": json_parse_ok,
            **{key: response.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")},
        }
    return policy


def generate_policy_without_rag(patient):
    """Generate a policy from the complete condition-specific guideline PDF.

    This is the no-retrieval baseline: it deliberately bypasses ChromaDB and
    reads the full local PDF for every patient.  It does not create embeddings;
    embedding creation belongs to the Chroma indexing/retrieval path and would
    make this baseline a different experiment.
    """
    condition = str(patient["condition"]).lower()
    filename = GUIDELINE_PDFS.get(condition)
    if filename is None:
        raise FileNotFoundError(
            f"No project guideline PDF is available for condition {condition!r}; "
            "the no-RAG full-PDF baseline cannot invent a clinical range."
        )
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError as exc:
        raise RuntimeError("The no-RAG full-PDF baseline requires langchain-community.") from exc

    source = GUIDELINE_PDF_DIR / filename
    if not source.is_file():
        raise FileNotFoundError(f"Guideline PDF missing: {source}")
    pdf_started = perf_counter()
    pages = PyPDFLoader(str(source)).load()
    guideline_text = "\n\n".join(page.page_content for page in pages)
    if not guideline_text.strip():
        raise ValueError(f"Guideline PDF contains no extractable text: {source}")
    prompt = f"""
Patient:

Age: {patient['age']}
Condition: {condition}

Full condition-specific clinical guideline PDF:

{guideline_text}

Using only the guideline above, generate personalized safe limits.
Return ONLY JSON.

Example:

{{
   "parameter":"systolic_bp",
   "min":110,
   "max":135
}}
"""
    client = ollama.Client(host=OLLAMA_HOST)
    started = perf_counter()
    options = {"temperature": 0, "seed": 42} if os.getenv("CDSS_EVAL") == "1" else None
    response = client.chat(
        model="llama3",
        format="json",
        messages=[{"role": "user", "content": prompt}], options=options,
    )
    match = re.search(r"\{.*\}", response["message"]["content"], re.S)
    if not match:
        raise ValueError("No JSON found in no-RAG baseline response")
    policy = normalize_policy(json.loads(match.group()))
    if policy.get("parameter") not in SUPPORTED_SENSOR_PARAMETERS:
        policy = fallback_policy(patient["condition"])
    if os.getenv("CDSS_EVAL") == "1":
        policy["evaluation"] = {
            "rag_retrieval_ms": 0.0, "pdf_scan_ms": (started - pdf_started) * 1000,
            "llm_ms": (perf_counter() - started) * 1000,
            "prompt_chars": len(prompt), "retrieved_chunks": 0,
            "guideline_pdf": filename, "guideline_pages": len(pages),
            "llm_raw_output": response["message"]["content"], "json_parse_ok": True,
            **{key: response.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")},
        }
    return policy
