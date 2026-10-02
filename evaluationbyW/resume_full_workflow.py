"""Resume a saved direct-search pass after the Chroma pass has completed.

No ChromaDB calls are made. The saved chunk corpus is re-embedded during
explicitly recorded restart setup, and retrieval agreement with the completed
direct prefix is checked before accepting new measurements.
"""
import contextlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace


def resume(out, tolerance):
    from evaluationbyW.evaluationby5 import DirectSearch, Progress, save_results, write_json
    out = out.resolve()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    patients = json.loads((out / "patient_order.json").read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in (out / "patient_results.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = [p["patient_id"] for p in patients]
    a = [r["patient_id"] for r in rows if r["method"] == "chroma"]
    b = [r["patient_id"] for r in rows if r["method"] == "direct"]
    if a != expected or b != expected[:len(b)] or len(set(b)) != len(b):
        raise ValueError("Resume requires the full Chroma pass and a contiguous direct-search prefix")
    if len(b) == len(expected):
        save_results(out, rows, manifest, tolerance)
        return
    progress = Progress(out)
    progress.update(status="restart setup", pass_number=2, method="Direct search over all chunks",
                    completed_patients=len(b), total_patients=len(expected), completed_method_runs=len(rows))
    os.environ.update(CDSS_EVAL="1", CDSS_RAG="1", CDSS_DEMO_CONDITIONS="", OMP_NUM_THREADS="1",
                      PATIENT_DATA_FILE=str(out / "patient_snapshot.json"))
    endpoint = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    os.environ["OLLAMA_HOST"] = endpoint
    restart = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "completed_direct_patients": len(b),
               "remaining_patients": len(expected) - len(b), "setup_seconds": {}}
    manifest.setdefault("restarts", []).append(restart)
    manifest["limitations"].append(
        f"The direct pass stopped after {len(b)} measured patients and was resumed from the saved prefix. "
        "Restart setup rebuilt direct vectors from the saved chunks with the same model digest, verified "
        "retrieval agreement for every prior distinct query, and warmed patient #1 again. Prior timings "
        "are unchanged. This interruption and renewed model cache state limit whole-pass timing comparisons.")
    write_json(out / "manifest.json", manifest)
    try:
        import requests
        import ollama
        from fastapi import FastAPI, Request
        from cdss_rpc import MCPJsonRpcServer
        from langchain_core.documents import Document
        from langchain_ollama import OllamaEmbeddings
        from evaluationbyW.full_workflow import services
        tags = requests.get(endpoint + "/api/tags", timeout=10).json()["models"]
        original = {m["name"]: m["digest"] for m in manifest["ollama_models"]["models"]}
        current = {m["name"]: m["digest"] for m in tags}
        for name in ("llama3:latest", "nomic-embed-text:latest"):
            if current.get(name) != original.get(name) or name not in current:
                raise ValueError(f"Model digest changed: {name}")
        chunks = [Document(page_content=d["text"], metadata=d["metadata"]) for d in
                  json.loads((out / "chunk_manifest.json").read_text(encoding="utf-8"))]
        start = time.perf_counter()
        progress.update(stage="rebuilding direct vectors from saved chunks")
        direct = DirectSearch(chunks, OllamaEmbeddings(model="nomic-embed-text", base_url=endpoint))
        restart["setup_seconds"]["direct_embeddings"] = time.perf_counter() - start
        from evaluationbyW.evaluationby5 import digest
        checked = {}
        for row in rows:
            if row["method"] == "direct":
                for query, hashes in zip(row["queries"], row["retrieved_chunks"]):
                    if query in checked and checked[query] != hashes:
                        raise ValueError("Prior query retrieval was inconsistent")
                    checked[query] = hashes
        start = time.perf_counter()
        for query, hashes in checked.items():
            actual = direct.search(query)
            if [digest(s.encode()) for s in actual["guidelines"]] != hashes:
                raise ValueError(f"Restart retrieval differs for query {query!r}")
        restart["setup_seconds"]["retrieval_consistency_check"] = time.perf_counter() - start
        restart["validated_queries"] = len(checked)
        knowledge = SimpleNamespace(app=FastAPI(), rpc=MCPJsonRpcServer("knowledge-direct-resume"))
        @knowledge.app.post("/rpc")
        async def handle(request: Request):
            return await knowledge.rpc.handle(request)
        warmups = json.loads((out / "warmup.json").read_text(encoding="utf-8"))
        with (out / "workflow.log").open("a", encoding="utf-8") as log, \
                contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), \
                services(knowledge, direct, progress) as runner:
            progress.update(status="restart warm-up", stage="resetting llama3", original_patient_number=1)
            start = time.perf_counter()
            ollama.Client(host=endpoint).generate(model="llama3", keep_alive=0)
            restart["setup_seconds"]["model_reset"] = time.perf_counter() - start
            warm = runner.run(manifest["warmup_patient_id"], "direct")
            warm["restart_warmup"] = True
            warmups.append(warm)
            write_json(out / "warmup.json", warmups)
            restart["warmup_error"] = warm["error"]
            write_json(out / "manifest.json", manifest)
            with (out / "patient_results.jsonl").open("a", encoding="utf-8") as stream:
                for position, patient in enumerate(patients[len(b):], len(b) + 1):
                    progress.update(status="running", original_patient_number=patient["original_order"], evaluation_position=position)
                    row = runner.run(patient["patient_id"], "direct")
                    row.update(order=patient["original_order"], pass_number=2, execution_segment=len(manifest["restarts"]) + 1)
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    rows.append(row)
                    log.flush()
                    progress.update(completed_patients=position, completed_method_runs=len(rows),
                                    errors=sum(bool(r["error"]) for r in rows), stage="patient complete")
        write_json(out / "direct_results.json", [r for r in rows if r["method"] == "direct"])
        save_results(out, rows, manifest, tolerance)
        progress.update(status="complete", stage="outputs saved")
    except Exception as exc:
        restart["error"] = f"{type(exc).__name__}: {exc}"
        write_json(out / "manifest.json", manifest)
        progress.update(status="failed", error=restart["error"])
        raise
