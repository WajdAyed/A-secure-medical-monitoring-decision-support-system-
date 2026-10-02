"""Scalability evaluation for the complete patient-processing pipeline.

Run examples:
	python evaluationby3.py --synthetic --sizes 100 500 1000 5000
	python evaluationby3.py --input patients.csv --patient-id patient_id

The input file is expected to contain one patient per row. The processing
function below is intentionally isolated so the real CDSS/privacy pipeline
can replace ``process_patient`` without changing the benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FIGURES_DIR = Path(__file__).resolve().parent / "figures WWWWWWW"


def checkpoint(message: str) -> None:
	"""Print a progress message immediately during long benchmarks."""
	print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def process_patient(patient: dict[str, str]) -> dict[str, str]:
	"""Process one patient; replace this body with the complete workflow."""
	patient_id = str(patient.get("patient_id", "unknown"))
	# A deterministic privacy-preserving identifier for benchmark output.
	private_id = hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:16]
	return {"patient_id": private_id, "status": "processed"}


def _process(patient: dict[str, str]) -> dict[str, str]:
	return process_patient(patient)


def load_patients(path: Path, patient_id: str) -> list[dict[str, str]]:
	if not path.is_file():
		raise FileNotFoundError(f"Input patient file not found: {path}")
	if path.suffix.lower() == ".json":
		import json

		parsed = json.loads(path.read_text(encoding="utf-8"))
		if not isinstance(parsed, list):
			raise ValueError(f"JSON patient file must contain a list: {path}")
		patients = parsed
	else:
		with path.open(newline="", encoding="utf-8") as file:
			patients = list(csv.DictReader(file))
	if not patients:
		raise ValueError(f"Input patient file contains no rows: {path}")
	for index, patient in enumerate(patients):
		patient.setdefault("patient_id", str(patient.get(patient_id, patient.get("id", index))))
	return patients


def synthetic_patients(size: int) -> list[dict[str, str]]:
	return [{"patient_id": str(i), "age": str(20 + i % 70), "diagnosis": "sample"}
			for i in range(size)]


@dataclass
class Result:
	patients: int
	workers: int
	seconds: float
	patients_per_second: float
	memory_mb: float


def benchmark(patients: list[dict[str, str]], workers: int) -> Result:
	if not patients:
		raise ValueError("Cannot benchmark an empty patient dataset.")
	checkpoint(f"Benchmark starting: {len(patients)} patients, {workers} worker(s)")
	started = time.perf_counter()
	if workers == 1:
		list(map(process_patient, patients))
	else:
		with ProcessPoolExecutor(max_workers=workers) as pool:
			list(pool.map(_process, patients, chunksize=max(1, len(patients) // (workers * 4))))
	elapsed = time.perf_counter() - started
	try:
		import resource
		memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if os.name != "nt" else 1024 ** 2)
	except (ImportError, AttributeError):
		memory_mb = 0.0
	result = Result(len(patients), workers, elapsed, len(patients) / elapsed if elapsed else 0, memory_mb)
	checkpoint(f"Benchmark complete: {elapsed:.3f}s ({result.patients_per_second:.2f} patients/s)")
	return result


def main() -> None:
	parser = argparse.ArgumentParser(description="Measure patient-processing scalability.")
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--input", type=Path, help="CSV or JSON file containing patients")
	source.add_argument("--synthetic", action="store_true", help="generate test patients")
	parser.add_argument("--patient-id", default="patient_id")
	parser.add_argument("--sizes", nargs="+", type=int, help="Benchmark sizes; defaults to all input patients")
	parser.add_argument("--workers", type=int, default=1)
	args = parser.parse_args()
	if args.workers < 1:
		parser.error("--workers must be at least 1")
	if args.sizes is not None and any(size < 1 for size in args.sizes):
		parser.error("--sizes must contain only positive integers")
	if args.input:
		checkpoint(f"Loading patients from {args.input}")
		all_patients = load_patients(args.input, args.patient_id)
		sizes = [len(all_patients)] if args.sizes is None else [min(size, len(all_patients)) for size in args.sizes]
		datasets = [all_patients[:size] for size in sizes]
		checkpoint(f"Loaded all {len(all_patients)} patients; benchmark sizes: {sizes}")
	else:
		sizes = args.sizes or [100, 500, 1000]
		checkpoint(f"Generating synthetic datasets: {sizes}")
		datasets = [synthetic_patients(size) for size in sizes]
	checkpoint(f"Running {len(datasets)} benchmark(s)")
	results = [benchmark(patients, args.workers) for patients in datasets]
	FIGURES_DIR.mkdir(parents=True, exist_ok=True)
	try:
		import matplotlib.pyplot as plt

		plt.figure(figsize=(10, 6))
		plt.plot([result.patients for result in results],
				 [result.patients_per_second for result in results], marker="o")
		plt.xlabel("Number of patients")
		plt.ylabel("Patients per second")
		plt.title("Patient-processing scalability")
		plt.grid(axis="y", alpha=0.3)
		plt.tight_layout()
		figure_path = FIGURES_DIR / "evaluationby3_scalability.png"
		plt.savefig(figure_path, dpi=180)
		plt.close()
		checkpoint(f"Saved scalability figure to {figure_path}")
	except ImportError as exc:
		checkpoint(f"Scalability figure was not created: {exc}")
	print("patients,workers,seconds,patients_per_second,memory_mb")
	for result in results:
		print(f"{result.patients},{result.workers},{result.seconds:.6f},"
			  f"{result.patients_per_second:.2f},{result.memory_mb:.2f}")
	checkpoint("All benchmarks complete")


if __name__ == "__main__":
	main()
