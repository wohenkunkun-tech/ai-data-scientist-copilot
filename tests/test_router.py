import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.router import run_analysis


class RouterTests(unittest.TestCase):
    def test_metric_query_returns_target_rate_only(self) -> None:
        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertEqual(result["status"], "success")
        self.assertIn("target_rate", result["evidence"])
        self.assertNotIn("segment_diagnosis", result["artifacts"])
        self._assert_no_dataframes(result["evidence"])

    def test_trend_analysis_returns_ordered_trend(self) -> None:
        result = run_analysis({"intent": "trend_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        trend = result["evidence"]["trend"]
        self.assertEqual(result["status"], "success")
        self.assertGreater(len(trend), 1)
        self.assertEqual([item["date"] for item in trend], sorted(item["date"] for item in trend))
        self._assert_no_dataframes(result["evidence"])

    def test_anomaly_diagnosis_returns_complete_evidence(self) -> None:
        result = run_analysis({"intent": "anomaly_diagnosis", "metric": "publishing_rate", "date": "2026-08-31"})
        evidence = result["evidence"]
        for key in ("baseline_rate", "target_rate", "delta_pp", "top_negative_segments", "experiment_summary", "external_context_summary"):
            self.assertIn(key, evidence)
        self.assertIn("segment_diagnosis", result["artifacts"])
        self._assert_no_dataframes(evidence)

    def test_experiment_analysis_runs_independently(self) -> None:
        result = run_analysis({"intent": "experiment_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertIn("experiments", result["evidence"])
        self.assertNotIn("segment_diagnosis", result["artifacts"])
        self._assert_no_dataframes(result["evidence"])

    def test_unknown_intent_returns_error(self) -> None:
        result = run_analysis({"intent": "unknown", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["errors"])

    def _assert_no_dataframes(self, value: object) -> None:
        if isinstance(value, pd.DataFrame):
            self.fail("evidence contains DataFrame")
        if isinstance(value, dict):
            for child in value.values():
                self._assert_no_dataframes(child)
        if isinstance(value, list):
            for child in value:
                self._assert_no_dataframes(child)


if __name__ == "__main__":
    unittest.main()
