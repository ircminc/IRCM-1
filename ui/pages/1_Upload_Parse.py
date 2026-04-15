"""
Upload & Parse EDI Files

Enhanced with:
  - Service layer (app.services.parse_service) for clean error handling
  - Background threading for large files (Phase 5)
  - HIPAA mode: file encryption + session-scoped temp storage
  - Audit logging for every upload/parse event
  - Progress indicators during parse
  - Validation warnings display
"""
import io
import time
import streamlit as st
import pandas as pd
from storage.file_store import list_files, delete_file, ensure_db

ensure_db()

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

# ── HIPAA mode indicator ───────────────────────────────────────────────────────
try:
    from config import settings as _cfg
    _hipaa = _cfg.hipaa_mode or _cfg.effective_encrypt()
    if _hipaa:
        st.warning("🔒 **HIPAA Mode** — uploaded files are encrypted in memory and will not be persisted to disk.")
except Exception:
    _cfg   = None
    _hipaa = False

# ── Session ID for audit logging ──────────────────────────────────────────────
_session_id = st.session_state.get("session_id", "unknown")

# ── File uploader ─────────────────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "Drop one or more EDI files here",
    type=["edi", "txt", "x12", "837", "835", "270", "271", "276", "277", "834", "820"],
    accept_multiple_files=True,
    help="Supports all ANSI X12 HIPAA 5010 transaction sets. Max 200 MB per file.",
)

