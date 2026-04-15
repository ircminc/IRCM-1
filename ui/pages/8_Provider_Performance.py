"""
Provider Performance Dashboard

Per-NPI breakdown of:
  - Revenue metrics (billed, paid, collection rate)
  - Denial rate and top denial reasons
  - CPT code utilization
  - Provider comparison vs practice average
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from storage.file_store import list_files, ensure_db

st.title("👨‍⚕️ Provider Performance")
st.caption("Revenue, denial, and utilization metrics broken down by billing/rendering provider NPI")

ensure_db()

# ── Check data availability ───────────────────────────────────────────────────
all_files = list_files()
files_837  = [f for f in all_files if f["tx_type"] == "837P"]
if not files_837:
    st.info("📭 No 837P files parsed yet. Upload claim files to see provider performance.")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
from analytics.aggregator    import get_claims_df, get_payments_df, get_adjustments_df, get_service_lines_df
from analytics.provider_perf import (
    provider_revenue_metrics, provider_denial_analysis,
    provider_cpt_utilization, provider_comparison,
)

@st.cache_data(ttl=120, show_spinner=False)
def load_all():
    claims_df  = get_claims_df()
    pay_df     = get_payments_df()
    adj_df     = get_adjustments_df()
    # Service lines need claim IDs
    if not claims_df.empty and "id" in claims_df.columns:
        claim_ids = claims_df["id"].tolist()
        sl_df = get_service_lines_df(claim_ids)
    else:
        sl_df = pd.DataFrame()
    return claims_df, pay_df, adj_df, sl_df

with st.spinner("Loading provider data…"):
    claims_df, pay_df, adj_df, sl_df = load_all()

if claims_df.empty:
    st.info("No claim data found.")
    st.stop()

# ── Compute metrics ───────────────────────────────────────────────────────────
revenue_df = provider_revenue_metrics(claims_df, pay_df)
denial_df  = provider_denial_analysis(claims_df, adj_df, pay_df)
cpt_df     = provider_cpt_utilization(sl_df, claims_df)
compare_df = provider_comparison(revenue_df, denial_df)

# ── Practice summary metrics ──────────────────────────────────────────────────
st.subheader("Practice Overview")

p1, p2, p3, p4 = st.columns(4)
p1.metric("Providers",        f"{len(revenue_df):,}" if not revenue_df.empty else "N/A")
p2.metric("Total Billed",     f"${float(claims_df['total_billed'].sum()):,.2f}" if "total_billed" in claims_df.columns else "N/A")
p3.metric("Avg Claims/Provider",
          f"{len(claims_df) // max(len(revenue_df), 1):,}" if not revenue_df.empty else "N/A")
if not denial_df.empty and "denial_rate_pct" in denial_df.columns:
    avg_dr = denial_df["denial_rate_pct"].mean()
    p4.metric("Avg Denial Rate", f"{avg_dr:.1f}%")
else:
    p4.metric("Avg Denial Rate", "N/A")

st.divider()

# ── Provider Revenue Table ────────────────────────────────────────────────────
st.subheader("💰 Revenue by Provider")

if not revenue_df.empty:
    # Format for display
    rev_display = revenue_df.copy()
    for col in ("total_billed", "total_paid", "avg_claim_value"):
        if col in rev_display.columns:
            rev_display[col] = rev_display[col].apply(
                lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A"
            )
    if "collection_rate_pct" in rev_display.columns:
        rev_display["collection_rate_pct"] = rev_display["collection_rate_pct"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )

    st.dataframe(rev_display, use_container_width=True, hide_index=True)

    # Revenue bar chart
    if "total_billed" in revenue_df.columns and len(revenue_df) > 1:
        top_n = min(15, len(revenue_df))
        chart_df = revenue_df.head(top_n).copy()
        npi_labels = chart_df.get("provider_npi", chart_df.index.astype(str))

        fig_rev = px.bar(
            chart_df,
            x="provider_npi",
            y="total_billed",
            title=f"Total Billed — Top {top_n} Providers",
            labels={"total_billed": "Total Billed ($)", "provider_npi": "Provider NPI"},
            color="total_billed",
            color_continuous_scale="Blues",
        )
        fig_rev.update_layout(height=380, coloraxis_showscale=False)
        st.plotly_chart(fig_rev, use_container_width=True)
else:
    st.info("No revenue data — check that 837P files include billing provider NPI.")

st.divider()

# ── Provider Denial Comparison ────────────────────────────────────────────────
st.subheader("🚫 Denial Rate by Provider")

if not denial_df.empty and "denial_rate_pct" in denial_df.columns:
    # Color bars by threshold: > 10% = red, 5-10% = orange, < 5% = green
    denial_df["color"] = denial_df["denial_rate_pct"].apply(
        lambda x: "#e74c3c" if x > 10 else ("#f39c12" if x > 5 else "#2ecc71")
    )

    fig_denial = px.bar(
        denial_df.head(20),
        x="provider_npi",
        y="denial_rate_pct",
        title="Denial Rate by Provider (%)",
        labels={"denial_rate_pct": "Denial Rate (%)", "provider_npi": "Provider NPI"},
        color="denial_rate_pct",
        color_continuous_scale=[[0, "#2ecc71"], [0.05, "#f39c12"], [1.0, "#e74c3c"]],
        range_color=[0, max(denial_df["denial_rate_pct"].max(), 15)],
    )
    # Add 5% and 10% benchmark lines
    fig_denial.add_hline(y=5,  line_dash="dot", line_color="orange",
                         annotation_text="5% target", annotation_position="top right")
    fig_denial.add_hline(y=10, line_dash="dot", line_color="red",
                         annotation_text="10% warning", annotation_position="top right")
    fig_denial.update_layout(height=380, coloraxis_showscale=False)
    st.plotly_chart(fig_denial, use_container_width=True)

    denial_display = denial_df[
        [c for c in ["provider_npi", "provider_name", "total_claims", "denied_claims",
                     "denial_rate_pct", "top_denial_reason"] if c in denial_df.columns]
    ].copy()
    if "denial_rate_pct" in denial_display.columns:
        denial_display["denial_rate_pct"] = denial_display["denial_rate_pct"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )
    st.dataframe(denial_display, use_container_width=True, hide_index=True)
else:
    st.info("Denial data requires both 837P and 835 files.")

st.divider()

# ── Provider CPT Utilization ──────────────────────────────────────────────────
st.subheader("🔬 CPT Utilization by Provider")

if not cpt_df.empty:
    # Provider selector
    providers = sorted(cpt_df["provider_npi"].unique().tolist())
    selected_npi = st.selectbox(
        "Select Provider NPI:",
        options=["All Providers"] + providers,
    )

    if selected_npi == "All Providers":
        display_df = cpt_df
    else:
        display_df = cpt_df[cpt_df["provider_npi"] == selected_npi]

    if not display_df.empty:
        top_cpts = display_df.groupby("cpt_hcpcs")["procedure_count"].sum() \
            .sort_values(ascending=False).head(15)

        fig_cpt = px.bar(
            top_cpts.reset_index(),
            x="cpt_hcpcs",
            y="procedure_count",
            title=f"Top CPT Codes — {selected_npi}",
            labels={"procedure_count": "Procedure Count", "cpt_hcpcs": "CPT/HCPCS"},
            color="procedure_count",
            color_continuous_scale="Teal",
        )
        fig_cpt.update_layout(height=350, coloraxis_showscale=False)
        st.plotly_chart(fig_cpt, use_container_width=True)

        st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("CPT utilization requires 837P files with service line detail.")

st.divider()

# ── Provider Comparison Table ─────────────────────────────────────────────────
st.subheader("📊 Provider Comparison vs Practice Average")

if not compare_df.empty:
    # Highlight above/below average
    display_cols = [c for c in [
        "provider_npi", "provider_name", "claim_count", "total_billed",
        "collection_rate_pct", "denial_rate_pct", "vs_avg_collection", "vs_avg_denial",
    ] if c in compare_df.columns]

    comp_display = compare_df[display_cols].copy()
    for col in ("total_billed",):
        if col in comp_display.columns:
            comp_display[col] = comp_display[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
    for col in ("collection_rate_pct", "denial_rate_pct", "vs_avg_collection", "vs_avg_denial"):
        if col in comp_display.columns:
            comp_display[col] = comp_display[col].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")

    st.dataframe(comp_display, use_container_width=True, hide_index=True)
    st.caption("vs_avg columns show deviation from practice mean. Positive collection = above average (good). Positive denial = above average denial rate (bad).")
