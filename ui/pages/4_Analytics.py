"""Cross-file analytics dashboard with Plotly charts."""
import streamlit as st
import pandas as pd
from storage.file_store import list_files, ensure_db

st.title("📈 Analytics Dashboard")

ensure_db()
files = list_files()
if not files:
    st.info("No files parsed yet.")
    st.stop()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    tx_filter  = st.selectbox("Transaction Type:", ["All","837P","835"])
    period     = st.selectbox("Period:", ["Monthly","Weekly","Quarterly"], index=0)
    period_map = {"Monthly":"M","Weekly":"W","Quarterly":"Q"}
    p_code     = period_map[period]

    if tx_filter == "All":
        file_ids = None
    else:
        matching = [f["id"] for f in files if f["tx_type"] == tx_filter]
        file_ids = matching if matching else None

    dos_from = st.text_input("DOS From (YYYY-MM-DD):", "")
    dos_to   = st.text_input("DOS To (YYYY-MM-DD):", "")

from analytics.trends import claims_by_period, payment_trend, ar_aging, payer_metrics
from analytics.denial_analyzer import denial_summary, top_denial_categories
from analytics.charts import (
    claims_volume_chart, denial_rate_chart, payer_mix_chart,
    denial_category_donut, ar_aging_chart
)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Volume", "💸 Payments & Denials", "🏥 Payer Mix",
    "⏱ AR Aging", "📉 Denial Details"
])

with tab1:
    vol_df = claims_by_period(p_code, file_ids=file_ids,
                               dos_from=dos_from or None, dos_to=dos_to or None)
    st.plotly_chart(claims_volume_chart(vol_df), use_container_width=True)
    if not vol_df.empty:
        st.dataframe(vol_df, use_container_width=True, hide_index=True)

with tab2:
    pay_df = payment_trend(p_code, file_ids=file_ids)
    st.plotly_chart(denial_rate_chart(pay_df), use_container_width=True)
    if not pay_df.empty:
        st.dataframe(pay_df, use_container_width=True, hide_index=True)

with tab3:
    payer_df = payer_metrics(file_ids=file_ids)
    st.plotly_chart(payer_mix_chart(payer_df), use_container_width=True)
    if not payer_df.empty:
        st.dataframe(payer_df.sort_values("total_billed", ascending=False),
                     use_container_width=True, hide_index=True)

with tab4:
    age_df = ar_aging(file_ids=file_ids)
    st.plotly_chart(ar_aging_chart(age_df), use_container_width=True)
    if not age_df.empty:
        st.dataframe(age_df, use_container_width=True, hide_index=True)

with tab5:
    denial_df  = denial_summary(file_ids=file_ids)
    top_cat_df = top_denial_categories(file_ids=file_ids)
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(denial_category_donut(top_cat_df), use_container_width=True)
    with col2:
        if not denial_df.empty:
            st.dataframe(denial_df[["reason_code","description","category","count","total_amount","pct_of_total"]],
                         use_container_width=True, hide_index=True)

# Analytics PDF export
st.divider()
if st.button("📄 Export Analytics Summary PDF"):
    from exporters.pdf.pdf_835 import export_pdf_summary
    from analytics.aggregator import get_claims_df, get_payments_df
    claims_df  = get_claims_df(file_ids=file_ids)
    payments_df = get_payments_df(file_ids=file_ids)
    denial_df  = denial_summary(file_ids=file_ids)
    with st.spinner("Generating PDF..."):
        try:
            pdf = export_pdf_summary(claims_df, payments_df, denial_df)
            st.download_button("⬇️ Download Analytics PDF", data=pdf,
                               file_name="analytics_summary.pdf", mime="application/pdf")
        except Exception as e:
            st.error(f"PDF export failed: {e}")
