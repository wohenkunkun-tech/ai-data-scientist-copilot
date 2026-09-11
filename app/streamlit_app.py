from datetime import date
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from src.intent_parser import parse_intent
from src.presentation import format_pp, format_rate, prepare_experiment_view, prepare_metric_card, prepare_segment_view, prepare_trend_view
from src.report_generator import generate_report
from src.router import run_analysis

DEFAULT_DATE = date(2026, 8, 31)
EXAMPLE_QUESTIONS = [
    "2026-08-31 的发布率是多少？",
    "分析一下最近 7 天发布率的趋势",
    "为什么 2026-08-31 的发布率下降了？",
    "最近的实验是否可能影响发布率？",
]

st.set_page_config(page_title="AI Product Data Analyst", page_icon="📊", layout="wide")


def run_query(query: str, answer_mode: str) -> tuple[dict[str, str], dict[str, Any], str, dict[str, float]]:
    """Run pipeline and capture parser, analysis, report, and total timings."""
    total_started = perf_counter()
    parse_started = perf_counter()
    parsed_intent = parse_intent(query, DEFAULT_DATE)
    parse_ms = (perf_counter() - parse_started) * 1000
    analysis_started = perf_counter()
    result = run_analysis(parsed_intent)
    analysis_ms = (perf_counter() - analysis_started) * 1000
    report_started = perf_counter()
    report = generate_report(result, prefer_llm=answer_mode == "AI Enhanced")
    report_ms = (perf_counter() - report_started) * 1000
    return parsed_intent, result, report, {
        "parse_ms": parse_ms,
        "analysis_ms": analysis_ms,
        "report_ms": report_ms,
        "total_ms": (perf_counter() - total_started) * 1000,
    }


def render_visualizations(result: dict[str, Any]) -> None:
    """Render fail-soft user-facing views from stable presentation contracts."""
    try:
        intent = result.get("intent")
        if intent == "metric_query":
            card = prepare_metric_card(result)
            if card:
                st.metric(card["label"], card["formatted_value"])
                st.caption(f"日期：{card['date']}")
        elif intent == "trend_analysis":
            _render_trend(result)
        elif intent == "anomaly_diagnosis":
            _render_anomaly(result)
        elif intent == "experiment_analysis":
            _render_experiment(result)
    except Exception as error:
        print(f"Visualization failed: {error}")
        st.caption("图表暂时无法展示，文字分析结果不受影响。")


def _render_trend(result: dict[str, Any]) -> None:
    view = prepare_trend_view(result)
    if not view:
        return
    start, end, change = st.columns(3)
    start.metric("起始发布率", view["start"])
    end.metric("结束发布率", view["end"])
    change.metric("区间变化", view["change"])
    st.markdown("#### 7 日发布率趋势")
    st.vega_lite_chart(
        view["rows"],
        {
            "height": 300,
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "date", "type": "ordinal", "axis": {"title": None, "labelAngle": 0, "labelExpr": "slice(datum.label, 5)"}},
                "y": {"field": "rate_percent", "type": "quantitative", "scale": {"domain": view["axis_domain"], "zero": False}, "axis": {"title": "发布率（%）", "format": ".4f"}},
                "tooltip": [{"field": "date", "type": "ordinal", "title": "日期"}, {"field": "rate_percent", "type": "quantitative", "title": "发布率（%）", "format": ".4f"}],
            },
        },
        use_container_width=True,
    )


def _render_anomaly(result: dict[str, Any]) -> None:
    evidence = result.get("evidence") or {}
    current, baseline, delta = st.columns(3)
    current.metric("当前发布率", format_rate(evidence.get("target_rate")))
    baseline.metric("基准期发布率", format_rate(evidence.get("baseline_rate")))
    delta_value = evidence.get("delta_pp")
    delta.metric("变化", f"{'下降' if delta_value is not None and delta_value < 0 else '上升'} {format_pp(abs(delta_value))}" if delta_value is not None else "未提供")
    view = prepare_segment_view(result)
    if not view:
        return
    height = min(max(len(view["rows"]) * 48 + 50, 180), 320)
    st.markdown("#### 主要负向分群贡献")
    st.vega_lite_chart(
        view["rows"],
        {
            "height": height,
            "mark": "bar",
            "encoding": {
                "y": {"field": "segment", "type": "nominal", "sort": {"field": "contribution_pp", "order": "ascending"}, "axis": {"title": None}},
                "x": {"field": "contribution_pp", "type": "quantitative", "axis": {"title": "贡献（百分点）", "format": ".4f"}},
                "tooltip": [{"field": "segment", "type": "nominal", "title": "分群"}, {"field": "contribution_pp", "type": "quantitative", "title": "贡献（百分点）", "format": ".4f"}],
            },
        },
        use_container_width=True,
    )


