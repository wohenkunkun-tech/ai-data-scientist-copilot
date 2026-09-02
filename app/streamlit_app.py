from datetime import date
from pathlib import Path
import sys

import plotly.express as px
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from src.diagnose import diagnose_publishing_rate
from src.experiment_impact import query_experiment_impact
from src.external_factors import external_calendar_context

st.set_page_config(page_title="AI Data Scientist Copilot", page_icon="📊", layout="wide")

st.title("AI Data Scientist Copilot")
st.caption("MVP · 发布率异常诊断 · 本地合成产品事件数据")

question = st.text_input("业务问题", value="为什么昨天发布率下降？")
target_date = st.date_input(
    "目标日期",
    value=date(2026, 8, 31),
    min_value=date(2026, 8, 8),
    max_value=date(2026, 8, 31),
    help="当前合成数据覆盖 2026-08-01 至 2026-08-31；诊断需要前 7 天基准期，因此可选 2026-08-08 至 2026-08-31。",
)

if st.button("开始诊断", type="primary"):
    result = diagnose_publishing_rate(str(target_date))
    delta_direction = "下降" if result.delta_pp < 0 else "上升"

    st.subheader(question)
    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("基准期发布率", f"{result.baseline_rate:.2%}")
    metric_2.metric("目标日发布率", f"{result.target_rate:.2%}")
    metric_3.metric("变化", f"{result.delta_pp:+.2f}pp", delta=f"{delta_direction} {abs(result.delta_pp):.2f}pp", delta_color="inverse")

    st.subheader("异常归因")
    top_segments = result.segment_diagnosis.head(10).copy()
    chart = px.bar(
        top_segments.sort_values("contribution_pp"),
        x="contribution_pp",
        y="segment",
        color="dimension",
        orientation="h",
        labels={"contribution_pp": "对整体变化贡献（pp）", "segment": "分群"},
        title="负向贡献最大的分群",
    )
    chart.update_layout(showlegend=False, height=440)
    st.plotly_chart(chart, use_container_width=True)

    primary = top_segments.iloc[0]
    st.subheader("初步业务结论")
    st.markdown(
        f"""
发布率从 **{result.baseline_rate:.2%}** 变为 **{result.target_rate:.2%}**，{delta_direction} **{abs(result.delta_pp):.2f}pp**。

最大异常分群是 **{primary['segment']}**：发布率从 **{primary['baseline_rate']:.2%}** 变为 **{primary['target_rate']:.2%}**，对整体变化贡献 **{primary['contribution_pp']:.2f}pp**。

建议优先检查该分群的发布漏斗、客户端版本和发布入口曝光。
        """
    )

    st.subheader("实验影响排查")
    rollouts, ab_results = query_experiment_impact(str(target_date))

    st.markdown("#### 1. 异动期间全量上线实验")
    if rollouts.empty:
        st.success("未发现目标日处于全量上线状态的实验。")
    else:
        st.warning("发现与异动日期重叠的全量上线实验。需优先核验目标人群、上线时间与漏斗变更。")
        st.dataframe(rollouts, use_container_width=True, hide_index=True)

    st.markdown("#### 2. 高流量内部 A/B 实验")
    if ab_results.empty:
        st.success("未发现目标日活跃的 A/B 实验。")
    else:
        ab_display = ab_results.copy()
        for column in ["control_rate", "treatment_rate"]:
            ab_display[column] = ab_display[column].map("{:.2%}".format)
        ab_display["lift_pp"] = ab_display["lift_pp"].map("{:+.2f}pp".format)
        ab_display["p_value"] = ab_display["p_value"].map("{:.4f}".format)
        st.dataframe(ab_display, use_container_width=True, hide_index=True)
        st.caption("判定规则：仅当实验仍在运行、流量较高、实验组相对对照组显著负向（p < 0.05）时，标记为可能影响核心指标。")

    st.subheader("外部因素对齐")
    st.caption("覆盖当前数据中的 US、BR、JP、GB、DE 法定节假日；学生假期为国家级近似窗口，不能替代州/学区校历。")
    calendar_context = external_calendar_context(str(target_date), ["US", "BR", "JP", "GB", "DE"])
    st.dataframe(calendar_context, use_container_width=True, hide_index=True)

    with st.expander("查看归因明细"):
        display = result.segment_diagnosis.copy()
        for column in ["baseline_rate", "target_rate", "delta_rate", "target_user_share"]:
            display[column] = display[column].map("{:.2%}".format)
        display["contribution_pp"] = display["contribution_pp"].map("{:+.3f}".format)
        st.dataframe(display, use_container_width=True, hide_index=True)
