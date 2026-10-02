"""Two complete method passes through the real Coordinator MCP workflow.

uv run --with langgraph --with langchain-chroma --with langchain-ollama --with langchain-community \
  --with langchain-text-splitters --with pypdf --with matplotlib --with fastapi \
  --with uvicorn --with requests python evaluationbyW/evaluationby5.py

No patient limit or response cache. Patient #1 warms both methods; original
patient #155 is excluded by default at the user's request.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import re
import shutil
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LABELS = {"chroma": "ChromaDB retrieval", "direct": "Direct search over all chunks"}
STAGES = ("retrieval_s", "bound_generation_s", "proof_s", "total_workflow_s")


class Progress:
    """Small live status files plus an append-only log suitable for Get-Content -Wait."""
    def __init__(self, out):
        self.out, self.state = out, {}
        print(f"Live progress: {out / 'progress.txt'}", file=sys.__stdout__, flush=True)

    def update(self, **values):
        self.state.update(values, updated_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        temporary = self.out / "progress.json.tmp"
        write_json(temporary, self.state)
        temporary.replace(self.out / "progress.json")
        message = " | ".join(f"{k}: {v}" for k, v in self.state.items())
        (self.out / "progress.txt").write_text(message + "\n", encoding="utf-8")
        with (self.out / "progress.log").open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
        print(message, file=sys.__stdout__, flush=True)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def collect_patients():
    """Use exactly the active application's cleaned patient cohort."""
    paths = [ROOT / "datasets/clean/patients_200.json"]
    records, seen, provenance = [], set(), []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [e.get("resource", {}) for e in data.get("entry", [])]
        if not isinstance(data, list):
            continue
        for record in data:
            if not isinstance(record, dict) or record.get("resourceType") != "Patient":
                continue
            ids = [str(i["value"]) for i in record.get("identifier", []) if i.get("value")]
            identifier = ids[0] if ids else str(record.get("id", ""))
            if not identifier:
                raise ValueError(f"Patient without an identifier in {path}")
            if identifier in seen:
                continue
            seen.add(identifier)
            records.append(record)
            provenance.append({"patient_id": identifier, "source": str(path.relative_to(ROOT)),
                               "emr_default_condition": "condition" not in record})
    return records, provenance


class DirectSearch:
    """Exhaustive cosine search. This class never imports or calls Chroma."""
    def __init__(self, chunks, embeddings):
        import numpy as np
        self.np, self.chunks, self.embeddings = np, chunks, embeddings
        vectors = []
        for offset in range(0, len(chunks), 16):
            vectors.extend(embeddings.embed_documents([d.page_content for d in chunks[offset:offset+16]]))
        self.vectors = np.asarray(vectors, dtype=np.float64)
        norms = np.linalg.norm(self.vectors, axis=1)
        if not np.all(np.isfinite(self.vectors)) or np.any(norms == 0):
            raise ValueError("Invalid document embeddings")
        self.unit_vectors = self.vectors / norms[:, None]

    def search(self, query, k=3):
        np = self.np
        query = query.strip()  # Match Knowledge MCP's condition/query normalization.
        if not query:
            raise ValueError("condition or query is required")
        vector = np.asarray(self.embeddings.embed_query(query), dtype=np.float64)
        norm = np.linalg.norm(vector)
        if not np.all(np.isfinite(vector)) or norm == 0:
            raise ValueError("Invalid query embedding")
        scores = self.unit_vectors @ (vector / norm)
        indices = np.argsort(-scores, kind="stable")[:k]
        return {"guidelines": [self.chunks[i].page_content for i in indices],
                "sources": [Path(self.chunks[i].metadata["source"]).name for i in indices],
                "cosine_scores": [float(scores[i]) for i in indices]}



def bounds_equal(a, b, tolerance):
    return len(a) == len(b) and all(
        x["parameter"] == y["parameter"] and all(
            math.isclose(x[k], y[k], abs_tol=tolerance, rel_tol=0) for k in ("min", "max"))
        for x, y in zip(a, b))


