"""Stable presentation view models, formatting, and chart-data preparation."""

from typing import Any

import pandas as pd


def format_rate(value: Any) -> str:
    """Format decimal rate as percentage with four decimal places."""
    try:
        return f"{float(value):.4%}"
    except (TypeError, ValueError):
        return str(value)


def format_pp(value: Any, signed: bool = False) -> str:
    """Format percentage-point value already stored in pp units."""
    try:
        return f"{float(value):{'+.4f' if signed else '.4f'}} 个百分点"
    except (TypeError, ValueError):
        return str(value)


def format_number(value: Any) -> str:
    """Format ordinary numeric value with four decimal places."""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def format_pvalue(value: Any) -> str:
    """Format p-value with four decimal places."""
    return format_number(value)


def prepare_metric_card(result: dict[str, Any]) -> dict[str, Any] | None:
    """Create UI metric card without relying on DataFrame columns."""
    evidence = result.get("evidence") or {}
    value = evidence.get("target_rate")
    if value is None:
        return None
    return {
        "label": "发布率",
        "metric": result.get("metric", "publishing_rate"),
        "date": result.get("date"),
        "raw_value": float(value),
        "formatted_value": format_rate(value),
    }


def prepare_trend_view(result: dict[str, Any]) -> dict[str, Any] | None:
    """Create ordered trend view model and zoomed axis domain from evidence."""
    evidence = result.get("evidence") or {}
    rows = evidence.get("trend") or []
    if not isinstance(rows, list) or not rows:
        return None
    try:
        chart_rows = sorted(
            [{"date": str(row["date"]), "rate_percent": float(row["publishing_rate"]) * 100} for row in rows],
            key=lambda row: row["date"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    rates = [row["rate_percent"] for row in chart_rows]
    start, end = chart_rows[0], chart_rows[-1]
    return {
        "rows": chart_rows,
        "axis_domain": trend_axis_domain(rates),
        "start": format_rate(start["rate_percent"] / 100),
        "end": format_rate(end["rate_percent"] / 100),
        "change": format_pp(end["rate_percent"] - start["rate_percent"], signed=True),
        "maximum": format_rate(max(rates) / 100),
        "minimum": format_rate(min(rates) / 100),
    }


def trend_axis_domain(values: list[float]) -> list[float] | None:
    """Return padded percent-scale domain so short-term movement stays visible."""
    if not values:
        return None
    lower, upper = min(values), max(values)
    value_range = upper - lower
    padding = max(value_range * 0.2, 0.02)
    return [lower - padding, upper + padding]


def prepare_segment_view(result: dict[str, Any]) -> dict[str, Any] | None:
    """Create sorted negative contribution rows for a horizontal bar chart."""
    evidence = result.get("evidence") or {}
    segments = evidence.get("top_negative_segments") or []
    if not isinstance(segments, list):
        return None
    rows = []
    for item in segments:
        try:
            rows.append({"segment": str(item["segment"]), "contribution_pp": float(item["contribution_pp"]), "contribution_label": format_pp(item["contribution_pp"], signed=True)})
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return None
    return {"rows": sorted(rows, key=lambda row: row["contribution_pp"])}


def prepare_experiment_view(result: dict[str, Any]) -> dict[str, Any] | None:
    """Create compact experiment presentation; chart only with control/treatment values."""
    experiments = (result.get("evidence") or {}).get("experiments") or []
    if not isinstance(experiments, list):
        return None
    ab_experiments = [item for item in experiments if item.get("type") == "ab_test"]
    if not ab_experiments:
        return None
    item = ab_experiments[0]
    view = {
        "name": item.get("experiment_name", "未命名实验"),
        "lift": format_pp(item.get("lift_pp"), signed=True),
        "p_value": format_pvalue(item.get("p_value")),
        "verdict": item.get("verdict", "当前证据不足"),
        "should_render_chart": False,
        "chart_rows": [],
    }
    if item.get("control_rate") is not None and item.get("treatment_rate") is not None:
        view["should_render_chart"] = True
        view["chart_rows"] = [
            {"group": "Control", "rate_percent": float(item["control_rate"]) * 100},
            {"group": "Treatment", "rate_percent": float(item["treatment_rate"]) * 100},
        ]
    return view
