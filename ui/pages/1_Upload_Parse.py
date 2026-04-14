"""Upload and parse ANSI X12 EDI files."""
import io
import time
import streamlit as st
from core.parser import parse_edi_file
from core.parser.base_parser import detect_tx_type, _get_delimiters
from storage.file_store import save_parsed_file, list_files, delete_file

st.title("📂 Upload & Parse EDI Files")

TX_LABELS = {
    "837P": "837P — Professional Claims",
    "835":  "835 — Electronic Remittance Advice",
    "270":  "270 — Eligibility Inquiry",
    "271":  "271 — Eligibility Response",
    "276":  "276 — Claim Status Inquiry",
    "277":  "277 — Claim Status Response",
    "834":  "834 — Benefit Enrollment",
    "820":  "820 — Payment Order",
}

uploaded_files = st.file_uploader(
    "Drop one or more EDI files here",
    type=["edi","txt","x12","837","835","270","271","276","277","834","820"],
    accept_multiple_files=True,
    help="Supports all ANSI X12 HIPAA 5010 transaction sets. Max 200 MB per file.",
)

if uploaded_files:
    for uploaded in uploaded_files:
        with st.expander(f"📄 {uploaded.name}", expanded=True):
            raw_bytes = uploaded.read()
            file_io   = io.BytesIO(raw_bytes)

            # Auto-detect TX type
            try:
                tx_type = detect_tx_type(file_io)
                st.success(f"Detected: **{TX_LABELS.get(tx_type, tx_type)}**")
            except Exception as e:
                st.error(f"Could not detect TX type: {e}")
                continue

            col1, col2 = st.columns([3,1])
            with col1:
                st.caption(f"Size: {len(raw_bytes)/1024:.1f} KB")
            with col2:
                parse_btn = st.button(f"Parse {uploaded.name}", key=f"parse_{uploaded.name}")

            if parse_btn:
                with st.spinner("Parsing..."):
                    start = time.time()
                    try:
                        file_io.seek(0)
                        result = parse_edi_file(file_io)
                        elapsed = time.time() - start
                        file_id = save_parsed_file(
                            filename=uploaded.name,
                            tx_type=result["tx_type"],
                            parsed_result=result,
                            file_size=len(raw_bytes),
                        )
                        st.session_state[f"parsed_{uploaded.name}"] = result
                        st.session_state[f"file_id_{uploaded.name}"] = file_id

                        data = result.get("data", {})
                        tx   = result.get("tx_type","")
                        if tx == "837P":
                            n = len(data.get("claims",[]))
                            lines = sum(len(c.get("service_lines",[])) for c in data.get("claims",[]))
                            st.success(f"✅ Parsed in {elapsed:.2f}s — {n} claims, {lines} service lines — saved as File #{file_id}")
                        elif tx == "835":
                            n = len(data.get("claim_payments",[]))
                            st.success(f"✅ Parsed in {elapsed:.2f}s — {n} claim payments — saved as File #{file_id}")
                        else:
                            st.success(f"✅ Parsed in {elapsed:.2f}s — saved as File #{file_id}")

                    except Exception as e:
                        st.error(f"Parse failed: {e}")
                        import traceback
                        st.code(traceback.format_exc())

st.divider()
st.subheader("Parsed File History")
files = list_files()
if not files:
    st.info("No files parsed yet. Upload an EDI file above.")
else:
    import pandas as pd
    df = pd.DataFrame(files)
    df["upload_ts"] = pd.to_datetime(df["upload_ts"]).dt.strftime("%Y-%m-%d %H:%M")
    df["file_size_kb"] = (df["file_size_bytes"] / 1024).round(1)
    st.dataframe(
        df[["id","filename","tx_type","upload_ts","status","record_count","file_size_kb"]],
        use_container_width=True,
        hide_index=True,
    )
    del_id = st.number_input("Delete file by ID:", min_value=0, step=1, value=0)
    if st.button("Delete File") and del_id > 0:
        delete_file(del_id)
        st.rerun()