def attach_model_outputs(out, rows):
    """Recover even rejected candidates from the unchanged generator's audit log.

    Validate call count, identity and condition before associating output with a
    measured row. JSONL remains the immutable timing record; enriched JSON/CSV
    additionally expose model responses from failed normalization/validation.
    """
    if all("model_outputs" in row for row in rows):
        return
    log_path = out / "workflow.log"
    if not log_path.exists():
        return
    blocks = re.split(r"\nPOLICY GENERATOR\n=+\n", log_path.read_text(encoding="utf-8"))[1:]
    warmups = json.loads((out / "warmup.json").read_text(encoding="utf-8"))
    calls = [row for row in warmups + rows for _ in row["queries"]]
    if len(blocks) != len(calls):
        raise ValueError(f"Audit model call count mismatch: {len(blocks)} versus {len(calls)}")
    block_index = 0
    for row in warmups + rows:
        row["model_outputs"] = []
        row["generated_candidates"] = []
        for query in row["queries"]:
            block = blocks[block_index]
            block_index += 1
            match = re.search(r"Patient information:\s*\n(\{[^\n]+\})", block)
            profile = ast.literal_eval(match.group(1)) if match else None
            if not profile or str(profile["id"]) != row["patient_id"] or profile["condition"] != query:
                raise ValueError("Audit model response identity/condition mismatch")
            match = re.search(r"\nOLLAMA RESPONSE\n=+\n\s*(.*?)(?:\n={20,}|\Z)", block, re.S)
            raw = match.group(1).strip() if match else None
            candidate = None
            if raw:
                try:
                    candidate = json.loads(raw)
                except json.JSONDecodeError:
                    pass
            row["model_outputs"].append({"query": query, "raw_output": raw, "parsed_candidate": candidate})
            row["generated_candidates"].append(candidate)


