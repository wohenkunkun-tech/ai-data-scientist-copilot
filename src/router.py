"""Route validated analysis intents to deterministic analytics modules."""

from typing import Any

import pandas as pd

from src.diagnose import diagnose_publishing_rate, get_publishing_rate, get_publishing_rate_trend
from src.experiment_impact import query_experiment_impact
from src.external_factors import external_calendar_context

COUNTRIES = ["US", "BR", "JP", "GB", "DE"]
SUPPORTED_INTENTS = {"metric_query", "trend_analysis", "anomaly_diagnosis", "experiment_analysis"}


def run_analysis(parsed_intent: dict[str, str]) -> dict[str, Any]:
    """Run only deterministic modules required by a validated analysis intent."""
    intent = parsed_intent.get("intent")
    target_date = parsed_intent.get("date")
    metric = parsed_intent.get("metric", "publishing_rate")
    result = _result_base(intent, metric, target_date)

    if intent not in SUPPORTED_INTENTS:
        result["status"] = "error"
        result["errors"].append(f"Unsupported intent: {intent}")
        return result
    if metric != "publishing_rate" or not target_date:
        result["status"] = "error"
        result["errors"].append("Only publishing_rate with a target date is supported")
        return result

    try:
        if intent == "metric_query":
            result["evidence"] = {"target_rate": get_publishing_rate(target_date)}
        elif intent == "trend_analysis":
            trend = get_publishing_rate_trend(target_date)
            if trend.empty:
                raise ValueError("No trend data returned")
            result["artifacts"]["trend"] = trend
            result["evidence"] = {"trend": _trend_records(trend)}
        elif intent == "anomaly_diagnosis":
            _run_anomaly_diagnosis(result, target_date)
        else:
            _run_experiment_analysis(result, target_date)
    except Exception as error:
        result["status"] = "error"
        result["errors"].append(str(error))
    return result


def _result_base(intent: str | None, metric: str, target_date: str | None) -> dict[str, Any]:
    return {"intent": intent, "metric": metric, "date": target_date, "status": "success", "evidence": {}, "artifacts": {}, "errors": []}


def _run_anomaly_diagnosis(result: dict[str, Any], target_date: str) -> None:
    diagnosis = diagnose_publishing_rate(target_date)
    top_segments = diagnosis.segment_diagnosis.head(5)
    result["artifacts"]["segment_diagnosis"] = diagnosis.segment_diagnosis
    result["evidence"] = {
        "baseline_rate": float(diagnosis.baseline_rate),
        "target_rate": float(diagnosis.target_rate),
        "delta_pp": float(diagnosis.delta_pp),
        "top_negative_segments": _segment_records(top_segments),
    }
    _add_experiment_evidence(result, target_date)
    _add_external_context(result, target_date)


def _run_experiment_analysis(result: dict[str, Any], target_date: str) -> None:
    _add_experiment_evidence(result, target_date)


def _add_experiment_evidence(result: dict[str, Any], target_date: str) -> None:
    try:
        rollouts, ab_results = query_experiment_impact(target_date)
        result["artifacts"]["rollouts"] = rollouts
        result["artifacts"]["ab_results"] = ab_results
        experiments = _experiment_records(rollouts, ab_results)
        result["evidence"]["experiments"] = experiments
        result["evidence"]["experiment_summary"] = experiments
        result["evidence"]["significant_negative_experiment"] = any(item.get("verdict") == "可能影响核心指标" for item in experiments)
    except Exception as error:
        _mark_partial(result, f"Experiment analysis unavailable: {error}")


def _add_external_context(result: dict[str, Any], target_date: str) -> None:
    try:
        context = external_calendar_context(target_date, COUNTRIES)
        result["artifacts"]["external_context"] = context
        records = _frame_records(context)
        result["evidence"]["external_context_summary"] = records
    except Exception as error:
        _mark_partial(result, f"External factors unavailable: {error}")


def _mark_partial(result: dict[str, Any], error: str) -> None:
    result["status"] = "partial_success"
    result["errors"].append(error)


def _trend_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"date": pd.Timestamp(row.date).date().isoformat(), "publishing_rate": float(row.publishing_rate)} for row in frame.itertuples(index=False)]


def _segment_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "dimension": row.dimension,
            "segment": row.segment,
            "contribution_pp": float(row.contribution_pp),
            "baseline_rate": float(row.baseline_rate),
            "target_rate": float(row.target_rate),
        }
        for row in frame.itertuples(index=False)
    ]


def _experiment_records(rollouts: pd.DataFrame, ab_results: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in rollouts.itertuples(index=False):
        records.append({"experiment_name": row.experiment_name, "type": "full_rollout", "targeting": row.targeting, "traffic_share": float(row.traffic_share)})
    for row in ab_results.itertuples(index=False):
        records.append({"experiment_name": row.experiment_name, "type": "ab_test", "traffic_share": float(row.traffic_share), "lift_pp": float(row.lift_pp), "p_value": float(row.p_value), "verdict": row.verdict})
    return records


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{column: _primitive(value) for column, value in row.items()} for row in frame.to_dict(orient="records")]


def _primitive(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value
