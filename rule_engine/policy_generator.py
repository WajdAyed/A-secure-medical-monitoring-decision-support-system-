import os
import ollama
import json
import math
import re
from time import perf_counter
from cdss_rpc import call_tool


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

KNOWLEDGE_MCP_URL = os.getenv("KNOWLEDGE_MCP_URL", "http://127.0.0.1:8010")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

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


def fallback_policy(condition):
    """Return the documented integer fallback for conditions absent from the RAG corpus."""
    parameter, lower, upper = FALLBACK_POLICIES.get(
        str(condition).lower(),
        ("systolic_bp", 110, 135),
    )
    return {"parameter": parameter, "min": lower, "max": upper}


def generate_policy(patient, use_rag=True):


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

    print("\nCalling Knowledge MCP (RAG)...")

    print("Knowledge MCP JSON-RPC endpoint:")
    print(f"{KNOWLEDGE_MCP_URL}/rpc")


    try:

        retrieval_start = perf_counter()
        data = call_tool(KNOWLEDGE_MCP_URL, "search_guidelines", {"condition": condition}, timeout=30)
        retrieval_ms = (perf_counter() - retrieval_start) * 1000

        print("\nKnowledge MCP response:")
        print(data)

        if "guidelines" not in data:

            print("\n❌ KNOWLEDGE MCP ERROR")
            print(data)

            raise Exception(
                f"Knowledge MCP Error:\n{data}"
            )

        docs = data["guidelines"]

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
        print(f"Invalid model policy ({exc}); using documented fallback for {condition}.")
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
    """Generate the evaluation baseline without retrieving guideline context."""
    prompt = f"""
Patient:

Age: {patient['age']}
Condition: {patient['condition']}

Generate personalized safe limits.
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
    if os.getenv("CDSS_EVAL") == "1":
        policy["evaluation"] = {
            "rag_retrieval_ms": 0.0, "llm_ms": (perf_counter() - started) * 1000,
            "prompt_chars": len(prompt), "retrieved_chunks": 0,
            "llm_raw_output": response["message"]["content"], "json_parse_ok": True,
            **{key: response.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")},
        }
    return policy
