import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.presentation import (
    format_pp,
    format_rate,
    prepare_experiment_view,
    prepare_metric_card,
    prepare_segment_view,
    prepare_trend_view,
    trend_axis_domain,
)


class PresentationTests(unittest.TestCase):
    def test_metric_card_uses_stable_contract(self) -> None:
        card = prepare_metric_card({"metric": "publishing_rate", "date": "2026-08-31", "evidence": {"target_rate": 0.0451666666667}})
        self.assertEqual(card["formatted_value"], "4.5167%")
        self.assertNotIn("publishing_rate", card["formatted_value"])

    def test_missing_visualization_data_returns_none(self) -> None:
        self.assertIsNone(prepare_metric_card({"evidence": {}}))
        self.assertIsNone(prepare_trend_view({"evidence": {}}))
        self.assertIsNone(prepare_segment_view({"evidence": {}}))

    def test_trend_view_is_ordered_and_percent_scaled(self) -> None:
        result = {"evidence": {"trend": [
            {"date": "2026-08-31", "publishing_rate": 0.0451666666667},
            {"date": "2026-08-25", "publishing_rate": 0.044},
        ]}}
        view = prepare_trend_view(result)
        self.assertEqual(len(view["rows"]), 2)
        self.assertEqual(view["rows"][0]["date"], "2026-08-25")
        self.assertEqual(view["rows"][1]["rate_percent"], 4.51666666667)
        self.assertEqual(view["end"], "4.5167%")

    def test_axis_domain_has_padding(self) -> None:
        domain = trend_axis_domain([4.4, 4.6])
        self.assertLess(domain[0], 4.4)
        self.assertGreater(domain[1], 4.6)

    def test_segments_are_negative_sorted_and_formatted(self) -> None:
        view = prepare_segment_view({"evidence": {"top_negative_segments": [
            {"segment": "Android", "contribution_pp": -0.1659},
            {"segment": "US | new | Android", "contribution_pp": -0.2066},
        ]}})
        self.assertEqual(view["rows"][0]["segment"], "US | new | Android")
        self.assertEqual(view["rows"][0]["contribution_label"], "-0.2066 个百分点")

    def test_single_lift_does_not_render_experiment_chart(self) -> None:
        view = prepare_experiment_view({"evidence": {"experiments": [{"type": "ab_test", "experiment_name": "A", "lift_pp": -0.1122, "p_value": 0.7526, "verdict": "未发现显著负向影响"}]}})
        self.assertFalse(view["should_render_chart"])

    def test_control_treatment_enables_experiment_chart(self) -> None:
        view = prepare_experiment_view({"evidence": {"experiments": [{"type": "ab_test", "experiment_name": "A", "lift_pp": -0.1, "p_value": 0.2, "control_rate": 0.05, "treatment_rate": 0.04}]}})
        self.assertTrue(view["should_render_chart"])
        self.assertEqual(len(view["chart_rows"]), 2)

    def test_formatting(self) -> None:
        self.assertEqual(format_rate(0.0451666666667), "4.5167%")
        self.assertEqual(format_pp(-0.2066), "-0.2066 个百分点")


if __name__ == "__main__":
    unittest.main()
