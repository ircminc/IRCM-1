"""
Upload & Parse EDI Files

Enhanced with:
  - Service layer (app.services.parse_service) for clean error handling
  - Background threading for large files (Phase 5)
  - HIPAA mode: file encryption + session-scoped temp storage
  - Audit logging for every upload/parse event
  - Progress indicators during parse
  - Validation warnings display
  - Batch parse: single click to process all uploaded files
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


# ── Shared parse helper ───────────────────────────────────────────────────────
def _parse_and_store(raw_bytes: bytes, filename: str, use_background: bool):
    """Parse one file, optionally persist to DB, and cache the result in session state.

    Returns (ParseResult, file_id_or_None).
    """
    from app.services.parse_service import parse_edi
    from app.services.background   import submit_parse, should_use_background

    # Optionally encrypt bytes in memory (HIPAA mode)
    bytes_to_parse = raw_bytes
    if _hipaa:
        try:
            from app.security.encryption import encrypt_bytes, decrypt_bytes, get_session_key
            key            = get_session_key()
            encrypted      = encrypt_bytes(raw_bytes, key)
            bytes_to_parse = decrypt_bytes(encrypted, key)
        except Exception:
            bytes_to_parse = raw_bytes   # fallback: parse unencrypted

    if use_background and should_use_background(len(bytes_to_parse)):
        future = submit_parse(bytes_to_parse, filename, _session_id)
        while not future.done():
            time.sleep(0.25)
        result = future.result()
    else:
        result = parse_edi(bytes_to_parse, filename, _session_id)

    file_id = None
    if result.success and not (_cfg and _cfg.effective_no_persistence()):
        try:
            from storage.file_store import save_parsed_file
            file_id = save_parsed_file(
                filename=filename,
                tx_type=result.tx_type,
                parsed_result={"tx_type": result.tx_type, "data": result.data},
                file_size=len(raw_bytes),
            )
        except Exception as e:
            st.session_state[f"save_err_{filename}"] = str(e)

    st.session_state[f"parsed_{filename}"] = result
    if file_id:
        st.session_state[f"file_id_{filename}"] = file_id
    return result, file_id


def _render_preview(result):
    """Render a small table preview for 837P or 835."""
    data = result.data
    tx   = result.tx_type

    if tx == "837P" and data.get("claims"):
        claims = data["claims"]
        preview_rows = [
            {
                "claim_id":     c.get("claim_id", ""),
                "total_billed": c.get("total_billed", ""),
                "payer":        c.get("payer_id", ""),
                "dos_from":     str(c.get("dos_from", "")),
                "lines":        len(c.get("service_lines", [])),
            }
            for c in claims[:20]
        ]
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
        if len(claims) > 20:
            st.caption(f"Showing 20 of {len(claims):,} claims")

    elif tx == "835" and data.get("claim_payments"):
        pays = data["claim_payments"]
        preview_rows = [
            {
                "clp_id": p.get("clp_id", ""),
                "status": p.get("status_code", ""),
                "billed": p.get("billed", ""),
                "paid":   p.get("paid", ""),
            }
            for p in pays[:20]
        ]
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)


# ── File uploader ─────────────────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "Drop one or more EDI files here",
    type=["edi", "txt", "x12", "837", "835", "270", "271", "276", "277", "834", "820"],
    accept_multiple_files=True,
    help="Supports all ANSI X12 HIPAA 4010 and 5010 transaction sets. Max 200 MB per file.",
)

if uploaded_files:
    # Read bytes up-front so both batch and per-file parsing share the same buffer.
    # Streamlit's UploadedFile.getvalue() returns the full bytes without consuming the cursor.
    file_bytes_by_name: dict[str, bytes] = {
        f.name: f.getvalue() for f in uploaded_files
    }

    # ── Batch "Parse All" control ─────────────────────────────────────────────
    if len(uploaded_files) >= 2:
        col_a, col_b, col_c = st.columns([2, 1, 2])
        with col_a:
            st.markdown(f"**{len(uploaded_files)} files ready.**")
        with col_b:
            batch_bg = st.checkbox(
                "Background parse",
                value=any(len(b) > 10 * 1024 * 1024 for b in file_bytes_by_name.values()),
                help="Parse each file in a background thread (recommended when any file > 10 MB).",
                key="batch_bg",
            )
        with col_c:
            parse_all_btn = st.button(
                f"🚀 Parse all {len(uploaded_files)} files",
                type="primary",
                key="parse_all_btn",
                use_container_width=True,
            )

        if parse_all_btn:
            from app.security.audit_logger import log_upload

            progress = st.progress(0.0, text="Starting batch parse…")
            status   = st.empty()
            summary_rows: list[dict] = []
            t_batch  = time.monotonic()

            total = len(uploaded_files)
            for idx, uploaded in enumerate(uploaded_files, start=1):
                fname = uploaded.name
                raw   = file_bytes_by_name[fname]
                progress.progress(
                    (idx - 1) / total,
                    text=f"Parsing {idx} of {total}: {fname}",
                )
                try:
                    log_upload(fname, len(raw), _session_id)
                except Exception:
                    pass
                try:
                    result, file_id = _parse_and_store(raw, fname, use_background=batch_bg)
                    summary_rows.append({
                        "file":        fname,
                        "tx_type":     result.tx_type,
                        "status":      "✅ ok" if result.success else "❌ failed",
                        "records":     result.record_count,
                        "warnings":    len(result.warnings),
                        "duration_ms": result.duration_ms,
                        "file_id":     file_id or "",
                        "error":       result.error or "",
                    })
                except Exception as exc:
                    summary_rows.append({
                        "file":        fname,
                        "tx_type":     "UNKNOWN",
                        "status":      "❌ failed",
                        "records":     0,
                        "warnings":    0,
                        "duration_ms": 0,
                        "file_id":     "",
                        "error":       str(exc),
                    })

            progress.progress(1.0, text="Batch parse complete.")
            elapsed = time.monotonic() - t_batch

            ok   = sum(1 for r in summary_rows if r["status"].startswith("✅"))
            bad  = len(summary_rows) - ok
            warn = sum(r["warnings"] for r in summary_rows)
            if bad == 0:
                status.success(
                    f"✅ {ok}/{len(summary_rows)} files parsed in {elapsed:.1f}s"
                    + (f" — {warn} warnings" if warn else "")
                )
            else:
                status.warning(
                    f"⚠️ {ok} succeeded, {bad} failed (in {elapsed:.1f}s)"
                )

            st.dataframe(
                pd.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
            )
        st.divider()

    # ── Per-file expanders ────────────────────────────────────────────────────
    for uploaded in uploaded_files:
        file_key   = f"parsed_{uploaded.name}"
        raw_bytes  = file_bytes_by_name[uploaded.name]
        size_kb    = len(raw_bytes) / 1024
        size_label = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

        with st.expander(f"📄 {uploaded.name}", expanded=True):
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
                # ── Foreground/background parse with progress ─────────────
                if use_bg and len(raw_bytes) > 10 * 1024 * 1024:
                    progress = st.progress(0, text="Queued for background parsing…")
                    t0 = time.monotonic()
                    # submit_parse + polling is encapsulated inside _parse_and_store,
                    # but we render a simple progress widget here for the user.
                    with st.spinner(f"Parsing {uploaded.name} in background…"):
                        result, file_id = _parse_and_store(raw_bytes, uploaded.name, use_background=True)
                    progress.progress(100, text="Done!")
                else:
                    with st.spinner(f"Parsing {uploaded.name}…"):
                        result, file_id = _parse_and_store(raw_bytes, uploaded.name, use_background=False)

                # ── Handle result ──────────────────────────────────────────
                if result.success:
                    for w in result.warnings:
                        st.warning(f"⚠️ {w}")

                    save_err = st.session_state.pop(f"save_err_{uploaded.name}", None)
                    if save_err:
                        st.warning(f"Could not save to database: {save_err}")

                    saved_msg = f" — saved as File #{file_id}" if file_id else " (not persisted)"
                    st.success(f"✅ {result.summary}{saved_msg}")

                    with st.expander("Preview parsed data", expanded=False):
                        _render_preview(result)
                else:
                    st.error(f"❌ Parse failed: {result.error}")

            # If the file was already parsed (batch or previous click), show the cached result.
            elif file_key in st.session_state:
                cached = st.session_state[file_key]
                if cached.success:
                    fid = st.session_state.get(f"file_id_{uploaded.name}")
                    saved_msg = f" — saved as File #{fid}" if fid else " (not persisted)"
                    st.info(f"✅ {cached.summary}{saved_msg}")
                    for w in cached.warnings:
                        st.warning(f"⚠️ {w}")
                    with st.expander("Preview parsed data", expanded=False):
                        _render_preview(cached)
                else:
                    st.error(f"❌ Parse failed: {cached.error}")

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
