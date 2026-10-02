"""Generate figures for the RAG-only ChromaDB experiment."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
FIGURES = ROOT / "figures 2"


def read_csv(name: str) -> list[dict]:
    with (RESULTS / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Install matplotlib first: python -m pip install matplotlib") from exc
    FIGURES.mkdir(parents=True, exist_ok=True)
    rows = read_csv("rag_only_summary.csv")
    conditions = [row["condition"] for row in rows]
    colors = ["#0f766e", "#2563eb", "#d97706"][:len(rows)]

    fig, axis = plt.subplots(figsize=(8, 4))
    values = [float(row["mean_latency_ms"]) for row in rows]
    bars = axis.bar(conditions, values, color=colors)
    axis.set_ylabel("Mean Chroma retrieval latency (ms)")
    axis.set_title("RAG-only guideline retrieval latency")
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.1f}", ha="center", va="bottom")
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_5_rag_only_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_5_rag_only_latency.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    width = .35
    positions = list(range(len(rows)))
    source = [float(row["source_hit_rate"]) for row in rows]
    bounds = [float(row["bounds_present_rate"]) for row in rows]
    axis.bar([x - width / 2 for x in positions], source, width, label="Correct source PDF", color="#0f766e")
    axis.bar([x + width / 2 for x in positions], bounds, width, label="Expected bounds in chunks", color="#d97706")
    axis.set_xticks(positions, conditions)
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Rate")
    axis.set_title("RAG retrieval accuracy and content coverage")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_6_rag_only_accuracy.png", dpi=250)
    fig.savefig(FIGURES / "figure_6_rag_only_accuracy.svg")
    plt.close(fig)
    print(f"RAG-only figures written to {FIGURES}")


if __name__ == "__main__":
    main()
