"""Compare Chroma RAG with direct full-PDF guideline processing on identical cases."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES = ROOT / "RAG" / "guidelines"
DEFAULT_OUTPUT = ROOT / "evaluation 2" / "results" / "rag_vs_full_pdf_raw.csv"
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool

CASES = {
    "hypertension": {"source": "Hypertension guideline.pdf", "parameter": "systolic_bp", "min": 110, "max": 135},
    "diabetes": {"source": "Diabetes guideline.pdf", "parameter": "blood_glucose", "min": 70, "max": 140},
    "heart_failure": {"source": "Heart Failure guideline.pdf", "parameter": "weight_kg", "min": 60, "max": 90},
}


def load_pdf_text(condition: str) -> tuple[str, float, int]:
    from langchain_community.document_loaders import PyPDFLoader
    source = GUIDELINES / CASES[condition]["source"]
    started = time.perf_counter()
    pages = PyPDFLoader(str(source)).load()
    text = "\n\n".join(page.page_content for page in pages)
    return text, (time.perf_counter() - started) * 1000, len(pages)


def direct_full_pdf_policy(condition: str, age: int, model: str) -> tuple[dict, dict]:
    import ollama
    text, scan_ms, pages = load_pdf_text(condition)
    prompt = f"""Patient:\nAge: {age}\nCondition: {condition}\n\nFull condition-specific clinical guideline PDF:\n{text}\n\nUsing only the guideline above, generate the safe monitoring range for this patient. Return ONLY JSON with parameter, min, and max. Example: {{\"parameter\":\"systolic_bp\",\"min\":110,\"max\":135}}"""
    started = time.perf_counter()
    client = ollama.Client(host=os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")))
    options = {"temperature": 0, "seed": 42}
    response = client.chat(model=model, format="json", messages=[{"role": "user", "content": prompt}], options=options)
    llm_ms = (time.perf_counter() - started) * 1000
    content = response["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("No JSON object in full-PDF response")
    return json.loads(match.group()), {"pdf_scan_ms": scan_ms, "llm_ms": llm_ms, "pages": pages, "prompt_chars": len(prompt), "total_ms": scan_ms + llm_ms}


def score(policy: dict, reference: dict) -> dict:
    minimum, maximum = policy.get("min"), policy.get("max")
    valid = isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum < maximum
    parameter_match = valid and policy.get("parameter") == reference["parameter"]
    exact = parameter_match and minimum == reference["min"] and maximum == reference["max"]
    return {"valid_policy": valid, "parameter_match": parameter_match, "exact_reference_match": exact, "total_bound_absolute_error": abs(minimum - reference["min"]) + abs(maximum - reference["max"]) if valid else ""}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-url", default=os.getenv("RULE_ENGINE_URL", "http://127.0.0.1:8004"))
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--age", type=int, default=50)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3"))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for condition, reference in CASES.items():
        for repeat in range(1, args.repeats + 1):
            for mode in ("rag_chroma", "no_rag_full_pdf"):
                started = time.perf_counter()
                try:
                    if mode == "rag_chroma":
                        policy = call_tool(args.rule_url, "generate_policy", {"patient": {"id": f"comparison-{condition}-{repeat}", "age": args.age, "condition": condition}, "use_rag": True}, timeout=args.timeout)
                        evaluation = policy.get("evaluation", {})
                        timings = {"retrieval_or_scan_ms": evaluation.get("rag_retrieval_ms", ""), "llm_ms": evaluation.get("llm_ms", ""), "pages": "", "prompt_chars": evaluation.get("prompt_chars", ""), "total_ms": (time.perf_counter() - started) * 1000}
                    else:
                        policy, timings = direct_full_pdf_policy(condition, args.age, args.model)
                        timings["retrieval_or_scan_ms"] = timings.pop("pdf_scan_ms")
                        timings["total_ms"] = (time.perf_counter() - started) * 1000
                    scored = score(policy, reference)
                    error = ""
                except Exception as exc:
                    policy, timings, scored, error = {}, {"retrieval_or_scan_ms": "", "llm_ms": "", "pages": "", "prompt_chars": "", "total_ms": (time.perf_counter() - started) * 1000}, {"valid_policy": False, "parameter_match": False, "exact_reference_match": False, "total_bound_absolute_error": ""}, str(exc)
                rows.append({"condition": condition, "repeat": repeat, "mode": mode, "latency_ms": round(timings["total_ms"], 4), "retrieval_or_scan_ms": timings["retrieval_or_scan_ms"], "llm_ms": timings["llm_ms"], "pages": timings["pages"], "prompt_chars": timings["prompt_chars"], "parameter": policy.get("parameter", ""), "min": policy.get("min", ""), "max": policy.get("max", ""), **scored, "error": error})
                print(condition, mode, repeat, f"{rows[-1]['latency_ms']:.2f} ms", "OK" if not error else "FAILED")
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} comparison measurements to {args.output}")


if __name__ == "__main__":
    main()
