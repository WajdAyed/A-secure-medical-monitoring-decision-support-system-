"""Experiment 1: deterministic no-RAG versus guideline-RAG medical QA.

Requires running Ollama (llama3), Knowledge MCP, and `pip install datasets`.
Raw per-question results are written even when an individual inference fails.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from pathlib import Path

import ollama

from evaluation_utils import RESULTS, SEED, bootstrap_ci, mcnemar_exact, seed_everything, write_csv

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from cdss_rpc import call_tool


DATASETS = {"MedMCQA": "openlifescienceai/medmcqa", "MedQA-USMLE": "GBaker/MedQA-USMLE-4-options"}


def question_and_options(row: dict) -> tuple[str, list[str], int]:
    question = str(row.get("question", row.get("Question", ""))).strip()
    options = row.get("options")
    if isinstance(options, dict):
        options = [options[key] for key in sorted(options)]
    elif not isinstance(options, list):
        options = [row.get(key, "") for key in ("opa", "opb", "opc", "opd") if row.get(key, "")]
    answer = row.get("cop", row.get("answer_idx", row.get("answer", row.get("label"))))
    if isinstance(answer, str) and answer.upper() in "ABCD":
        answer = "ABCD".index(answer.upper())
    return question, [str(x) for x in options], int(answer)


def load_questions(name: str, sample_size: int | None) -> list[dict]:
    from datasets import load_dataset
    dataset = load_dataset(DATASETS[name], split="train")
    indices = list(range(len(dataset)))
    rng = random.Random(SEED)
    rng.shuffle(indices)
    test = indices[int(.8 * len(indices)):]
    if sample_size is not None:
        test = test[:sample_size]
    output = []
    for index in test:
        try:
            question, options, answer = question_and_options(dict(dataset[index]))
            if question and len(options) >= 2 and 0 <= answer < len(options):
                output.append({"id": str(index), "question": question, "options": options, "answer": answer})
        except (KeyError, TypeError, ValueError):
            continue
    return output


def ask(question: dict, context: str) -> tuple[int | None, str, float]:
    choices = "\n".join(f"{chr(65+i)}. {value}" for i, value in enumerate(question["options"]))
    prompt = f"Answer this medical multiple-choice question. Return ONLY one letter A-{chr(64+len(question['options']))}.\n\n{question['question']}\n{choices}"
    if context:
        prompt += f"\n\nGuideline context (may or may not answer this question):\n{context}"
    started = time.perf_counter()
    response = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).chat(
        model="llama3", messages=[{"role": "user", "content": prompt}], options={"seed": SEED, "temperature": 0},
    )
    text = response["message"]["content"].strip()
    match = re.search(r"\b([A-D])\b", text.upper())
    return ("ABCD".index(match.group(1)) if match else None), text, (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=None, help="Fixed test-set sample per dataset; omit for all 20%% test examples")
    parser.add_argument("--output", type=Path, default=RESULTS / "benchmark_comparison_raw.csv")
    args = parser.parse_args()
    if args.sample_size is not None and args.sample_size < 1: parser.error("--sample-size must be positive")
    seed_everything()
    rows = []
    for dataset_name in DATASETS:
        questions = load_questions(dataset_name, args.sample_size)
        for item in questions:
            for condition in ("no_rag", "guideline_rag"):
                try:
                    context = ""
                    retrieval_ms = 0.0
                    if condition == "guideline_rag":
                        began = time.perf_counter()
                        retrieved = call_tool(os.getenv("KNOWLEDGE_MCP_URL", "http://127.0.0.1:8010"), "search_guidelines", {"query": item["question"], "k": 3}, timeout=60)
                        retrieval_ms = (time.perf_counter() - began) * 1000
                        context = "\n\n".join(retrieved.get("guidelines", []))
                    prediction, response, generation_ms = ask(item, context)
                    error = ""
                except Exception as exc:
                    prediction, response, retrieval_ms, generation_ms, error = None, "", 0.0, 0.0, str(exc)
                rows.append({"seed": SEED, "dataset": dataset_name, "question_id": item["id"], "condition": condition,
                             "correct_answer": item["answer"], "predicted_answer": prediction, "correct": prediction == item["answer"],
                             "retrieval_ms": round(retrieval_ms, 4), "generation_ms": round(generation_ms, 4), "error": error, "response": response})
    fields = ["seed", "dataset", "question_id", "condition", "correct_answer", "predicted_answer", "correct", "retrieval_ms", "generation_ms", "error", "response"]
    write_csv(args.output, rows, fields)
    summary = []
    for name in DATASETS:
        paired = {row["question_id"]: {} for row in rows if row["dataset"] == name}
        for row in rows:
            if row["dataset"] == name and not row["error"]: paired[row["question_id"]][row["condition"]] = row["correct"]
        for condition in ("no_rag", "guideline_rag"):
            values = [item[condition] for item in paired.values() if condition in item]
            low, high = bootstrap_ci([float(x) for x in values])
            summary.append({"dataset": name, "condition": condition, "n": len(values), "accuracy": sum(values) / len(values) if values else "", "ci95_low": low, "ci95_high": high})
        pairs = [item for item in paired.values() if set(item) == {"no_rag", "guideline_rag"}]
        b, c, p = mcnemar_exact([x["no_rag"] for x in pairs], [x["guideline_rag"] for x in pairs])
        for row in summary[-2:]: row.update({"mcnemar_b": b, "mcnemar_c": c, "mcnemar_p": p})
    write_csv(RESULTS / "benchmark_comparison_summary.csv", summary, list(summary[0]) if summary else ["dataset"])
    print(f"Wrote {len(rows)} raw results to {args.output}")


if __name__ == "__main__": main()
