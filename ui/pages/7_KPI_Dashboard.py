"""
KPI Dashboard — Revenue Cycle Key Performance Indicators

Displays:
  - Net Collection Rate, First Pass Resolution Rate, Days in AR, Denial Rate
  - AR Aging bucket chart
  - KPI trend over time (monthly/quarterly)
  - Traffic-light grading vs industry benchmarks
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from storage.file_store import list_files, ensure_db

st.title("🎯 KPI Dashboard")
st.caption("Revenue Cycle Key Performance Indicators — computed from all parsed 837P & 835 files")

ensure_db()

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_files = list_files()
    files_837 = [f for f in all_files if f["tx_type"] == "837P"]
    files_835 = [f for f in all_files if f["tx_type"] == "835"]

    if not files_837 and not files_835:
        st.info("No parsed files found.\nUpload 837P and 835 files first.")

    period = st.selectbox("Trend Period", ["Monthly", "Quarterly"], index=0)
    p_code = {"Monthly": "M", "Quarterly": "Q"}[period]

    dos_from = st.text_input("DOS From (YYYY-MM-DD):", "")
    dos_to   = st.text_input("DOS To   (YYYY-MM-DD):", "")

# ── Load data ─────────────────────────────────────────────────────────────────
from analytics.aggregator import get_claims_df, get_payments_df, get_adjustments_df
from analytics.kpi_engine import compute_kpis, kpi_trend, aging_dataframe

@st.cache_data(ttl=120, show_spinner=False)
def load_kpis(dos_from, dos_to):
    claims_df  = get_claims_df(dos_from=dos_from or None, dos_to=dos_to or None)
    pay_df     = get_payments_df()
    adj_df     = get_adjustments_df()
    return claims_df, pay_df, adj_df

with st.spinner("Computing KPIs…"):
    claims_df, pay_df, adj_df = load_kpis(dos_from, dos_to)

if claims_df.empty and pay_df.empty:
    st.info("📭 No data found. Parse some 837P and 835 files to see KPIs.")
    st.stop()

kpi = compute_kpis(claims_df, pay_df, adj_df)

# ── Top KPI metrics row ────────────────────────────────────────────────────────
st.subheader("Core Metrics")

c1, c2, c3, c4, c5 = st.columns(5)

def _fmt_pct(val):
    return f"{val:.1f}%" if val is not None else "N/A"

def _fmt_days(val):
    return f"{val:.1f}" if val is not None else "N/A"

with c1:
    ncr = kpi.net_collection_rate
    st.metric(
        "Net Collection Rate",
        _fmt_pct(ncr),
        help="Target: ≥ 95% | Formula: Payments ÷ (Billed − Contractual Adj)",
    )
    if ncr is not None:
        st.markdown(kpi.grade("net_collection_rate"))

with c2:
    fpr = kpi.first_pass_rate
    st.metric(
        "First Pass Rate",
        _fmt_pct(fpr),
        help="Target: ≥ 90% | Claims paid without rework on first submission",
    )
    if fpr is not None:
        st.markdown(kpi.grade("first_pass_rate"))

with c3:
    dar = kpi.days_in_ar
    st.metric(
        "Days in A/R",
        _fmt_days(dar),
        help="Target: < 40 days | Average age of outstanding claims",
    )
    if dar is not None:
        st.markdown(kpi.grade("days_in_ar"))

with c4:
    dr = kpi.denial_rate
    st.metric(
        "Denial Rate",
        _fmt_pct(dr),
        help="Target: < 5% | Claims denied on first submission",
    )
    if dr is not None:
        st.markdown(kpi.grade("denial_rate"))

with c5:
    rr = kpi.avg_reimbursement_rate
    st.metric(
        "Avg Reimbursement",
        _fmt_pct(rr),
        help="Amount paid ÷ Amount billed",
    )
    if rr is not None:
        st.markdown(kpi.grade("avg_reimbursement_rate"))

st.divider()

# ── Financial summary ─────────────────────────────────────────────────────────
st.subheader("Financial Summary")
fc1, fc2, fc3, fc4 = st.columns(4)
fc1.metric("Total Claims",        f"{kpi.total_claims:,}")
fc2.metric("Total Billed",        f"${kpi.total_billed:,.2f}")
fc3.metric("Total Paid",          f"${kpi.total_paid:,.2f}")
fc4.metric("Contractual Adj",     f"${kpi.total_contractual:,.2f}")

st.divider()

# ── AR Aging chart ────────────────────────────────────────────────────────────
st.subheader("📅 A/R Aging Buckets")

aging_df = aging_dataframe(kpi)

if not aging_df.empty and aging_df["count"].sum() > 0:
    col_a, col_b = st.columns(2)

    with col_a:
        fig_aging_count = px.bar(
            aging_df,
            x="bucket", y="count",
            title="Claims by Age Bucket",
            color="bucket",
            color_discrete_sequence=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
            labels={"count": "# Claims", "bucket": ""},
        )
        fig_aging_count.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig_aging_count, use_container_width=True)

    with col_b:
        fig_aging_amt = px.bar(
            aging_df,
            x="bucket", y="total_billed",
            title="Billed Amount by Age Bucket",
            color="bucket",
            color_discrete_sequence=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
            labels={"total_billed": "Total Billed ($)", "bucket": ""},
        )
        fig_aging_amt.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig_aging_amt, use_container_width=True)

    # Aging table
    aging_display = aging_df.copy()
    aging_display["total_billed"] = aging_display["total_billed"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(aging_display, use_container_width=True, hide_index=True)
else:
    st.info("No aging data available — requires 837P files with service dates.")

st.divider()

# ── KPI Trend chart ───────────────────────────────────────────────────────────
st.subheader(f"📈 KPI Trend ({period})")

trend_df = kpi_trend(pay_df, adj_df, period=p_code)

if not trend_df.empty:
    fig_trend = go.Figure()

    if "avg_reimb_pct" in trend_df.columns:
        fig_trend.add_trace(go.Scatter(
            x=trend_df["period"], y=trend_df["avg_reimb_pct"],
            mode="lines+markers", name="Reimbursement Rate %",
            line=dict(color="#1f77b4", width=2),
        ))

    if "denial_rate_pct" in trend_df.columns:
        fig_trend.add_trace(go.Scatter(
            x=trend_df["period"], y=trend_df["denial_rate_pct"],
            mode="lines+markers", name="Denial Rate %",
            line=dict(color="#e74c3c", width=2, dash="dash"),
            yaxis="y2",
        ))

    fig_trend.update_layout(
        title="Reimbursement Rate vs Denial Rate Over Time",
        xaxis_title="Period",
        yaxis=dict(title="Reimbursement Rate (%)", ticksuffix="%"),
        yaxis2=dict(title="Denial Rate (%)", overlaying="y", side="right", ticksuffix="%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    if "total_paid" in trend_df.columns:
        fig_pay = px.bar(
            trend_df, x="period", y="total_paid",
            title="Total Paid by Period",
            labels={"total_paid": "Total Paid ($)", "period": "Period"},
            color_discrete_sequence=["#1f77b4"],
        )
        fig_pay.update_layout(height=300)
        st.plotly_chart(fig_pay, use_container_width=True)
else:
    st.info("KPI trend requires 835 ERA files with payment dates.")

st.divider()

# ── Benchmark reference ───────────────────────────────────────────────────────
with st.expander("📊 Industry Benchmarks Reference"):
    bench_data = {
        "KPI":                   ["Net Collection Rate", "First Pass Resolution Rate",
                                  "Days in A/R", "Denial Rate", "Avg Reimbursement Rate"],
        "Your Value":            [
            _fmt_pct(kpi.net_collection_rate),
            _fmt_pct(kpi.first_pass_rate),
            _fmt_days(kpi.days_in_ar),
            _fmt_pct(kpi.denial_rate),
            _fmt_pct(kpi.avg_reimbursement_rate),
        ],
        "Industry Target":       ["≥ 95%", "≥ 90%", "< 40 days", "< 5%", "≥ 70%"],
        "Warning Threshold":     ["85–94%", "75–89%", "40–60 days", "5–10%", "50–69%"],
        "Critical Threshold":    ["< 85%",  "< 75%",  "> 60 days", "> 10%", "< 50%"],
    }
    st.dataframe(pd.DataFrame(bench_data), use_container_width=True, hide_index=True)
