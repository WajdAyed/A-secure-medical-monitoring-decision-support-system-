"""Generate comparison figures for Chroma RAG and full-PDF processing."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation 2" / "results"
FIGURES = ROOT / "figures 2"


def main() -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("Install matplotlib first: python -m pip install matplotlib") from exc
    with (RESULTS / "rag_comparison_summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    names = {"rag_chroma": "RAG + Chroma", "no_rag_full_pdf": "No RAG + full PDF"}
    modes = ["rag_chroma", "no_rag_full_pdf"]
    colors = ["#0f766e", "#6b7280"]
    FIGURES.mkdir(parents=True, exist_ok=True)

    fig, axis = plt.subplots(figsize=(8, 4))
    values = [float(next(row for row in rows if row["mode"] == mode)["mean_total_ms"]) for mode in modes]
    bars = axis.bar([names[mode] for mode in modes], values, color=colors)
    axis.set_ylabel("Mean total policy time (ms)")
    axis.set_title("RAG versus complete-PDF policy processing")
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,.0f}", ha="center", va="bottom")
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_9_rag_vs_full_pdf_latency.png", dpi=250)
    fig.savefig(FIGURES / "figure_9_rag_vs_full_pdf_latency.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9, 4.5))
    positions = list(range(3))
    fields = [("valid_policy_rate", "Valid policy", "#2563eb"), ("parameter_match_rate", "Parameter match", "#0f766e"), ("exact_reference_match_rate", "Exact reference", "#d97706")]
    width = .34
    for offset, mode in zip((-.18, .18), modes):
        row = next(item for item in rows if item["mode"] == mode)
        values = [float(row[field]) for field, _, _ in fields]
        axis.bar([x + offset for x in positions], values, width, label=names[mode], color=colors[modes.index(mode)])
    axis.set_xticks(positions, [label for _, label, _ in fields])
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Rate")
    axis.set_title("Policy accuracy comparison")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_10_rag_vs_full_pdf_accuracy.png", dpi=250)
    fig.savefig(FIGURES / "figure_10_rag_vs_full_pdf_accuracy.svg")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    rows_by_mode = {row["mode"]: row for row in rows}
    retrieval_fallback = None
    rag_only_summary = RESULTS / "rag_only_summary.csv"
    if rag_only_summary.exists():
        with rag_only_summary.open(newline="", encoding="utf-8") as stream:
            retrieval_rows = list(csv.DictReader(stream))
        retrieval_fallback = sum(float(row["mean_latency_ms"]) for row in retrieval_rows) / len(retrieval_rows)
    stage_values = []
    for mode in modes:
        row = rows_by_mode[mode]
        total = float(row["mean_total_ms"])
        if row["mean_retrieval_or_scan_ms"] and row["mean_llm_ms"]:
            stage_values.append((float(row["mean_retrieval_or_scan_ms"]), float(row["mean_llm_ms"])))
        elif mode == "rag_chroma" and retrieval_fallback is not None:
            stage_values.append((retrieval_fallback, max(0.0, total - retrieval_fallback)))
        else:
            stage_values.append((0.0, total))
    bottom = [0, 0]
    for index, (label, values) in enumerate((("Retrieval / PDF scan", [item[0] for item in stage_values]), ("LLM generation", [item[1] for item in stage_values]))):
        axis.bar([names[mode] for mode in modes], values, .55, bottom=bottom, label=label, color=("#14b8a6" if index == 0 else "#f59e0b"))
        bottom = [bottom[i] + values[i] for i in range(2)]
    axis.set_ylabel("Mean time (ms)")
    axis.set_title("Where time is spent in each architecture")
    axis.legend()
    axis.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_11_rag_vs_full_pdf_stages.png", dpi=250)
    fig.savefig(FIGURES / "figure_11_rag_vs_full_pdf_stages.svg")
    plt.close(fig)
    print(f"Comparison figures written to {FIGURES}")


if __name__ == "__main__":
    main()
