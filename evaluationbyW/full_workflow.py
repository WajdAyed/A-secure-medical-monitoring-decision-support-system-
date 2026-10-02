"""Evaluation instrumentation around the real six-service MCP/LangGraph workflow.

Clinical nodes and RPC calls are not substituted. The Ruler's sole retrieval
dependency selects one of two Knowledge tools; both use the original generator.
"""
import contextlib
import json
import socket
import threading
import time
from unittest.mock import patch

from cdss_rpc import call_tool


class WorkflowRunner:
    def __init__(self, progress=None):
        self.progress = progress
        self.row = None
        self.method = None
        self.stage = "patient"
        self.stage_started = None

    def set_stage(self, stage):
        self.stage, self.stage_started = stage, time.perf_counter()
        if self.progress:
            self.progress.update(stage=stage)

    def on_node_complete(self, key, value):
        if self.row is None:
            return
        if key == "patient":
            self.row["patient_profile"] = value["patient"]
            self.set_stage("bounds")
        elif key == "policy":
            policy = value["policy"]
            policies = policy.get("policies", [policy])
            self.row["bounds"] = [{k: p[k] for k in ("parameter", "min", "max")} for p in policies]
            self.set_stage("proof")
        elif key == "proof":
            self.row["proof"] = value["proof"]
            self.row["proof_verified"] = value["proof"].get("verified")
            self.row["proof_s"] = value["timings"]["proof_ms"] / 1000
            self.set_stage("decision")
        elif key == "decision":
            self.row["final_decision"] = value["decision"]

    def retrieve(self, query):
        from evaluationbyW.evaluationby5 import digest
        self.row["queries"].append(query)
        self.set_stage("retrieval")
        start = time.perf_counter()
        try:
            name = "search_guidelines" if self.method == "chroma" else "search_guidelines_direct"
            result = call_tool(self.knowledge_url, name, {"condition": query, "k": 3}, timeout=120)
            if len(result["guidelines"]) != 3:
                raise ValueError("Expected exactly three retrieved chunks")
            self.row["sources"].append(result["sources"])
            self.row["retrieved_chunks"].append([digest(s.encode()) for s in result["guidelines"]])
            return result["guidelines"]
        except Exception:
            self.row["retrieval_failed"] = True
            raise
        finally:
            self.row["retrieval_s"] = (self.row["retrieval_s"] or 0) + time.perf_counter() - start
            self.set_stage("bounds")

    def on_model_output(self, text):
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            candidate = None
        self.row["model_outputs"].append({"raw_output": text, "parsed_candidate": candidate})
        self.row["generated_candidates"].append(candidate)

    def generate_policy(self, patient, use_rag=True):
        from rule_engine.policy_generator import generate_policy
        start = time.perf_counter()
        before = self.row["retrieval_s"] or 0
        try:
            policy = generate_policy(patient, use_rag=True, retriever=self.retrieve,
                                     strict=True, observer=self.on_model_output)
            self.row["generated_policies"].append(policy)
            return policy
        finally:
            self.row["bound_generation_s"] = (self.row["bound_generation_s"] or 0) + time.perf_counter() - start - ((self.row["retrieval_s"] or 0) - before)

    def run(self, patient_id, method):
        from evaluationbyW.evaluationby5 import LABELS
        self.method = method
        self.row = {"patient_id": patient_id, "method": method, "label": LABELS[method],
                    "retrieval_s": None, "bound_generation_s": None, "proof_s": None,
                    "sources": [], "retrieved_chunks": [], "queries": [], "bounds": None,
                    "generated_policies": [], "generated_candidates": [], "model_outputs": [],
                    "proof": None, "proof_verified": None, "final_decision": None,
                    "error": None, "error_stage": None}
        if self.progress:
            self.progress.update(patient_id=patient_id, method=LABELS[method])
        self.set_stage("patient")
        start = time.perf_counter()
        try:
            result = call_tool(self.coordinator_url, "run_cdss", {
                "patient_id": patient_id, "use_rag": True, "debug_sensor_values": False}, timeout=600)
            self.row["coordinator_timings_ms"] = result.get("timings", {})
            if result["decision"]["status"] == "UNABLE_TO_ASSESS":
                raise RuntimeError("Proof failed or is missing: " + json.dumps(result["proof"]))
        except Exception as exc:
            self.row["error"] = f"{type(exc).__name__}: {exc}"
            self.row["error_stage"] = "retrieval" if self.row.get("retrieval_failed") else self.stage
            if self.stage == "proof" and self.row["proof_s"] is None:
                self.row["proof_s"] = time.perf_counter() - self.stage_started
        self.row["total_workflow_s"] = time.perf_counter() - start
        return self.row


@contextlib.contextmanager
def services(knowledge, direct, progress=None):
    import uvicorn
    from patient_mcp.app import app as patient_app
    from device_agent.app import app as device_app
    from privacy_mcp.app import app as privacy_app
    import privacy_mcp.zkp_client as zkp
    import rule_engine.app as ruler
    import langgraph_coordinator.graph as nodes
    import langgraph_coordinator.app as coordinator
    runner = WorkflowRunner(progress)
    servers = []

    def start(app):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        servers.append((server, thread, sock))
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Evaluation service failed to start")
            time.sleep(0.02)
        return f"http://127.0.0.1:{port}"

    @knowledge.rpc.tool("search_guidelines_direct", "Exhaustive cosine retrieval without ChromaDB", {})
    def search_direct(condition, k=3):
        result = direct.search(condition, k)
        return {key: result[key] for key in ("guidelines", "sources")}

    try:
        patient_url = start(patient_app)
        device_url = start(device_app)
        privacy_url = start(privacy_app)
        runner.knowledge_url = start(knowledge.app)
        ruler_url = start(ruler.app)
        runner.coordinator_url = start(coordinator.app)
        with contextlib.ExitStack() as stack:
            for module, name, value in (
                (nodes, "EMR_MCP_URL", patient_url), (nodes, "RULER_AGENT_URL", ruler_url),
                (nodes, "PRIVACY_MCP_URL", privacy_url), (zkp, "DEVICE_AGENT_URL", device_url),
                (nodes, "EVALUATION_OBSERVER", runner.on_node_complete),
                (ruler, "generate_policy", runner.generate_policy),
            ):
                stack.enter_context(patch.object(module, name, value))
            yield runner
    finally:
        for server, _, _ in servers:
            server.should_exit = True
        for _, thread, sock in servers:
            thread.join(timeout=5)
            sock.close()
