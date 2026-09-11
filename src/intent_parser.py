"""Parse supported product-analysis questions into validated task intents."""

import json
import re
from datetime import date, datetime
from typing import Protocol

from src.llm_client import LLMClient

ALLOWED_INTENTS = {
    "metric_query",
    "trend_analysis",
    "anomaly_diagnosis",
    "experiment_analysis",
}
DEFAULT_METRIC = "publishing_rate"


class TextGenerator(Protocol):
    """Small interface required from an LLM client."""

    def generate(self, prompt: str) -> str | None:
        """Return generated text, or None when unavailable."""


def parse_intent(question: str, fallback_date: str | date, llm_client: TextGenerator | None = None) -> dict[str, str]:
    """Return a validated intent, using a conservative rule fast path first."""
    normalized_fallback = _normalize_date(fallback_date)
    fast_intent = _high_confidence_rule_intent(question)
    if fast_intent is not None:
        return {
            "intent": fast_intent,
            "metric": DEFAULT_METRIC,
            "date": _extract_date(question, normalized_fallback),
            "parser_source": "rule_fast_path",
        }

    client = llm_client or LLMClient()
    prompt = _build_prompt(question, normalized_fallback)

    try:
        llm_result = _validate_llm_result(client.generate(prompt), normalized_fallback)
    except Exception:
        llm_result = None
    if llm_result is not None:
        return {**llm_result, "parser_source": "llm"}

    return {
        "intent": _rule_intent(question),
        "metric": DEFAULT_METRIC,
        "date": _extract_date(question, normalized_fallback),
        "parser_source": "rule_fallback",
    }


def _high_confidence_rule_intent(question: str) -> str | None:
    """Classify only unambiguous supported requests without an LLM call."""
    normalized = question.lower()
    matches = {
        "experiment_analysis": any(keyword in normalized for keyword in ("实验", "ab", "a/b", "experiment")),
        "anomaly_diagnosis": any(keyword in normalized for keyword in ("为什么", "原因", "下降", "异常", "下跌", "诊断")),
        "trend_analysis": any(keyword in normalized for keyword in ("趋势", "trend")),
        "metric_query": any(keyword in normalized for keyword in ("多少", "是什么", "几", "查询")),
    }
    intents = [intent for intent, matched in matches.items() if matched]
    return intents[0] if len(intents) == 1 else None


def _build_prompt(question: str, fallback_date: str) -> str:
    return f"""You classify one product analytics question. Return only a JSON object.
No explanation, Markdown, code fence, or extra fields.
Allowed intent values: metric_query, trend_analysis, anomaly_diagnosis, experiment_analysis.
metric must be publishing_rate.
date must be YYYY-MM-DD. If question has no explicit date, use {fallback_date}.
Question: {question}
Required JSON shape: {{\"intent\": \"anomaly_diagnosis\", \"metric\": \"publishing_rate\", \"date\": \"{fallback_date}\"}}"""


def _validate_llm_result(raw: str | None, fallback_date: str) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or set(parsed) != {"intent", "metric", "date"}:
        return None
    if parsed["intent"] not in ALLOWED_INTENTS or parsed["metric"] != DEFAULT_METRIC:
        return None
    try:
        normalized_date = _normalize_date(parsed["date"])
    except (TypeError, ValueError):
        return None
    return {"intent": parsed["intent"], "metric": DEFAULT_METRIC, "date": normalized_date or fallback_date}


def _normalize_date(value: str | date) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _extract_date(question: str, fallback_date: str) -> str:
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", question)
    chinese_match = re.search(r"(?:(20\d{2})年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", question)
    try:
        if iso_match:
            return date(*map(int, iso_match.groups())).isoformat()
        if chinese_match:
            year, month, day = chinese_match.groups()
            return date(int(year or fallback_date[:4]), int(month), int(day)).isoformat()
    except ValueError:
        pass
    return fallback_date


def _rule_intent(question: str) -> str:
    normalized = question.lower()
    if any(keyword in normalized for keyword in ("实验", "ab", "a/b", "experiment")):
        return "experiment_analysis"
    if any(keyword in normalized for keyword in ("趋势", "最近", "trend")):
        return "trend_analysis"
    if any(keyword in normalized for keyword in ("为什么", "原因", "下降", "异常", "下跌", "诊断")):
        return "anomaly_diagnosis"
    return "metric_query"
