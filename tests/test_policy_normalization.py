import unittest

from rule_engine.policy_generator import fallback_policy, normalize_policy


class NormalizePolicyTests(unittest.TestCase):
    def test_normalize_policy_extracts_numeric_bounds_from_nested_data(self):
        policy = {
            "parameter": "BMI",
            "safe_range": {"lower": 25, "upper": 30.5},
        }

        result = normalize_policy(policy)

        self.assertEqual(result["parameter"], "BMI")
        self.assertEqual(result["min"], 25)
        self.assertEqual(result["max"], 31)

    def test_normalize_policy_rejects_missing_bounds_without_creating_invalid_contract(self):
        policy = {"parameter": "BMI", "notes": "no range was returned"}

        with self.assertRaises(ValueError):
            normalize_policy(policy)

    def test_fallback_policy_covers_unsupported_anemia_condition(self):
        self.assertEqual(
            fallback_policy("anemia"),
            {"parameter": "hemoglobin", "min": 12, "max": 16},
        )
