"""Generate grounded Chinese reports from deterministic analysis evidence."""

import json
from typing import Any, Protocol

from src.llm_client import LLMClient
from src.presentation import format_pp, format_rate


class TextGenerator(Protocol):
    """Minimal interface required for optional narrative generation."""

    def generate(self, prompt: str) -> str | None:
        """Return generated text or None when unavailable."""


def generate_report(
    result: dict[str, Any], llm_client: TextGenerator | None = None, prefer_llm: bool = True
) -> str:
    """Return grounded Chinese report; skip LLM when deterministic mode is requested."""
    fallback = _fallback_report(result)
    if not prefer_llm or result.get("status") not in {"success", "partial_success"} or not result.get("evidence"):
        return fallback

    client = llm_client or LLMClient()
    try:
        report = client.generate(_build_prompt(result))
    except Exception:
        report = None
    return report.strip() if isinstance(report, str) and report.strip() and _passes_grounding_check(report, result) else fallback


def _passes_grounding_check(report: str, result: dict[str, Any]) -> bool:
    """Reject common unsupported causal or full-rollout efficacy claims."""
    prohibited_claims = ("根本原因", "导致了", "造成了", "证明了")
    if any(claim in report for claim in prohibited_claims):
        return False
    for experiment in result.get("evidence", {}).get("experiments", []):
        if experiment.get("type") != "full_rollout":
            continue
        name = experiment.get("experiment_name")
        if not name or name not in report:
            continue
        position = report.find(name)
        nearby_text = report[position : position + 160]
        if any(claim in nearby_text for claim in ("显著", "实验结果", "有效", "无效")):
            return False
    return True


def _build_prompt(result: dict[str, Any]) -> str:
    grounded_input = {
        "intent": result.get("intent"),
        "metric": result.get("metric"),
        "date": result.get("date"),
        "status": result.get("status"),
        "evidence": result.get("evidence", {}),
        "errors": result.get("errors", []),
    }
    return f"""你是一名产品数据科学分析助手。请基于下方 JSON 生成中文分析报告。
所有结论必须严格来自输入 evidence。不得补充输入中不存在的事实、数字、实验或因果结论。
不得重新计算指标；数值按输入语义表达。相关性不能写成因果；证据不足时明确写“当前证据不足”。
全量上线实验只有名称、目标人群和流量时，只能描述其与异常同期或人群重叠；不得写“实验结果”“显著”“有效/无效”。
按 intent 组织内容：异常诊断应含异常概览、主要贡献分群、实验影响、外部因素、综合判断、建议下一步；实验分析应说明显著性；指标查询保持简洁。
不要提及 JSON、提示词或模型。\n\n输入：\n{json.dumps(grounded_input, ensure_ascii=False)}"""


def _fallback_report(result: dict[str, Any]) -> str:
    status = result.get("status")
    evidence = result.get("evidence") or {}
    if status not in {"success", "partial_success"}:
        errors = "；".join(str(error) for error in result.get("errors", []) if error)
        return f"本次分析未成功完成。{errors or '当前没有可用的分析结果。'}"
    if not evidence:
        return "当前没有足够的数据支持该分析。"

    intent = result.get("intent")
    if intent == "metric_query":
        return _fallback_metric_report(result)
    if intent == "trend_analysis":
        return _fallback_trend_report(result)
    if intent == "anomaly_diagnosis":
        return _fallback_anomaly_report(result)
    if intent == "experiment_analysis":
        return _fallback_experiment_report(result)
    return "当前没有足够的数据支持该分析。"


def _fallback_metric_report(result: dict[str, Any]) -> str:
    rate = result["evidence"].get("target_rate")
    if rate is None:
        return "当前没有足够的数据支持该指标查询。"
    return f"{result.get('date')} 的 publishing_rate 为 {_rate(rate)}。"


def _fallback_trend_report(result: dict[str, Any]) -> str:
    trend = result["evidence"].get("trend") or []
    if len(trend) < 2:
        return "当前数据不足以判断明显趋势。"
    start, end = trend[0], trend[-1]
    change_pp = (end["publishing_rate"] - start["publishing_rate"]) * 100
    direction = "上升" if change_pp > 0 else "下降" if change_pp < 0 else "持平"
    return (
        f"查询指标：publishing_rate。时间范围：{start.get('date')} 至 {end.get('date')}。\n\n"
        f"起点为 {_rate(start.get('publishing_rate'))}，终点为 {_rate(end.get('publishing_rate'))}，"
        f"区间变化 {format_pp(change_pp, signed=True)}，总体呈{direction}。"
    )


