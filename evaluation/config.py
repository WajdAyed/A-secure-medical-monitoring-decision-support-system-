"""Shared, deterministic configuration for the CDSS evaluation suite."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RESULTS, FIGURES = ROOT / "evaluation" / "results", ROOT / "evaluation" / "figures"
N_PATIENTS, WARMUP, SEED = 200, 1, 42
TIMEOUT_SECONDS, RETRIES = 120, 2
URLS = {"coordinator":"http://127.0.0.1:8007", "emr":"http://127.0.0.1:8005", "ruler":"http://127.0.0.1:8004", "privacy":"http://127.0.0.1:8003", "knowledge":"http://127.0.0.1:8010", "ollama":"http://127.0.0.1:11434"}
