"""CMS Medicare rate comparison dashboard."""
import streamlit as st
import pandas as pd
from storage.file_store import list_files, ensure_db

st.set_page_config(page_title="CMS Rates", layout="wide")
st.title("💊 CMS Medicare Rate Comparison")

ensure_db()

# CMS cache status
from config import settings
from pathlib import Path
import datetime

col1, col2 = st.columns(2)

with col1:
    st.subheader("Physician Fee Schedule (PFS)")
    pfs_files = sorted(settings.cache_dir.glob("pfs_*.parquet"), reverse=True)
    if pfs_files:
        latest = pfs_files[0]
        mtime  = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
        age    = (datetime.datetime.now() - mtime).days
        st.success(f"Cached: `{latest.name}` · Last updated {age} days ago")
    else:
        st.warning("PFS data not yet downloaded.")
    if st.button("Refresh PFS Now"):
        with st.spinner("Downloading PFS RVU file..."):
            try:
                from cms_rates.pfs_client import get_pfs_dataframe
                df = get_pfs_dataframe()
                if df is not None:
                    st.success(f"PFS loaded: {len(df):,} codes")
                else:
                    st.error("Could not download PFS data.")
            except Exception as e:
                st.error(str(e))

with col2:
    st.subheader("ASP Drug Pricing")
    asp_files = sorted(settings.cache_dir.glob("asp_*.parquet"), reverse=True)
    if asp_files:
        latest = asp_files[0]
        mtime  = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
        age    = (datetime.datetime.now() - mtime).days
        st.success(f"Cached: `{latest.name}` · Last updated {age} days ago")
    else:
        st.warning("ASP data not yet downloaded.")
    if st.button("Refresh ASP Now"):
        with st.spinner("Downloading ASP pricing file..."):
            try:
                from cms_rates.asp_client import get_asp_dataframe
                df, label = get_asp_dataframe()
                if df is not None:
                    st.success(f"ASP loaded: {len(df):,} codes ({label})")
                else:
                    st.error("Could not download ASP data.")
            except Exception as e:
                st.error(str(e))

st.divider()
st.subheader("CPT Code Rate Lookup")
cpt_input = st.text_input("Enter CPT/HCPCS code:", placeholder="e.g. 99213 or J0171")
if cpt_input:
    from cms_rates.rate_comparator import compare_service_line
    billed_input = st.number_input("Billed amount ($):", min_value=0.0, step=0.01, value=0.0)
    if st.button("Look Up Rate"):
        with st.spinner("Looking up..."):
            try:
                comp = compare_service_line(cpt_input.strip(), billed_amount=billed_input or None)
                flag_colors = {
                    "OVER_300PCT": "🔴", "UNDER_100PCT": "🟡",
                    "WITHIN_RANGE": "🟢", "NO_RATE": "⚪"
                }
                flag_icon = flag_colors.get(comp.flag, "⚪")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Non-Facility Rate", f"${comp.pfs_non_facility_rate:,.2f}" if comp.pfs_non_facility_rate else "N/A")
                c2.metric("Facility Rate",     f"${comp.pfs_facility_rate:,.2f}"     if comp.pfs_facility_rate     else "N/A")
                c3.metric("Work RVU",          f"{comp.work_rvu:.2f}"               if comp.work_rvu             else "N/A")
                c4.metric("ASP+6% Limit",      f"${comp.asp_payment_limit:,.2f}"    if comp.asp_payment_limit    else "N/A")
                if billed_input:
                    st.write(f"{flag_icon} **Rate Flag: {comp.flag}**")
                    if comp.vs_non_facility_pct is not None:
                        st.write(f"Billed is **{comp.vs_non_facility_pct:.1f}%** of Medicare non-facility rate")
                if comp.description:
                    st.write(f"**Description:** {comp.description}")
                st.caption(f"Source: {comp.rate_source}")
            except Exception as e:
                st.error(str(e))

st.divider()
st.subheader("Rate Comparison: Across Parsed 837P Files")
files_837 = [f for f in list_files() if f["tx_type"] == "837P"]
if not files_837:
    st.info("No 837P files parsed yet.")
else:
    file_opts = {f"{f['filename']} (#{f['id']})": f["id"] for f in files_837}
    selected  = st.selectbox("Select 837P file:", list(file_opts.keys()))
    file_id   = file_opts[selected]

    if st.button("Run CMS Rate Comparison"):
        from storage.models_db import Claim837, ServiceLine837
        from storage.database import get_session
        from cms_rates.rate_comparator import compare_claims

        with st.spinner("Loading claims and computing CMS comparisons..."):
            with get_session() as session:
                db_claims = session.query(Claim837).filter(Claim837.file_id == file_id).all()
                claims_list = []
                for c in db_claims:
                    sl_rows = session.query(ServiceLine837).filter(ServiceLine837.claim_id == c.id).all()
                    claims_list.append({
                        "claim_id": c.claim_id,
                        "service_lines": [
                            {"cpt_hcpcs": sl.cpt_hcpcs, "modifier_1": sl.modifier_1,
                             "billed_amount": sl.billed_amount, "line_number": sl.line_number}
                            for sl in sl_rows
                        ]
                    })
            try:
                comparisons = compare_claims(claims_list)
                df = pd.DataFrame(comparisons)
                if not df.empty:
                    flag_counts = df["flag"].value_counts()
                    col1,col2,col3,col4 = st.columns(4)
                    col1.metric("OVER 300%",  flag_counts.get("OVER_300PCT",0), delta_color="inverse")
                    col2.metric("UNDER 100%", flag_counts.get("UNDER_100PCT",0))
                    col3.metric("WITHIN RANGE", flag_counts.get("WITHIN_RANGE",0))
                    col4.metric("NO RATE DATA", flag_counts.get("NO_RATE",0))

                    from analytics.charts import cpt_charge_vs_cms_scatter
                    st.plotly_chart(cpt_charge_vs_cms_scatter(comparisons), use_container_width=True)

                    st.dataframe(
                        df[["cpt_hcpcs","modifier","description","billed_amount",
                            "pfs_non_facility_rate","vs_non_facility_pct","flag","rate_source"]],
                        use_container_width=True, hide_index=True,
                    )
            except Exception as e:
                st.error(f"CMS comparison failed: {e}")
