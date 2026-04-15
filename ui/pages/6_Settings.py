"""
Settings — App Configuration, CMS Cache, HIPAA Mode, Audit Log

Covers:
  - Rate threshold display
  - CMS data cache management
  - Database management
  - HIPAA mode controls and PHI masking preview
  - Audit log viewer and download
  - App version / environment info
"""
import streamlit as st
import datetime
import pandas as pd
from config import settings

st.title("⚙️ Settings")

tab_general, tab_hipaa, tab_cms, tab_db, tab_audit = st.tabs([
    "General", "🔒 HIPAA Mode", "CMS Data", "Database", "Audit Log"
])

# ══════════════════════════════════════════════════════════════════════════════
# GENERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_general:
    st.subheader("Application Info")
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"**Version:** `{settings.app_version}`")
        st.info(f"**Log Level:** `{settings.log_level}`")
        st.info(f"**Max Upload:** `{settings.max_upload_mb} MB`")
    with c2:
        st.info(f"**Cache Dir:** `{settings.cache_dir}`")
        st.info(f"**DB Path:** `{settings.db_path}`")
        st.info(f"**Audit Log:** `{settings.audit_log_path}`")

    st.divider()
    st.subheader("CMS Rate Thresholds")
    st.info(f"**OVER threshold:** Billed > **{settings.rate_flag_over_pct:.0f}%** of Medicare rate → `OVER_300PCT` flag")
    st.info(f"**UNDER threshold:** Billed < **{settings.rate_flag_under_pct:.0f}%** of Medicare rate → `UNDER_100PCT` flag")
    st.caption("To change thresholds, set `RATE_FLAG_OVER_PCT` and `RATE_FLAG_UNDER_PCT` in your `.env` file.")

    st.divider()
    st.subheader("Conversion Factor")
    st.info(f"**CY2025 PFS Conversion Factor:** `{settings.pfs_conversion_factor}`")
    st.caption("Update `PFS_CONVERSION_FACTOR` in `.env` each January when CMS publishes the new annual rate.")


