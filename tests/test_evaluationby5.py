import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evaluationbyW.evaluationby5 import DirectSearch, bounds_equal, collect_patients, save_results
from rule_engine import policy_generator
from langgraph_coordinator import graph


class RetrievalComparisonTests(unittest.TestCase):
    def test_resume_rejects_out_of_order_checkpoint(self):
        from evaluationbyW.resume_full_workflow import resume
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "manifest.json").write_text("{}", encoding="utf-8")
            (out / "patient_order.json").write_text(json.dumps([
                {"patient_id": "1"}, {"patient_id": "2"}]), encoding="utf-8")
            rows = [{"patient_id": "1", "method": "chroma"},
                    {"patient_id": "2", "method": "chroma"},
                    {"patient_id": "2", "method": "direct"}]
            (out / "patient_results.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contiguous"):
                resume(out, 1e-6)

    def test_direct_search_checks_every_vector_and_normalizes_magnitude(self):
        chunks = [SimpleNamespace(page_content=str(i), metadata={"source": f"{i}.pdf"}) for i in range(4)]
        embeddings = Mock()
        embeddings.embed_documents.return_value = [[1, 1], [0, 1], [-1, 0], [100, 0]]
        embeddings.embed_query.return_value = [1, 0]
        direct = DirectSearch(chunks, embeddings)
        self.assertEqual(direct.search("query", 2)["guidelines"], ["3", "0"])
        direct.search("query", 2)
        embeddings.embed_documents.assert_called_once()
        self.assertEqual(embeddings.embed_query.call_count, 2)

    def test_tolerance_does_not_hide_parameter_difference(self):
        a = [{"parameter": "systolic_bp", "min": 100, "max": 130}]
        self.assertTrue(bounds_equal(a, [dict(a[0], max=130.0000001)], 1e-6))
        self.assertFalse(bounds_equal(a, [dict(a[0], max=131)], 1e-6))
        self.assertFalse(bounds_equal(a, [dict(a[0], parameter="heart_rate")], 1e-6))

    def test_all_distinct_patient_records_are_included(self):
        records, provenance = collect_patients()
        self.assertEqual(len(records), 200)
        self.assertEqual(len({p["patient_id"] for p in provenance}), 200)
        self.assertEqual(sum(p["emr_default_condition"] for p in provenance), 0)

    def test_strict_generation_never_falls_back(self):
        client = Mock()
        client.chat.return_value = {"message": {"content": '{"parameter":"unknown","min":10,"max":20}'}}
        with patch.dict(os.environ, {"CDSS_RAG": "1", "CDSS_EVAL": "1"}), \
                patch.object(policy_generator.ollama, "Client", return_value=client), \
                patch.object(policy_generator, "fallback_policy", side_effect=AssertionError("Fallback called")), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                policy_generator.generate_policy({"age": 60, "condition": "hypertension"}, retriever=lambda q: ["guideline"], strict=True)

    def test_shared_workflow_reaches_real_coordinator_decision_and_keeps_errors(self):
        from fastapi import FastAPI, Request
        from cdss_rpc import MCPJsonRpcServer
        from evaluationbyW.full_workflow import services
        import patient_mcp.app as patient
        import privacy_mcp.app as privacy
        knowledge = SimpleNamespace(app=FastAPI(), rpc=MCPJsonRpcServer("test-knowledge"))
        @knowledge.app.post("/rpc")
        async def handle(request: Request):
            return await knowledge.rpc.handle(request)
        @knowledge.rpc.tool("search_guidelines", "Fixture corpus", {})
        def search(condition, k=3):
            return {"guidelines": ["a", "b", "c"], "sources": ["a.pdf"] * 3}
        direct = Mock()
        direct.search.return_value = search("hypertension")
        client = Mock()
        client.chat.return_value = {"message": {"content": '{"parameter":"systolic_bp","min":100,"max":130}'}}
        with patch.dict(os.environ, {"CDSS_RAG": "1", "CDSS_EVAL": "1"}), \
                patch.object(patient, "get_patient_by_id", return_value={"id": "test", "age": 60, "condition": "hypertension"}), \
                patch.object(privacy, "generate_and_verify_proof", return_value={"verified": True, "status": "NORMAL"}), \
                patch.object(policy_generator.ollama, "Client", return_value=client), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                services(knowledge, direct) as runner:
            result = runner.run("test", "direct")
            self.assertIsNone(result["error"])
            self.assertEqual(result["final_decision"]["status"], "IN_RANGE")
            self.assertTrue(result["proof_verified"])
            self.assertIn("total_ms", result["coordinator_timings_ms"])
            chroma_result = runner.run("test", "chroma")
            self.assertEqual(chroma_result["bounds"], result["bounds"])
            direct.search.side_effect = ValueError("retrieval failed")
            failed = runner.run("test", "direct")
            self.assertIn("retrieval failed", failed["error"])
            self.assertIsNone(failed["bounds"])
            self.assertIsNone(failed["proof_s"])
            self.assertIsNotNone(failed["retrieval_s"])

    def test_failed_pairs_are_not_identical_or_zero_duration_successes(self):
        rows = []
        for order in (1, 2):
            for position, method in enumerate(("chroma", "direct"), 1):
                failed = order == 2
                rows.append({"patient_id": str(order), "order": order, "method": method,
                             "within_pair_order": position, "error": "bad patient" if failed else None,
                             "bounds": None if failed else [{"parameter": "heart_rate", "min": 60, "max": 100}],
                             "final_decision": None if failed else {"status": "IN_RANGE"},
                             "retrieved_chunks": [] if failed else [["same"]],
                             "retrieval_s": None if failed else 0.1, "bound_generation_s": None if failed else 0.5,
                             "proof_s": None if failed else 0.1, "total_workflow_s": 0.01 if failed else float(position)})
        with tempfile.TemporaryDirectory() as directory:
            rows.sort(key=lambda r: r["method"])  # Separate complete method passes.
            summary = save_results(Path(directory), rows, {"limitations": []}, 1e-6)
            self.assertEqual(summary["paired_success_count"], 1)
            self.assertEqual(summary["identical_bounds"], 1)
            self.assertEqual(summary["bounds_unavailable"], 1)
            self.assertEqual(summary["identical_decisions"], 1)
            self.assertEqual(summary["methods"]["chroma"]["failures"], 1)
            self.assertEqual(summary["methods"]["chroma"]["paired_successful"]["total_workflow_s"]["mean"], 1)
            self.assertEqual(summary["methods"]["chroma"]["all_attempts"]["retrieval_s"]["n"], 1)
            self.assertTrue((Path(directory) / "ragNorag.png").is_file())


if __name__ == "__main__":
    unittest.main()
