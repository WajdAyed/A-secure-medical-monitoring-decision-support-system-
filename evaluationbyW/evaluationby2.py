"""Run the patient workflow directly against a guideline PDF and plot results."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


FIGURES_DIR = Path(__file__).resolve().parent / "figures WWWWWWW"
DEFAULT_MAX_GUIDELINE_CHARACTERS = 12_000


def checkpoint(message: str) -> None:
	"""Print a progress message immediately so long API calls are visible."""
	print(
		f"[{time.strftime('%H:%M:%S')}] "
		f"{message.encode('ascii', 'replace').decode('ascii')}",
		flush=True,
	)


def extract_guidelines(pdf_path: Path) -> str:
	try:
		from pypdf import PdfReader
	except ImportError as exc:
		raise RuntimeError(
			"The 'pypdf' package is required to read guideline PDFs. "
			"Install it with 'python -m pip install pypdf'."
		) from exc
	if not pdf_path.is_file():
		raise FileNotFoundError(f"Guideline PDF not found: {pdf_path}")
	text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
	if not text.strip():
		raise ValueError(f"No extractable text found in guideline PDF: {pdf_path}")
	return text


def process_patient(
	client: Any,
	model: str,
	patient_text: str,
	guideline: str,
	max_guideline_characters: int,
) -> dict:
	if len(guideline) > max_guideline_characters:
		checkpoint(
			f"Truncating guideline from {len(guideline):,} to "
			f"{max_guideline_characters:,} characters for model context"
		)
		guideline = guideline[:max_guideline_characters]
	prompt = f"""Use only the guideline PDF text below to complete the normal clinical workflow.
Extract the required bounds/thresholds and make the decision for this patient.
Return JSON with exactly: decision, bounds, explanation. Use unknown when unavailable.

GUIDELINE PDF TEXT:
{guideline}