# ══════════════════════════════════════════════════════════════════════════════
# HIPAA MODE
# ══════════════════════════════════════════════════════════════════════════════
with tab_hipaa:
    st.subheader("🔒 HIPAA-Conscious Mode")
    st.markdown(
        """
        When **HIPAA Mode** is enabled, the following protections are activated:

        | Protection | Description |
        |---|---|
        | **File Encryption** | Uploaded EDI files are encrypted in memory (Fernet/AES-128) |
        | **PHI Masking** | Patient names, DOB, and IDs are masked in all displayed outputs |
        | **No Persistence** | Parsed data is NOT saved to the SQLite database |
        | **Session Cleanup** | All temp files are securely deleted when the session ends |

        > **Note:** These are lightweight application-layer safeguards.
        > For full HIPAA compliance, use a dedicated HIPAA-compliant hosting environment
        > with Business Associate Agreements and formal audit controls.
        """
    )

    st.divider()
    st.subheader("Current HIPAA Settings")

    flags = {
        "HIPAA_MODE":               settings.hipaa_mode,
        "HIPAA_ENCRYPT_UPLOADS":    settings.hipaa_encrypt_uploads,
        "HIPAA_MASK_PHI":           settings.hipaa_mask_phi,
        "HIPAA_NO_PERSISTENCE":     settings.hipaa_no_persistence,
        "HIPAA_SESSION_CLEANUP":    settings.hipaa_session_cleanup,
    }

    for flag, val in flags.items():
        icon = "✅" if val else "⬜"
        effective = " *(active via HIPAA_MODE=true)*" if (not val and settings.hipaa_mode) else ""
        st.write(f"{icon} `{flag}`{effective}")

    if settings.hipaa_mode:
        st.error("🔒 **HIPAA Mode is ACTIVE** — all protections enabled")
    else:
        st.info("HIPAA mode is off. To enable, set `HIPAA_MODE=true` in your `.env` file.")

    st.divider()
    st.subheader("Encryption Status")
    try:
        from app.security.encryption import is_available
        if is_available():
            st.success("✅ `cryptography` library installed — file encryption available")
        else:
            st.warning("⚠️ `cryptography` not installed. Run: `pip install cryptography`")
    except Exception:
        st.warning("Could not check encryption availability.")

    st.divider()
    st.subheader("PHI Masking Preview")
    st.markdown("How patient data appears when masking is active:")
    from app.security.phi_masker import mask_name, mask_dob, mask_id, mask_npi
    preview_df = pd.DataFrame({
        "Field":    ["Patient Name", "Date of Birth", "Member ID",      "Provider NPI"],
        "Original": ["John Smith",   "1985-07-22",    "ABC123456789",   "1234567890"],
        "Masked":   [
            mask_name("John Smith"),
            mask_dob("1985-07-22"),
            mask_id("ABC123456789"),
            mask_npi("1234567890"),
        ]
    })
    st.dataframe(preview_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# CMS DATA
# ══════════════════════════════════════════════════════════════════════════════
with tab_cms:
    st.subheader("CMS Data Cache")

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Physician Fee Schedule (PFS)**")
        pfs_files = sorted(settings.cache_dir.glob("pfs_*.parquet"), reverse=True)
        if pfs_files:
            latest = pfs_files[0]
            mtime  = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
            age    = (datetime.datetime.now() - mtime).days
            st.success(f"Cached: `{latest.name}` · Updated {age} days ago")
        else:
            st.warning("PFS data not downloaded yet.")

        if st.button("🔄 Refresh PFS Now"):
            with st.spinner("Downloading PFS RVU file…"):
                try:
                    from cms_rates.pfs_client import get_pfs_dataframe
                    df = get_pfs_dataframe()
                    if df is not None:
                        st.success(f"✅ PFS refreshed: {len(df):,} codes")
                    else:
                        st.error("Could not download PFS data.")
                except Exception as e:
                    st.error(str(e))

    with col2:
        st.write("**ASP Drug Pricing**")
        asp_files = sorted(settings.cache_dir.glob("asp_*.parquet"), reverse=True)
        if asp_files:
            latest = asp_files[0]
            mtime  = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
            age    = (datetime.datetime.now() - mtime).days
            st.success(f"Cached: `{latest.name}` · Updated {age} days ago")
        else:
            st.warning("ASP data not downloaded yet.")

        if st.button("🔄 Refresh ASP Now"):
            with st.spinner("Downloading ASP pricing file…"):
                try:
                    from cms_rates.asp_client import get_asp_dataframe
                    df, label = get_asp_dataframe()
                    if df is not None:
                        st.success(f"✅ ASP refreshed: {len(df):,} codes ({label})")
                    else:
                        st.error("Could not download ASP data.")
                except Exception as e:
                    st.error(str(e))

    st.divider()
    if st.button("🗑️ Clear CMS Cache", type="secondary"):
        for f in list(settings.cache_dir.glob("*.parquet")):
            f.unlink()
        st.success("CMS cache cleared. Data will re-download on next use.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("Database")
    st.write(f"**DB path:** `{settings.db_path}`")
    db_size = settings.db_path.stat().st_size / 1024 if settings.db_path.exists() else 0
    st.write(f"**DB size:** {db_size:.1f} KB")

    from storage.file_store import list_files
    all_files = list_files()
    counts: dict = {}
    for f in all_files:
        tx = f.get("tx_type", "UNKNOWN")
        counts[tx] = counts.get(tx, 0) + 1
    if counts:
        count_df = pd.DataFrame([{"TX Type": k, "Files": v} for k, v in sorted(counts.items())])
        st.dataframe(count_df, use_container_width=True, hide_index=True)

    st.divider()
    if st.button("🗑️ Clear All Parsed Data", type="secondary"):
        confirm = st.checkbox("I understand this will delete all parsed file records.")
        if confirm:
            from storage.database import engine
            from storage.models_db import Base
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
            st.success("Database cleared.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════
with tab_audit:
    st.subheader("Audit Log")

    log_path = settings.audit_log_path
    if not log_path.exists():
        st.info(f"Audit log not yet created. It will appear at:\n`{log_path}`")
    else:
        import json
        entries = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "audit_record" in data:
                            entries.append(data["audit_record"])
                        elif "message" in data:
                            try:
                                inner = json.loads(data["message"])
                                entries.append(inner)
                            except Exception:
                                entries.append({
                                    "ts": data.get("ts", ""),
                                    "event": data.get("message", ""),
                                    "details": {},
                                })
                        else:
                            entries.append(data)
                    except Exception:
                        pass
        except Exception as e:
            st.error(f"Could not read audit log: {e}")

        if entries:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                event_types    = sorted(set(e.get("event", "") for e in entries))
                selected_events = st.multiselect("Filter by event:", event_types, default=event_types)
            with col_f2:
                max_rows = st.number_input("Max rows:", min_value=10, max_value=5000, value=100, step=50)

            filtered = [e for e in entries if e.get("event", "") in selected_events]
            filtered = filtered[-max_rows:]

            log_df = pd.DataFrame([{
                "Timestamp": e.get("ts", ""),
                "Event":     e.get("event", ""),
                "Session":   e.get("session_id", ""),
                "Details":   str(e.get("details", "")),
            } for e in reversed(filtered)])

            st.dataframe(log_df, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(filtered)} of {len(entries)} audit events")

            st.download_button(
                "⬇️ Download Full Audit Log",
                data=log_path.read_bytes(),
                file_name="audit_log.jsonl",
                mime="application/jsonlines",
            )
        else:
            st.info("Audit log exists but contains no parseable entries yet.")
