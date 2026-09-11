import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.presentation import format_pp, format_rate
from src.report_generator import generate_report
from src.router import run_analysis


class FakeLLM:
    def __init__(self, response: str | None):
        self.response = response

    def generate(self, prompt: str) -> str | None:
        return self.response


class ReportGeneratorTests(unittest.TestCase):
    def test_metric_query_report(self) -> None:
        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        report = generate_report(result, FakeLLM(None))
        self.assertIsInstance(report, str)
        self.assertIn("2026-08-31", report)
        self.assertIn("publishing_rate", report)

    def test_trend_report(self) -> None:
        result = run_analysis({"intent": "trend_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        report = generate_report(result, FakeLLM(None))
        self.assertIn("时间范围", report)
        self.assertIn("总体呈", report)

    def test_anomaly_report_includes_key_evidence_numbers(self) -> None:
        result = run_analysis({"intent": "anomaly_diagnosis", "metric": "publishing_rate", "date": "2026-08-31"})
        report = generate_report(result, FakeLLM(None))
        self.assertIn(format_rate(result['evidence']['baseline_rate']), report)
        self.assertIn(format_pp(abs(result['evidence']['delta_pp'])), report)
        self.assertIn("US | new | Android", report)
        self.assertIn("【实验影响】", report)
        self.assertIn("【外部因素】", report)

    def test_experiment_report(self) -> None:
        result = run_analysis({"intent": "experiment_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        report = generate_report(result, FakeLLM(None))
        self.assertIn("【实验影响分析】", report)
        self.assertIn("创作者信息流刷新", report)

    def test_none_llm_uses_fallback(self) -> None:
        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertIn("publishing_rate", generate_report(result, FakeLLM(None)))

    def test_empty_llm_uses_fallback(self) -> None:
        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertIn("publishing_rate", generate_report(result, FakeLLM("")))

    def test_failed_status_does_not_call_llm(self) -> None:
        result = {"intent": "metric_query", "status": "error", "evidence": {}, "errors": ["No data"]}
        report = generate_report(result, FakeLLM("should not appear"))
        self.assertIn("未成功完成", report)
        self.assertIn("No data", report)

    def test_empty_evidence_returns_message(self) -> None:
        result = {"intent": "metric_query", "status": "success", "evidence": {}, "errors": []}
        self.assertIn("没有足够的数据", generate_report(result, FakeLLM(None)))

    def test_partial_evidence_does_not_crash(self) -> None:
        result = {"intent": "anomaly_diagnosis", "date": "2026-08-31", "status": "success", "evidence": {"target_rate": 0.04}, "errors": []}
        report = generate_report(result, FakeLLM(None))
        self.assertIsInstance(report, str)
        self.assertIn("当前证据不足", report)

    def test_fast_mode_skips_llm(self) -> None:
        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertIn("publishing_rate", generate_report(result, FakeLLM("模型报告"), prefer_llm=False))

    def test_four_decimal_formatting(self) -> None:
        self.assertEqual(format_rate(0.123456), "12.3456%")
        self.assertEqual(format_pp(-1.23456, signed=True), "-1.2346 个百分点")

        result = run_analysis({"intent": "metric_query", "metric": "publishing_rate", "date": "2026-08-31"})
        self.assertEqual(generate_report(result, FakeLLM("模型报告")), "模型报告")


if __name__ == "__main__":
    unittest.main()
