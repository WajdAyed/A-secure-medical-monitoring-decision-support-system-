"""Shared deterministic utilities for the new clinical-RAG evaluation suite."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Iterable

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"
FIGURES = ROOT / "evaluation" / "figures"


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_ci(values: Iterable[float], seed: int = SEED, draws: int = 2_000) -> tuple[float, float]:
    values = list(values)
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(draws))
    return means[int(.025 * (draws - 1))], means[int(.975 * (draws - 1))]


def mcnemar_exact(no_rag: list[bool], rag: list[bool]) -> tuple[int, int, float]:
    """Two-sided exact binomial McNemar p-value without scipy."""
    b = sum(a and not c for a, c in zip(no_rag, rag))
    c = sum(not a and d for a, d in zip(no_rag, rag))
    n = b + c
    if n == 0:
        return b, c, 1.0
    from math import comb
    p = min(1.0, 2 * sum(comb(n, i) for i in range(0, min(b, c) + 1)) / 2**n)
    return b, c, p


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
