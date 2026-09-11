import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.intent_parser import parse_intent


class FakeLLM:
    def __init__(self, response: str | None):
        self.response = response

    def generate(self, prompt: str) -> str | None:
        return self.response


class IntentParserTests(unittest.TestCase):
    def test_anomaly_question_uses_fast_path(self) -> None:
        result = parse_intent("为什么 8 月 31 日发布率下降？", "2026-08-30", FakeLLM(None))
        self.assertEqual(result["intent"], "anomaly_diagnosis")
        self.assertEqual(result["metric"], "publishing_rate")
        self.assertEqual(result["date"], "2026-08-31")
        self.assertEqual(result["parser_source"], "rule_fast_path")

    def test_conflicting_rule_keywords_delegate_to_llm(self) -> None:
        response = json.dumps({"intent": "experiment_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        result = parse_intent("为什么实验导致发布率下降？", "2026-08-31", FakeLLM(response))
        self.assertEqual(result["parser_source"], "llm")
        self.assertEqual(result["intent"], "experiment_analysis")

    def test_experiment_question_uses_rule_fallback(self) -> None:
        result = parse_intent("当天有没有实验影响发布率？", "2026-08-31", FakeLLM(None))
        self.assertEqual(result["intent"], "experiment_analysis")
        self.assertEqual(result["date"], "2026-08-31")

    def test_invalid_llm_json_falls_back_without_crashing(self) -> None:
        result = parse_intent("发布率是多少？", "2026-08-31", FakeLLM("not-json"))
        self.assertEqual(result["intent"], "metric_query")
        self.assertEqual(result["parser_source"], "rule_fast_path")

    def test_valid_llm_json_is_used(self) -> None:
        response = json.dumps({"intent": "trend_analysis", "metric": "publishing_rate", "date": "2026-08-30"})
        result = parse_intent("最近表现如何？", "2026-08-31", FakeLLM(response))
        self.assertEqual(result["intent"], "trend_analysis")
        self.assertEqual(result["parser_source"], "llm")
    def test_unknown_llm_intent_falls_back(self) -> None:
        response = json.dumps({"intent": "random_analysis", "metric": "publishing_rate", "date": "2026-08-31"})
        result = parse_intent("发布率是多少？", "2026-08-31", FakeLLM(response))
        self.assertEqual(result["intent"], "metric_query")
        self.assertEqual(result["parser_source"], "rule_fast_path")

    def test_unavailable_client_falls_back_to_trend(self) -> None:
        result = parse_intent("最近发布率趋势怎么样？", "2026-08-31", FakeLLM(None))
        self.assertEqual(result["intent"], "trend_analysis")
        self.assertEqual(result["parser_source"], "rule_fast_path")

    def test_invalid_llm_date_falls_back_to_selected_date(self) -> None:
        response = json.dumps({"intent": "metric_query", "metric": "publishing_rate", "date": "August 31"})
        result = parse_intent("发布率是多少？", "2026-08-31", FakeLLM(response))
        self.assertEqual(result["date"], "2026-08-31")
        self.assertEqual(result["parser_source"], "rule_fast_path")

    def test_fenced_llm_json_never_crashes(self) -> None:
        response = "```json\n{\"intent\": \"anomaly_diagnosis\", \"metric\": \"publishing_rate\", \"date\": \"2026-08-31\"}\n```"
        result = parse_intent("为什么发布率下降？", "2026-08-31", FakeLLM(response))
        self.assertEqual(result["intent"], "anomaly_diagnosis")
        self.assertEqual(result["parser_source"], "rule_fast_path")


if __name__ == "__main__":
    unittest.main()