def save_results(out, rows, manifest, tolerance):
    attach_model_outputs(out, rows)
    write_json(out / "patient_results.json", rows)
    paired = []
    grouped = {}
    for row in rows:
        grouped.setdefault(row["patient_id"], {})[row["method"]] = row
    for pair in grouped.values():
        if len(pair) != 2:
            continue
        a, b = pair["chroma"], pair["direct"]
        item = {"patient_id": a["patient_id"], "order": a["order"],
                "identical_retrieved_chunks": a["retrieved_chunks"] == b["retrieved_chunks"]
                if a["retrieved_chunks"] and b["retrieved_chunks"] else None,
                "identical_patient_profiles": a.get("patient_profile") == b.get("patient_profile")
                if a.get("patient_profile") and b.get("patient_profile") else None,
                "identical_bounds_within_tolerance": bounds_equal(a["bounds"], b["bounds"], tolerance)
                if a["bounds"] is not None and b["bounds"] is not None else None,
                "identical_decisions": a["final_decision"] == b["final_decision"]
                if not a["error"] and not b["error"] else None}
        for method, row in pair.items():
            item.update({f"{method}_{key}": row.get(key) for key in
                         (*STAGES, "sources", "generated_candidates", "bounds", "proof_verified", "proof", "final_decision", "error", "error_stage")})
        paired.append(item)
    with (out / "patient_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]) if paired else ["patient_id"])
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                          for k, v in row.items()} for row in paired)
    matched_ids = {r["patient_id"] for r in paired if r["identical_decisions"] is not None}
    summary = {"patient_count": len(paired), "absolute_bound_tolerance": tolerance,
               "relative_bound_tolerance": 0, "clinical_compatibility_assessed": False,
               "identical_bounds": sum(r["identical_bounds_within_tolerance"] is True for r in paired),
               "different_bounds": sum(r["identical_bounds_within_tolerance"] is False for r in paired),
               "bounds_unavailable": sum(r["identical_bounds_within_tolerance"] is None for r in paired),
               "identical_decisions": sum(r["identical_decisions"] is True for r in paired),
               "different_decisions": sum(r["identical_decisions"] is False for r in paired),
               "decisions_unavailable": sum(r["identical_decisions"] is None for r in paired),
               "paired_success_count": len(matched_ids), "methods": {}, "setup": manifest}
    summary["identical_retrieval_pairs"] = sum(r["identical_retrieved_chunks"] is True for r in paired)
    summary["different_retrieval_pairs"] = sum(r["identical_retrieved_chunks"] is False for r in paired)
    summary["asymmetric_failure_pairs"] = sum(bool(r["chroma_error"]) != bool(r["direct_error"]) for r in paired)
    summary["different_patient_profile_pairs"] = sum(r["identical_patient_profiles"] is False for r in paired)
    summary["different_bounds_with_identical_retrieval"] = sum(
        r["identical_retrieved_chunks"] is True and r["identical_bounds_within_tolerance"] is False for r in paired)
    summary["different_decisions_with_identical_retrieval"] = sum(
        r["identical_retrieved_chunks"] is True and r["identical_decisions"] is False for r in paired)
    for method in LABELS:
        selected = [r for r in rows if r["method"] == method]
        stats = {"attempted": len(selected), "failures": sum(bool(r["error"]) for r in selected)}
        for group, subset in (("all_attempts", selected), ("successful", [r for r in selected if not r["error"]]),
                              ("paired_successful", [r for r in selected if r["patient_id"] in matched_ids])):
            stats[group] = {}
            for stage in STAGES:
                values = [r[stage] for r in subset if r[stage] is not None]
                stats[group][stage] = {"n": len(values), "total": sum(values),
                                      "mean": statistics.mean(values) if values else None}
        summary["methods"][method] = stats
        stats["paired_execution_order"] = {}
        for position in (1, 2):
            subset = [r for r in selected if r["patient_id"] in matched_ids and r.get("within_pair_order") == position]
            stats["paired_execution_order"][str(position)] = {
                "n": len(subset), "mean_total_s": statistics.mean(r["total_workflow_s"] for r in subset) if subset else None}
    write_json(out / "summary.json", summary)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, stage, title in zip(axes, ("total_workflow_s", "retrieval_s"), ("Mean total workflow time", "Mean retrieval time")):
        for index, method in enumerate(LABELS):
            mean = summary["methods"][method]["paired_successful"][stage]["mean"]
            if mean is not None:
                ax.bar(index, mean, color=("#3264a8", "#de8f32")[index])
                ax.text(index, mean, f"{mean:.4f}s", ha="center", va="bottom")
            else:
                ax.text(index, 0.5, "No completed pairs", ha="center")
        ax.set_xticks([0, 1], LABELS.values(), fontsize=9)
        ax.set_ylabel("Seconds")
        ax.set_title(title)
        ax.margins(y=0.2)
    errors = ", ".join(f"{LABELS[m]}: {summary['methods'][m]['failures']} errors" for m in LABELS)
    fig.suptitle(f"All {len(paired)} patients; {len(matched_ids)} successful pairs\n{errors}", fontsize=10)
    fig.text(0.5, 0.01, "Means use the same successful patient pairs; setup and warm-up excluded.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.91))
    fig.savefig(out / "ragNorag.png", dpi=180)
    plt.close(fig)
    lines = ["# ChromaDB versus exhaustive direct retrieval", "", f"Patients: {len(paired)}. Paired successful workflows: {len(matched_ids)}.",
             f"Bounds: {summary['identical_bounds']} identical within absolute tolerance {tolerance} (relative tolerance 0); "
             f"{summary['different_bounds']} different; {summary['bounds_unavailable']} unavailable.",
             f"Decisions: {summary['identical_decisions']} identical; {summary['different_decisions']} different; {summary['decisions_unavailable']} unavailable.",
             "Numeric agreement is not a clinical compatibility assessment.", "", "| Method | Errors | Paired mean total (s) | Paired mean retrieval (s) | Paired mean bounds (s) |", "|---|---:|---:|---:|---:|"]
    for method, stats in summary["methods"].items():
        means = [stats["paired_successful"][s]["mean"] for s in ("total_workflow_s", "retrieval_s", "bound_generation_s")]
        lines.append(f"| {LABELS[method]} | {stats['failures']} | " + " | ".join(f"{v:.6f}" if v is not None else "unavailable" for v in means) + " |")
    lines += ["", "All attempted patients (failures are timed up to the actual failing stage):", "",
              "| Method | Attempts | Completed decisions | Total patient time (s) | Mean attempt time (s) |",
              "|---|---:|---:|---:|---:|"]
    for method, stats in summary["methods"].items():
        timing = stats["all_attempts"]["total_workflow_s"]
        mean = f"{timing['mean']:.6f}" if timing["mean"] is not None else "unavailable"
        lines.append(f"| {LABELS[method]} | {stats['attempted']} | {stats['attempted'] - stats['failures']} | {timing['total']:.6f} | {mean} |")
    if matched_ids:
        a, b = [summary["methods"][m]["paired_successful"] for m in LABELS]
        delta = {s: a[s]["mean"] - b[s]["mean"] for s in STAGES}
        lines += ["", "Mean Chroma minus direct time differences (positive means direct was faster):",
                  json.dumps(delta), "These are single-run stage differences, not a causal estimate. LLM generation, prompt reuse, and system load can dominate elapsed time."]
    lines += ["", f"Ordered retrieved chunks: {summary['identical_retrieval_pairs']} identical pairs and {summary['different_retrieval_pairs']} different pairs.",
              f"Among pairs with identical retrieved chunks, {summary['different_bounds_with_identical_retrieval']} had different accepted bounds and {summary['different_decisions_with_identical_retrieval']} had different decisions.",
              f"There were {summary['asymmetric_failure_pairs']} pairs where only one method failed. Missing bounds are unavailable, not agreement or disagreement. Differences with identical retrieved text cannot be attributed to chunk selection; fixed generation settings do not guarantee identical model outputs."]
    lines += ["", "## Protocol and limitations", *[f"- {s}" for s in manifest["limitations"]],
              "", "See summary.json for setup durations, totals, stage sample counts, all-attempt means, successful-only means, and paired means. Errors and partial outputs are retained in patient_results.json and patient_comparison.csv."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluationbyW" / "evaluationby5_results" / time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--bound-tolerance", type=float, default=1e-6)
    parser.add_argument("--analyze", type=Path, help="Regenerate tables/report/figure from a completed run without rerunning patients")
    parser.add_argument("--resume", type=Path, help="Resume the unfinished direct pass in an existing full-program run")
    parser.add_argument("--exclude-patient-numbers", type=int, nargs="*", default=[155],
                        help="Original 1-based patient positions to exclude; default: 155. Patient #1 is always the warm-up.")
    args = parser.parse_args()
    if not math.isfinite(args.bound_tolerance) or args.bound_tolerance < 0:
        parser.error("Tolerance must be finite and nonnegative")
    if args.resume:
        from evaluationbyW.resume_full_workflow import resume
        resume(args.resume, args.bound_tolerance)
        return
    excluded = set(args.exclude_patient_numbers)
    if any(n < 1 for n in excluded):
        parser.error("Excluded patient numbers must be positive")
    if args.analyze:
        source = args.analyze.resolve()
        out = args.output.resolve()
        out.mkdir(parents=True, exist_ok=False)
        progress = Progress(out)
        progress.update(status="analyzing completed measurements", source_run=str(source), excluded_patient_numbers=sorted(excluded))
        rows = [json.loads(line) for line in (source / "patient_results.jsonl").read_text(encoding="utf-8").splitlines()]
        attach_model_outputs(source, rows)
        rows = [r for r in rows if r["order"] not in excluded]
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest.update(source_run=str(source), analysis_only=True,
                        original_patient_count=manifest["patient_count"],
                        patient_count=len({r["patient_id"] for r in rows}), excluded_patient_numbers=sorted(excluded))
        manifest["limitations"][0] = "Completed measurements are reused without rerunning inference. Original patient positions " + str(sorted(excluded)) + " are excluded at the user's request; both methods retain the original patient order and warm-up on patient #1."
        write_json(out / "manifest.json", manifest)
        shutil.copy2(source / "warmup.json", out / "warmup.json")
        provenance = json.loads((source / "patient_order.json").read_text(encoding="utf-8"))
        write_json(out / "patient_order.json", [dict(p, original_order=i) for i, p in enumerate(provenance, 1) if i not in excluded])
        with (out / "patient_results.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        save_results(out, rows, manifest, args.bound_tolerance)
        progress.update(status="complete", completed_patients=manifest["patient_count"],
                        total_patients=manifest["patient_count"], completed_method_runs=len(rows), stage="outputs saved")
        print(f"Analysis refreshed: {out}")
        return
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    progress = Progress(out)
    progress.update(status="setup", stage="patient discovery", excluded_patient_numbers=sorted(excluded), completed_patients=0)
    os.environ.update(CDSS_EVAL="1", CDSS_RAG="1", CDSS_DEMO_CONDITIONS="", OMP_NUM_THREADS="1")
    os.environ["KNOWLEDGE_CHROMA_DIR"] = str(out / "chroma_index")
    os.environ["PATIENT_DATA_FILE"] = str(out / "patient_snapshot.json")
    manifest = {"setup_seconds": {}, "limitations": [
        "Uses the active application's datasets/clean/patients_200.json only: 200 patients, or 199 with requested exclusion #155. Raw-only records are not members of the active cohort.",
        "Every patient is submitted through the real Coordinator run_cdss MCP endpoint and compiled LangGraph. Patient, Ruler, Knowledge, Privacy and Device calls all use real loopback HTTP MCP transport. Services share a Python process for instrumentation; they are not separate Docker containers.",
        "A fresh isolated Chroma index uses the builder's PDF loader, chunk_size=1000, chunk_overlap=200, default collection and distance metric. The project's existing persistent index is untouched. Both methods receive identical chunks and current nomic-embed-text vectors; indexing is setup, not patient time.",
        "Chroma uses default squared L2 distance, direct search uses exhaustive cosine similarity. Rankings can differ for non-unit vectors and ties; this metric distinction in the existing path is retained and disclosed.",
        "Both methods use the existing llama3 prompt, temperature=0 and seed=42, normalization and supported parameters. Hard-coded fallback is disabled for both; invalid model output is an error. This explicit strict mode differs from production fallback behavior.",
        "All original coordinator nodes, Ruler RPC, condition policies, proof requests, Rust proving/verifying and final decision logic are retained. The Ruler selects one of two Knowledge retrieval tools; generation and strict validation are shared.",
        "Device CDSS_EVAL uses the existing deterministic patient/parameter sensor simulation. Fresh proof nonces remain random. ALERT means the device reported an out-of-range value and produced no proof; it is not a technical error or successful proof verification.",
        "Two full sequential passes: all Chroma patients, then all direct-search patients, in identical original order. Before each pass llama3 is unloaded to reset cross-pass prompt reuse, then patient #1 warms the full workflow and is measured again. Natural within-pass model caching remains enabled for both methods. No artificial minimum duration or application response cache is used.",
        "Figure means use paired successful workflows; failed and incomplete attempts have separate statistics. Missing stage times are null, never zero. One run per patient is insufficient for statistical speed claims."
    ]}
    rows = []
    with (out / "workflow.log").open("w", encoding="utf-8") as log:
        try:
            start = time.perf_counter()
            records, provenance = collect_patients()
            warm_id = provenance[0]["patient_id"]
            write_json(out / "patient_snapshot.json", records)
            provenance = [dict(p, original_order=i) for i, p in enumerate(provenance, 1) if i not in excluded]
            write_json(out / "patient_order.json", provenance)
            manifest.update(patient_count=len(provenance), original_patient_count=len(records), excluded_patient_numbers=sorted(excluded), warmup_patient_id=warm_id)
            progress.update(total_patients=len(provenance), stage="loading guideline chunks")
            manifest["setup_seconds"]["patient_snapshot"] = time.perf_counter() - start
            from langchain_community.document_loaders import PyPDFLoader
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from langchain_ollama import OllamaEmbeddings
            import requests
            endpoint = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
            os.environ["OLLAMA_HOST"] = endpoint
            manifest["ollama_models"] = requests.get(endpoint + "/api/tags", timeout=10).json()
            manifest["packages"] = {p: importlib.metadata.version(p) for p in ("chromadb", "langchain-chroma", "langchain-ollama", "langchain-community", "langchain-text-splitters", "ollama", "numpy")}
            start = time.perf_counter()
            pages, documents = [], []
            for path in sorted((ROOT / "RAG/guidelines").glob("*.pdf")):
                documents.append({"file": path.name, "sha256": digest(path.read_bytes())})
                pages.extend(PyPDFLoader(str(path)).load())
            chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(pages)
            if len(chunks) < 3:
                raise ValueError("Insufficient guideline chunks")
            manifest.update(documents=documents, chunks=len(chunks), embedding_model="nomic-embed-text", llm="llama3", k=3, chunk_size=1000, chunk_overlap=200)
            write_json(out / "chunk_manifest.json", [{"text": d.page_content, "metadata": d.metadata, "sha256": digest(d.page_content.encode())} for d in chunks])
            manifest["setup_seconds"]["shared_pdf_loading_chunking"] = time.perf_counter() - start
            start = time.perf_counter()
            embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=endpoint)
            print(f"Embedding {len(chunks)} chunks once before measurement", flush=True)
            progress.update(stage="precomputing chunk embeddings", chunks=len(chunks))
            direct = DirectSearch(chunks, embeddings)
            manifest["setup_seconds"]["direct_embedding_precompute"] = time.perf_counter() - start
            manifest["vector_norm_range"] = [float(x) for x in (direct.np.linalg.norm(direct.vectors, axis=1).min(), direct.np.linalg.norm(direct.vectors, axis=1).max())]
            # Method A setup only. Method B uses only its own in-memory chunk vectors.
            start = time.perf_counter()
            progress.update(stage="building Chroma index")
            with contextlib.redirect_stdout(log):
                import knowledge_mcp.app as knowledge
            for offset in range(0, len(chunks), 128):
                batch = chunks[offset:offset+128]
                knowledge.db._collection.add(ids=[str(i) for i in range(offset, offset+len(batch))],
                    documents=[d.page_content for d in batch], metadatas=[d.metadata for d in batch],
                    embeddings=direct.vectors[offset:offset+len(batch)].tolist())
            if knowledge.db._collection.count() != len(chunks):
                raise ValueError("Chroma chunk count mismatch")
            manifest["chroma_configuration"] = knowledge.db._collection.configuration
            manifest["setup_seconds"]["chroma_index_build_and_load"] = time.perf_counter() - start
            from evaluationbyW.full_workflow import services
            start = time.perf_counter()
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), services(knowledge, direct, progress) as runner:
                manifest["setup_seconds"]["shared_services_start"] = time.perf_counter() - start
                warmups = []
                manifest["execution_mode"] = "two full passes via Coordinator MCP"
                manifest["setup_seconds"]["pass_model_reset"] = {}
                write_json(out / "manifest.json", manifest)
                with (out / "patient_results.jsonl").open("w", encoding="utf-8") as stream:
                    for pass_number, method in enumerate(LABELS, 1):
                        import ollama
                        progress.update(status="preparing pass", pass_number=pass_number, method=LABELS[method], stage="resetting llama3", completed_patients=0)
                        reset_start = time.perf_counter()
                        ollama.Client(host=endpoint).generate(model="llama3", keep_alive=0)
                        manifest["setup_seconds"]["pass_model_reset"][method] = time.perf_counter() - reset_start
                        progress.update(status="warm-up", original_patient_number=1)
                        warmups.append(runner.run(warm_id, method))
                        write_json(out / "warmup.json", warmups)
                        manifest["warmup_errors"] = {r["method"]: r["error"] for r in warmups}
                        write_json(out / "manifest.json", manifest)
                        for completed, patient in enumerate(provenance, 1):
                            index = patient["original_order"]
                            progress.update(status="running", original_patient_number=index, evaluation_position=completed)
                            row = runner.run(patient["patient_id"], method)
                            row.update(order=index, pass_number=pass_number)
                            rows.append(row)
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                            stream.flush()
                            log.flush()
                            print(f"{completed}/{len(provenance)} (original patient #{index}) {method}: {row['total_workflow_s']:.2f}s {row['error'] or row['final_decision']['status']}", file=sys.__stdout__, flush=True)
                            progress.update(completed_patients=completed, completed_method_runs=len(rows),
                                            errors=sum(bool(r["error"]) for r in rows), stage="patient complete")
                        write_json(out / f"{method}_results.json", [r for r in rows if r["method"] == method])
            summary = save_results(out, rows, manifest, args.bound_tolerance)
            progress.update(status="complete", stage="outputs saved")
            print(json.dumps({k: v for k, v in summary.items() if k not in ("setup", "methods")}, indent=2))
        except Exception as exc:
            progress.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            manifest["fatal_error"] = f"{type(exc).__name__}: {exc}"
            write_json(out / "manifest.json", manifest)
            if rows:
                save_results(out, rows, manifest, args.bound_tolerance)
            raise
    print(f"Outputs: {out}", flush=True)


if __name__ == "__main__":
    main()