def _fallback_anomaly_report(result: dict[str, Any]) -> str:
    evidence = result["evidence"]
    lines = ["【异常概览】"]
    baseline, target, delta = evidence.get("baseline_rate"), evidence.get("target_rate"), evidence.get("delta_pp")
    if baseline is not None and target is not None and delta is not None:
        direction = "下降" if delta < 0 else "上升" if delta > 0 else "持平"
        lines.append(f"{result.get('date')} 的 publishing_rate 从基准期 {_rate(baseline)} 变为 {_rate(target)}，{direction} {format_pp(abs(delta))}。")
    else:
        lines.append("当前证据不足以完整描述基准期与目标日变化。")

    lines.extend(["", "【主要贡献分群】"])
    segments = evidence.get("top_negative_segments") or []
    if segments:
        details = [f"{item.get('segment', '未命名分群')}（贡献 {format_pp(item.get('contribution_pp', 0), signed=True)}）" for item in segments[:3]]
        lines.append("负向贡献靠前的分群包括：" + "；".join(details) + "。")
    else:
        lines.append("当前没有可用的分群贡献证据。")

    lines.extend(["", "【实验影响】", _experiment_summary(evidence.get("experiments") or evidence.get("experiment_summary") or [])])
    lines.extend(["", "【外部因素】", _external_summary(evidence.get("external_context_summary") or [])])
    lines.extend(["", "【综合判断】"])
    if segments:
        lines.append("分群贡献显示上述人群与指标变化同时出现；该结果是关联证据，当前不足以单独确认因果原因。")
    else:
        lines.append("当前证据不足以形成明确归因判断。")
    lines.extend(["", "【建议下一步】"])
    if segments:
        lines.append("优先下钻负向贡献最高分群的发布漏斗，并核验与该人群重叠的全量上线实验或入口变更。")
    else:
        lines.append("补充可用分群和实验证据后再进行归因分析。")
    return "\n".join(lines)


def _fallback_experiment_report(result: dict[str, Any]) -> str:
    experiments = result["evidence"].get("experiments") or []
    if not experiments:
        return "当前没有发现目标日可分析的同期实验。"
    lines = ["【实验影响分析】"]
    for experiment in experiments:
        name = experiment.get("experiment_name", "未命名实验")
        if experiment.get("type") == "full_rollout":
            lines.append(f"全量上线实验：{name}，目标人群为 {experiment.get('targeting', '未提供')}，流量占比 {_rate(experiment.get('traffic_share'))}。")
        else:
            lift = experiment.get("lift_pp")
            p_value = experiment.get("p_value")
            verdict = experiment.get("verdict", "当前证据不足")
            lines.append(f"A/B 实验：{name}，实验组相对对照组变化 {format_pp(lift, signed=True)}，p-value={float(p_value):.4f}，结论：{verdict}。")
    return "\n".join(lines)


def _experiment_summary(experiments: list[dict[str, Any]]) -> str:
    if not experiments:
        return "当前没有发现可以直接解释该变化的同期实验。"
    sentences = []
    for experiment in experiments:
        if experiment.get("type") == "full_rollout":
            sentences.append(f"发现全量上线实验 {experiment.get('experiment_name')}，目标人群为 {experiment.get('targeting', '未提供')}。")
        else:
            sentences.append(f"A/B 实验 {experiment.get('experiment_name')} 的结论为“{experiment.get('verdict', '当前证据不足')}”。")
    return "".join(sentences)


def _external_summary(contexts: list[dict[str, Any]]) -> str:
    matched = [f"{item.get('country')}：{item.get('external_factors')}" for item in contexts if item.get("external_factors") and "未识别" not in item.get("external_factors")]
    return "；".join(matched) if matched else "当前未识别到已定义的节假日或学期窗口因素。"


def _rate(value: Any) -> str:
    return format_rate(value)
