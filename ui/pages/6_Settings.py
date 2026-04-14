"""App settings: CMS refresh, cache management."""
import streamlit as st
from config import settings
import datetime

st.title("⚙️ Settings")

st.subheader("CMS Rate Thresholds")
st.info(f"**OVER threshold:** Billed > **{settings.rate_flag_over_pct:.0f}%** of Medicare rate → OVER_300PCT flag")
st.info(f"**UNDER threshold:** Billed < **{settings.rate_flag_under_pct:.0f}%** of Medicare rate → UNDER_100PCT flag")
st.caption("To change these thresholds, set `RATE_FLAG_OVER_PCT` and `RATE_FLAG_UNDER_PCT` in your `.env` file.")

st.divider()
st.subheader("CMS Data Cache")
col1, col2 = st.columns(2)
with col1:
    st.write(f"**Cache directory:** `{settings.cache_dir}`")
    pfs_files = sorted(settings.cache_dir.glob("pfs_*.parquet"), reverse=True)
    asp_files = sorted(settings.cache_dir.glob("asp_*.parquet"), reverse=True)
    st.write(f"PFS files cached: {len(pfs_files)}")
    st.write(f"ASP files cached: {len(asp_files)}")
with col2:
    if st.button("Clear CMS Cache"):
        for f in list(settings.cache_dir.glob("*.parquet")):
            f.unlink()
        st.success("Cache cleared.")
        st.rerun()

st.divider()
st.subheader("Database")
st.write(f"**DB path:** `{settings.db_path}`")
db_size = settings.db_path.stat().st_size / 1024 if settings.db_path.exists() else 0
st.write(f"**DB size:** {db_size:.1f} KB")
if st.button("Clear All Parsed Data", type="secondary"):
    confirm = st.checkbox("I understand this will delete all parsed file records.")
    if confirm:
        from storage.database import engine
        from storage.models_db import Base
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        st.success("Database cleared.")
        st.rerun()

st.divider()
st.subheader("Conversion Factor")
st.write(f"**CY2025 Conversion Factor:** `{settings.pfs_conversion_factor}`")
st.caption("Update `PFS_CONVERSION_FACTOR` in `.env` each January when CMS publishes the new annual rate.")
