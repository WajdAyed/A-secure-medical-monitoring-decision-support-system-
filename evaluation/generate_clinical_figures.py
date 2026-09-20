"""Generate 300-dpi PNG/PDF figures and captions from clinical evaluation CSVs."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from evaluation_utils import FIGURES, RESULTS, seed_everything

PALETTE = {"no_rag": "#0072B2", "rag": "#D55E00", "guideline_rag": "#D55E00"}  # Okabe-Ito


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle: return list(csv.DictReader(handle))


def save(fig, output: Path, caption: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    output.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS); parser.add_argument("--figures", type=Path, default=FIGURES)
    args = parser.parse_args(); seed_everything()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    benchmark = args.results / "benchmark_comparison_summary.csv"
    if benchmark.exists():
        data = rows(benchmark); datasets = sorted({r["dataset"] for r in data}); width = .36; fig, ax = plt.subplots(figsize=(7, 4))
        for j, condition in enumerate(("no_rag", "guideline_rag")):
            subset = {r["dataset"]: r for r in data if r["condition"] == condition}; values = [float(subset[d]["accuracy"]) for d in datasets]; errors = [[v-float(subset[d]["ci95_low"]) for d,v in zip(datasets,values)], [float(subset[d]["ci95_high"])-v for d,v in zip(datasets,values)]]
            ax.bar([i+(j-.5)*width for i in range(len(datasets))], values, width, yerr=errors, capsize=4, label=condition.replace("_", " ").title(), color=PALETTE[condition])
        ax.set_xticks(range(len(datasets)), datasets); ax.set_ylim(0, 1); ax.set_ylabel("Accuracy (proportion)"); ax.set_xlabel("Dataset"); ax.legend(); ax.set_title("Medical QA accuracy with 95% bootstrap CIs"); save(fig, args.figures / "benchmark_accuracy", "Accuracy on the fixed seed=42 20% test split; error bars are 95% bootstrap confidence intervals."); plt.close(fig)
        fig, ax = plt.subplots(figsize=(7, 4)); own = [float(next(r for r in data if r["dataset"] == d and r["condition"] == "guideline_rag")["accuracy"]) - float(next(r for r in data if r["dataset"] == d and r["condition"] == "no_rag")["accuracy"]) for d in datasets]; labels = datasets + ["Paper: multi-agent", "Paper: curated top-500"]; values = own + [.05, .10]
        ax.bar(labels, values, color=[PALETTE["rag"]]*len(own)+["#009E73", "#CC79A7"]); ax.axhline(0, color="black", linewidth=.8); ax.set_ylabel("Accuracy delta (percentage points)"); ax.set_xlabel("Evaluation"); ax.set_title("RAG gain over baseline"); ax.tick_params(axis="x", rotation=20); save(fig, args.figures / "benchmark_accuracy_delta", "Own-system deltas use the same test questions. Paper-reported gains are shown only as contextual, different-model comparisons."); plt.close(fig)
    policy = args.results / "policy_gold_summary.csv"
    if policy.exists():
        data = rows(policy); names = ["json_valid_rate", "mean_bound_mae", "within_tolerance_rate", "run_to_run_min_sd", "retrieval_hit_at_3"]; available = [x for x in names if any(r.get(x, "") for r in data)]
        fig, axes = plt.subplots(1, len(available), figsize=(3.2*len(available), 4)); axes = [axes] if len(available) == 1 else axes
        for ax, metric in zip(axes, available):
            subset = [r for r in data if r.get(metric, "")]; ax.bar([r["mode"] for r in subset], [float(r[metric]) for r in subset], color=[PALETTE[r["mode"]] for r in subset]); ax.set_xlabel("Condition"); ax.set_ylabel(metric.replace("_", " "))
        fig.suptitle("Gold-policy evaluation metrics"); save(fig, args.figures / "policy_gold_metrics", "Policy-generation quality against clinician-filled gold policies; lower is better for MAE and standard deviation."); plt.close(fig)
    latency = args.results / "latency_raw.csv"
    if latency.exists():
        data = rows(latency); stages = ["retrieval_ms", "generation_ms", "proof_ms", "decision_ms"]; fig, ax = plt.subplots(figsize=(7, 4)); bottom = [0., 0.]
        for stage, color in zip(stages, ["#56B4E9", "#E69F00", "#009E73", "#CC79A7"]):
            values = [sum(float(r[stage]) for r in data if r["mode"] == mode)/max(1, sum(r["mode"] == mode for r in data)) for mode in ("no_rag", "rag")]; ax.bar(["No RAG", "RAG"], values, bottom=bottom, label=stage.replace("_ms", ""), color=color); bottom = [a+b for a,b in zip(bottom,values)]
        ax.set_xlabel("Condition"); ax.set_ylabel("Mean latency (ms)"); ax.legend(); ax.set_title("Stage latency across at least 30 runs"); save(fig, args.figures / "latency_stages", "Mean per-stage latency. Sensor values vary across runs and remain local to the proof measurement."); plt.close(fig)
    print(f"Clinical figures written to {args.figures}")


if __name__ == "__main__": main()
