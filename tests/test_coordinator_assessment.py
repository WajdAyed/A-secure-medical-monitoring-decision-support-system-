import unittest

from langgraph_coordinator.graph import summarize_proof


class CoordinatorAssessmentTests(unittest.TestCase):
    def test_verified_membership_is_in_range(self):
        self.assertEqual(
            summarize_proof({"status": "NORMAL", "verified": True})["status"],
            "IN_RANGE",
        )

    def test_device_alert_requests_review(self):
        self.assertEqual(summarize_proof({"status": "ALERT", "verified": False})["status"], "OUT_OF_RANGE")

    def test_failed_or_unverified_proof_is_unknown(self):
        for proof in ({"status": "PROOF_FAILED"}, {"status": "NORMAL", "verified": False}, {}):
            with self.subTest(proof=proof):
                self.assertEqual(summarize_proof(proof)["status"], "UNABLE_TO_ASSESS")

    def test_multi_measurement_failure_is_not_hidden_by_alert(self):
        proof = {"status": "ALERT", "measurements": [
            {"result": {"status": "ALERT", "verified": False}},
            {"result": {"status": "PROOF_FAILED", "verified": False}},
        ]}
        self.assertEqual(summarize_proof(proof)["status"], "UNABLE_TO_ASSESS")

    def test_multi_measurement_all_verified(self):
        proof = {"measurements": [
            {"result": {"status": "NORMAL", "verified": True}},
            {"result": {"status": "NORMAL", "verified": True}},
        ]}
        self.assertEqual(summarize_proof(proof)["status"], "IN_RANGE")