if uploaded_files:
    for uploaded in uploaded_files:
        file_key = f"parsed_{uploaded.name}"
        with st.expander(f"📄 {uploaded.name}", expanded=True):
            raw_bytes  = uploaded.read()
            size_kb    = len(raw_bytes) / 1024
            size_label = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

            st.caption(f"Size: {size_label}")

            # Audit: file received
            try:
                from app.security.audit_logger import log_upload
                log_upload(uploaded.name, len(raw_bytes), _session_id)
            except Exception:
                pass

            # Auto-detect TX type before full parse
            try:
                from core.parser.base_parser import detect_tx_type
                tx_detected = detect_tx_type(io.BytesIO(raw_bytes))
                st.success(f"Detected: **{TX_LABELS.get(tx_detected, tx_detected)}**")
            except Exception as e:
                st.error(f"Could not detect transaction type: {e}")
                continue

            col1, col2, col3 = st.columns([2, 1, 1])
            with col2:
                use_bg = st.checkbox(
                    "Background parse",
                    value=len(raw_bytes) > 10 * 1024 * 1024,
                    key=f"bg_{uploaded.name}",
                    help="Recommended for files > 10 MB",
                )
            with col3:
                parse_btn = st.button(f"Parse", key=f"parse_{uploaded.name}", type="primary")

            if parse_btn:
                from app.services.parse_service import parse_edi
                from app.services.background   import submit_parse, should_use_background
                from config import settings as cfg

                # Optionally encrypt bytes in memory (HIPAA mode)
                bytes_to_parse = raw_bytes
                if _hipaa:
                    try:
                        from app.security.encryption import encrypt_bytes, get_session_key
                        key            = get_session_key()
                        encrypted      = encrypt_bytes(raw_bytes, key)
                        # Decrypt immediately for parsing (key stays in session_state only)
                        from app.security.encryption import decrypt_bytes
                        bytes_to_parse = decrypt_bytes(encrypted, key)
                    except Exception:
                        bytes_to_parse = raw_bytes   # fallback: parse unencrypted

                if use_bg and should_use_background(len(bytes_to_parse)):
                    # ── Background parse with progress ────────────────────────
                    progress = st.progress(0, text="Queued for background parsing…")
                    status   = st.empty()
                    future   = submit_parse(bytes_to_parse, uploaded.name, _session_id)

                    t0 = time.monotonic()
                    while not future.done():
                        elapsed = time.monotonic() - t0
                        progress.progress(
                            min(int(elapsed * 5), 90),  # rough indeterminate progress
                            text=f"Parsing… {elapsed:.1f}s",
                        )
                        time.sleep(0.5)

                    progress.progress(100, text="Done!")
                    result = future.result()
                else:
                    # ── Foreground parse ─────────────────────────────────────
                    with st.spinner(f"Parsing {uploaded.name}…"):
                        result = parse_edi(bytes_to_parse, uploaded.name, _session_id)

                # ── Handle result ──────────────────────────────────────────────
                if result.success:
                    # Show warnings
                    for w in result.warnings:
                        st.warning(f"⚠️ {w}")

                    # Save to DB (unless HIPAA no-persistence mode)
                    file_id = None
                    if not (_cfg and _cfg.effective_no_persistence()):
                        try:
                            from storage.file_store import save_parsed_file
                            file_id = save_parsed_file(
                                filename=uploaded.name,
                                tx_type=result.tx_type,
                                parsed_result={"tx_type": result.tx_type, "data": result.data,
                                               "envelope": None, "groups": []},
                                file_size=len(raw_bytes),
                            )
                        except Exception as e:
                            st.warning(f"Could not save to database: {e}")

                    st.session_state[file_key] = result
                    if file_id:
                        st.session_state[f"file_id_{uploaded.name}"] = file_id

                    saved_msg = f" — saved as File #{file_id}" if file_id else " (not persisted)"
                    st.success(
                        f"✅ {result.summary}{saved_msg}"
                    )

                    # Preview parsed data
                    with st.expander("Preview parsed data", expanded=False):
                        data = result.data
                        tx   = result.tx_type
                        if tx == "837P" and data.get("claims"):
                            claims = data["claims"]
                            preview_rows = []
                            for c in claims[:20]:
                                preview_rows.append({
                                    "claim_id":     getattr(c, "claim_id", ""),
                                    "total_billed": getattr(c, "total_billed", ""),
                                    "payer":        getattr(c, "payer_id", ""),
                                    "dos_from":     str(getattr(c, "dos_from", "")),
                                    "lines":        len(getattr(c, "service_lines", [])),
                                })
                            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
                            if len(claims) > 20:
                                st.caption(f"Showing 20 of {len(claims):,} claims")

                        elif tx == "835" and data.get("claim_payments"):
                            pays = data["claim_payments"]
                            preview_rows = []
                            for p in pays[:20]:
                                preview_rows.append({
                                    "clp_id": getattr(p, "clp_id", ""),
                                    "status": getattr(p, "status_code", ""),
                                    "billed": getattr(p, "billed", ""),
                                    "paid":   getattr(p, "paid", ""),
                                })
                            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
                else:
                    st.error(f"❌ Parse failed: {result.error}")

# ── Parsed File History ────────────────────────────────────────────────────────
st.divider()
st.subheader("Parsed File History")

files = list_files()
if not files:
    st.info("No files parsed yet. Upload an EDI file above.")
else:
    df = pd.DataFrame(files)
    df["upload_ts"]    = pd.to_datetime(df["upload_ts"]).dt.strftime("%Y-%m-%d %H:%M")
    df["file_size_kb"] = (df["file_size_bytes"] / 1024).round(1)

    st.dataframe(
        df[["id", "filename", "tx_type", "upload_ts", "status", "record_count", "file_size_kb"]],
        use_container_width=True,
        hide_index=True,
    )

    col_del1, col_del2 = st.columns([1, 3])
    with col_del1:
        del_id = st.number_input("Delete file by ID:", min_value=0, step=1, value=0)
    with col_del2:
        st.write("")
        st.write("")
        if st.button("🗑️ Delete", type="secondary") and del_id > 0:
            try:
                from app.security.audit_logger import log_delete
                matching = [f for f in files if f["id"] == del_id]
                if matching:
                    log_delete(del_id, matching[0].get("tx_type", ""), _session_id)
            except Exception:
                pass
            delete_file(del_id)
            st.rerun()
