"""Benchmark every patient and plot the execution time of each implementation.

The first patient is used as a warm-up and is excluded from the statistics and
the figure. Replace ``implementations`` with the project functions to test.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import matplotlib.pyplot as plt


FIGURES_DIR = Path(__file__).resolve().parent / "figures WWWWWWW"
PATIENTS_FILE = Path(__file__).resolve().parents[1] / "datasets" / "clean" / "patients_200.json"


def checkpoint(message: str) -> None:
	"""Print a progress message immediately, including the current time."""
	print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def evaluate_patients(
	patients: Iterable[object],
	implementations: dict[str, Callable[[object], object]],
) -> dict[str, list[float]]:
	"""Return execution time (seconds) for every implementation and patient."""
	patients = list(patients)
	if not patients:
		raise ValueError("At least one patient is required for the warm-up run.")

	# Warm-up: run once, but do not include this patient's timings.
	warmup_patient = patients[0]
	checkpoint("Starting warm-up patient")
	for implementation in implementations.values():
		implementation(warmup_patient)
	checkpoint("Warm-up complete")

	timings = {name: [] for name in implementations}
	for patient_number, patient in enumerate(patients[1:], start=2):
		checkpoint(f"Processing patient {patient_number}/{len(patients)}")
		for name, implementation in implementations.items():
			start = time.perf_counter()
			implementation(patient)
			timings[name].append(time.perf_counter() - start)
		checkpoint(f"Patient {patient_number} complete")

	return timings


def plot_timings(timings: dict[str, list[float]]) -> Path:
	"""Create and save a grouped timing chart."""
	if not timings or not any(timings.values()):
		raise ValueError("No non-warm-up patient timings were recorded.")
	lengths = {len(values) for values in timings.values()}
	if len(lengths) != 1:
		raise ValueError("Every implementation must produce one timing per patient.")

	patient_count = max(map(len, timings.values()))
	width = 0.8 / max(len(timings), 1)
	x = list(range(patient_count))

	fig, ax = plt.subplots(figsize=(max(10, patient_count * 0.8), 6))
	for index, (name, values) in enumerate(timings.items()):
		positions = [item + (index - (len(timings) - 1) / 2) * width for item in x]
		bars = ax.bar(positions, values, width, label=name)
		ax.bar_label(bars, labels=[f"{value:.4f}s" for value in values], padding=3, rotation=90)

	ax.set_xlabel("Patient number (patient 1 was warm-up and is excluded)")
	ax.set_ylabel("Time (seconds)")
	ax.set_title("Execution time per patient and implementation")
	ax.set_xticks(x, [str(number) for number in range(2, patient_count + 2)])
	ax.legend()
	ax.grid(axis="y", alpha=0.3)
	fig.tight_layout()
	FIGURES_DIR.mkdir(parents=True, exist_ok=True)
	figure_path = FIGURES_DIR / "evaluationby1_timings.png"
	fig.savefig(str(figure_path), dpi=180)
	plt.close(fig)
	checkpoint(f"Saved timing figure to {figure_path}")
	return figure_path


if __name__ == "__main__":
	checkpoint(f"Loading patients from {PATIENTS_FILE}")
	patients = json.loads(PATIENTS_FILE.read_text(encoding="utf-8"))
	if not isinstance(patients, list) or len(patients) != 200:
		raise ValueError(f"Expected exactly 200 patients in {PATIENTS_FILE}")
	checkpoint(f"Loaded all {len(patients)} patients")
	implementations = {
		"Baseline": lambda patient: patient.get("id", "unknown"),
		"Validated": lambda patient: str(patient.get("id", "unknown")),
	}
	plot_timings(evaluate_patients(patients, implementations))