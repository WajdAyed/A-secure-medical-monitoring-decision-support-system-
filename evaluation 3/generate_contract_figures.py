"""Generate contract pass-rate and latency figures."""
from __future__ import annotations

import csv
from pathlib import Path

RESULTS = Path(__file__).with_name("results")
FIGURES = Path(__file__).with_name("figures")


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with (RESULTS / "contract_summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    FIGURES.mkdir(parents=True, exist_ok=True)
    labels = [row["family"] for row in rows]
    rates = [float(row["pass_rate"]) * 100 for row in rows]
    fig, axis = plt.subplots(figsize=(8, 4)); axis.bar(labels, rates, color="#0f766e"); axis.set_ylim(0, 105); axis.set_ylabel("Passed cases (%)"); axis.set_title("Workflow contract pass rate"); axis.tick_params(axis="x", rotation=20); fig.tight_layout(); fig.savefig(FIGURES / "figure_18_contract_pass_rate.png", dpi=250); plt.close(fig)
    latency = [float(row["median_latency_ms"]) for row in rows]
    fig, axis = plt.subplots(figsize=(8, 4)); axis.bar(labels, latency, color="#2563eb"); axis.set_ylabel("Median latency (ms)"); axis.set_title("Contract-case latency"); axis.tick_params(axis="x", rotation=20); fig.tight_layout(); fig.savefig(FIGURES / "figure_19_contract_latency.png", dpi=250); plt.close(fig)
    print(f"Wrote figures to {FIGURES}")


if __name__ == "__main__":
    main()