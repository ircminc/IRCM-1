"""Browse parsed data per transaction type."""
import streamlit as st
import pandas as pd
from storage.file_store import list_files, ensure_db
from core.parser import parse_edi_file
import io

st.set_page_config(page_title="Data Explorer", layout="wide")
st.title("🔍 Data Explorer")

ensure_db()
files = list_files()
if not files:
    st.info("No files parsed yet. Go to Upload & Parse first.")
    st.stop()

# File selector
file_opts = {f"{f['filename']} (#{f['id']} · {f['tx_type']})": f["id"] for f in files}
selected_label = st.selectbox("Select a parsed file:", list(file_opts.keys()))
file_id   = file_opts[selected_label]
file_info = next(f for f in files if f["id"] == file_id)
tx_type   = file_info["tx_type"]

st.caption(f"TX Type: **{tx_type}** · Records: **{file_info['record_count']}** · Parsed: **{file_info['upload_ts']}**")

# Pull from DB for 837P and 835; for others, show raw parse result if cached
if tx_type == "837P":
    from analytics.aggregator import get_claims_df, get_service_lines_df
    claims_df = get_claims_df(file_ids=[file_id])
    if claims_df.empty:
        st.warning("No claim data found in database.")
    else:
        tabs = st.tabs(["Claims", "Service Lines"])
        with tabs[0]:
            st.dataframe(claims_df, use_container_width=True, hide_index=True)
        with tabs[1]:
            claim_ids = claims_df["id"].tolist() if "id" in claims_df.columns else []
            sl_df = get_service_lines_df(claim_ids)
            st.dataframe(sl_df, use_container_width=True, hide_index=True)

elif tx_type == "835":
    from analytics.aggregator import get_payments_df, get_adjustments_df
    pay_df = get_payments_df(file_ids=[file_id])
    adj_df = get_adjustments_df(file_ids=[file_id])
    tabs   = st.tabs(["Claim Payments", "Adjustments"])
    with tabs[0]:
        st.dataframe(pay_df, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(adj_df, use_container_width=True, hide_index=True)

else:
    st.info(f"Live DB explorer for {tx_type} is not yet implemented. Use Export to view data.")