PATIENT:
{patient_text}"""
	answer = client.chat.completions.create(
		model=model,
		temperature=0,
		response_format={"type": "json_object"},
		messages=[{"role": "user", "content": prompt}],
	)
	content = answer.choices[0].message.content
	if not content:
		raise ValueError("The model returned an empty response.")
	result = json.loads(content)
	if not isinstance(result, dict):
		raise ValueError("The model response must be a JSON object.")
	return result


def main() -> None:
	parser = argparse.ArgumentParser(description="Evaluate all patients without ChromaDB.")
	parser.add_argument("--patients", type=Path, required=True)
	parser.add_argument("--guidelines", type=Path, required=True)
	parser.add_argument("--output", type=Path, default=Path("evaluation_results"))
	parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
	parser.add_argument("--limit", type=int, help="Process at most this many patient records")
	parser.add_argument(
		"--request-timeout",
		type=float,
		default=30.0,
		help="Seconds to wait for each model request (default: 30)",
	)
	parser.add_argument(
		"--max-guideline-characters",
		type=int,
		default=DEFAULT_MAX_GUIDELINE_CHARACTERS,
		help="Maximum guideline text sent to the model (default: 12000)",
	)
	args = parser.parse_args()
	if args.max_guideline_characters < 1:
		parser.error("--max-guideline-characters must be positive")
	if args.limit is not None and args.limit < 1:
		parser.error("--limit must be positive")
	if args.request_timeout <= 0:
		parser.error("--request-timeout must be positive")
	try:
		from openai import OpenAI
	except ImportError:
		parser.error(
			"The 'openai' package is required for evaluationby2.py. "
			"Install it with 'python -m pip install openai'."
		)
	if not args.patients.is_dir():
		parser.error(f"Patient directory does not exist: {args.patients}")
	args.output.mkdir(parents=True, exist_ok=True)
	FIGURES_DIR.mkdir(parents=True, exist_ok=True)

	files = sorted(p for p in args.patients.iterdir() if p.suffix.lower() in {".txt", ".json"})
	if not files:
		raise SystemExit("No .txt or .json patient files found.")f
	patient_inputs: list[tuple[str, str]] = []
	for patient_file in files:
		text = patient_file.read_text(encoding="utf-8")
		if patient_file.suffix.lower() == ".json":
			try:
				parsed = json.loads(text)
			except json.JSONDecodeError:
				parsed = None
			if isinstance(parsed, list):
				patient_inputs.extend(
					(f"{patient_file.stem}_{index}", json.dumps(patient))
					for index, patient in enumerate(parsed, 1)
				)
				continue
		patient_inputs.append((patient_file.stem, text))
	if args.limit is not None:
		patient_inputs = patient_inputs[:args.limit]
	limit_message = f" (limited to {args.limit})" if args.limit is not None else ""
	checkpoint(f"Found {len(patient_inputs)} patient records{limit_message}")
	checkpoint(f"Reading guideline PDF: {args.guidelines}")

	client = OpenAI(timeout=args.request_timeout, max_retries=0)
	guideline = extract_guidelines(args.guidelines)
	checkpoint(f"Loaded guideline text ({len(guideline):,} characters)")
	records = []

	for number, (patient_name, patient_text) in enumerate(patient_inputs, 1):
		started = time.perf_counter()
		checkpoint(f"Starting patient {number}/{len(patient_inputs)}: {patient_name}")
		error = ""
		try:
			result = process_patient(
				client,
				args.model,
				patient_text,
				guideline,
				args.max_guideline_characters,
			)
		except Exception as exc:
			error = str(exc)
			result = {
				"decision": "unknown",
				"bounds": "unknown",
				"explanation": "Model request failed; see the error column.",
			}
			checkpoint(
				f"FAILED patient {number}/{len(patient_inputs)}; continuing: {exc}"
			)
		seconds = time.perf_counter() - started
		records.append({
			"patient": patient_name,
			"order": number,
			"warmup": number == 1,
			"seconds": seconds,
			"decision": str(result.get("decision", "unknown")),
			"bounds": result.get("bounds", "unknown"),
			"explanation": result.get("explanation", ""),
			"error": error,
		})
		checkpoint(f"Completed {patient_name}: {seconds:.2f}s | {records[-1]['decision']}")

	data = pd.DataFrame(records)
	data.to_csv(args.output / "patient_results.csv", index=False)
	checkpoint("Wrote patient_results.csv")
	(args.output / "patient_results.json").write_text(
		data.to_json(orient="records", indent=2), encoding="utf-8"
	)
	checkpoint("Wrote patient_results.json")

	plt.figure(figsize=(11, 5))
	plt.plot(data["order"], data["seconds"], marker="o")
	warmup = data.iloc[0]
	plt.scatter([warmup["order"]], [warmup["seconds"]], color="red", label="Warm-up patient", zorder=3)
	plt.xlabel("Patient (workflow order)")
	plt.ylabel("Processing time (seconds)")
	plt.title("Processing time for each patient")
	plt.xticks(data["order"])
	plt.legend()
	plt.tight_layout()
	plt.savefig(FIGURES_DIR / "evaluationby2_processing_time_line.png", dpi=180)
	plt.close()

	counts = data["decision"].value_counts().sort_index()
	counts.plot.bar(figsize=(9, 5), title="Decision output histogram", xlabel="Decision", ylabel="Patients")
	plt.tight_layout()
	plt.savefig(FIGURES_DIR / "evaluationby2_decision_histogram.png", dpi=180)
	plt.close()
	checkpoint("Wrote timing and decision plots")

	comparison = data.assign(group=data["warmup"].map({True: "warmup", False: "remaining"}))
	comparison.groupby(["group", "decision"]).size().unstack(fill_value=0).to_csv(
		args.output / "decision_difference_warmup_vs_remaining.csv"
	)
	checkpoint(f"Results written to {args.output.resolve()}")


if __name__ == "__main__":
	main()