def _render_experiment(result: dict[str, Any]) -> None:
    view = prepare_experiment_view(result)
    if not view:
        return
    name, lift, p_value, verdict = st.columns(4)
    name.metric("实验", view["name"])
    lift.metric("发布率变化", view["lift"])
    p_value.metric("p-value", view["p_value"])
    verdict.metric("统计判断", view["verdict"])
    if view["should_render_chart"]:
        st.vega_lite_chart(
            view["chart_rows"],
            {"height": 240, "mark": "bar", "encoding": {"x": {"field": "group", "type": "nominal", "axis": {"title": None}}, "y": {"field": "rate_percent", "type": "quantitative", "axis": {"title": "发布率（%）", "format": ".4f"}}, "tooltip": [{"field": "group", "type": "nominal"}, {"field": "rate_percent", "type": "quantitative", "title": "发布率（%）", "format": ".4f"}]}},
            use_container_width=True,
        )


def render_analysis_details(parsed_intent: dict[str, str], result: dict[str, Any], execution: dict[str, float] | None = None, answer_mode: str | None = None) -> None:
    """Render inspectable evidence and stored execution timing."""
    with st.expander("Analysis Details"):
        st.markdown("#### Parsed Intent")
        st.markdown(
            f"Intent: `{parsed_intent.get('intent', 'unknown')}`  \n"
            f"Metric: `{parsed_intent.get('metric', 'unknown')}`  \n"
            f"Date: `{parsed_intent.get('date', 'unknown')}`  \n"
            f"Parser: `{parsed_intent.get('parser_source', 'unknown')}`"
        )
        if execution is not None:
            st.markdown("#### Execution")
            st.markdown(
                f"Parser Source: `{parsed_intent.get('parser_source', 'unknown')}`  \n"
                f"Answer Mode: `{answer_mode or 'unknown'}`  \n"
                f"Parse: {execution.get('parse_ms', 0):.2f} ms  \n"
                f"Analysis: {execution.get('analysis_ms', 0):.2f} ms  \n"
                f"Report: {execution.get('report_ms', 0):.2f} ms  \n"
                f"Total: {execution.get('total_ms', 0):.2f} ms"
            )
        st.markdown("#### Structured Evidence")
        st.json(result.get("evidence", {}))
        errors = result.get("errors", [])
        if errors:
            st.markdown("#### Notes")
            st.warning("部分辅助分析未完成：" + "；".join(str(error) for error in errors))


def render_message(message: dict[str, Any]) -> None:
    """Render a stored chat message and optional evidence details."""
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and "parsed_intent" in message:
            if message.get("result", {}).get("status") != "success":
                st.warning("部分分析未能完成，以下结论基于当前可用数据。")
            render_visualizations(message["result"])
            render_analysis_details(
                message["parsed_intent"],
                message["result"],
                message.get("execution"),
                message.get("answer_mode"),
            )


def add_analysis_to_history(query: str, answer_mode: str) -> None:
    """Execute a query safely and append both chat turns to session history."""
    st.session_state.messages.append({"role": "user", "content": query})
    try:
        with st.spinner("正在理解问题并运行数据分析……"):
            parsed_intent, result, report, execution = run_query(query, answer_mode)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": report,
                "parsed_intent": parsed_intent,
                "result": result,
                "execution": execution,
                "answer_mode": answer_mode,
            }
        )
    except Exception as error:
        print(f"Analysis pipeline failed: {error}")
        st.session_state.messages.append(
            {"role": "assistant", "content": "本次分析未能完成。请尝试换一种问法后重试。"}
        )


if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("About")
    st.write("AI Product Data Analyst")
    st.markdown("#### Supported Questions")
    st.markdown("• Metric lookup\n• Trend analysis\n• Anomaly diagnosis\n• Experiment analysis")
    st.markdown("#### Architecture")
    st.caption("Natural Language → Intent Parser → Analysis Router → Evidence → Grounded Report")
    st.markdown("#### Safety")
    st.caption("Answers use structured analysis evidence. Unsupported conclusions fall back to deterministic reports.")
    answer_mode = st.radio("Answer mode", ("Fast", "AI Enhanced"), index=0)
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("AI Product Data Analyst")
st.caption("通过自然语言查询产品指标、趋势、异常归因与实验影响。")
st.caption("Question → Intent Understanding → Analysis Router → Data Evidence → Grounded Report")

if not st.session_state.messages:
    st.markdown("#### Example Questions")
    columns = st.columns(2)
    selected_example = None
    for index, example in enumerate(EXAMPLE_QUESTIONS):
        if columns[index % 2].button(example, key=f"example_{index}", use_container_width=True):
            selected_example = example
else:
    selected_example = None

for message in st.session_state.messages:
    render_message(message)

query = st.chat_input("输入数据问题，例如：为什么 2026-08-31 的发布率下降了？")
query_to_run = query or selected_example
if query_to_run and query_to_run.strip():
    add_analysis_to_history(query_to_run.strip(), answer_mode)
    st.rerun()
