"""
ANSI X12 Medical Billing Converter — entry point.
Uses st.navigation() so pages can live anywhere (not just pages/).
"""
import streamlit as st

st.set_page_config(
    page_title="ANSI X12 Medical Billing Converter",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── One-time startup tasks ────────────────────────────────────────────────────
try:
    from cms_rates.scheduler import start_scheduler
    start_scheduler()
except Exception:
    pass

try:
    from storage.file_store import ensure_db
    ensure_db()
except Exception as e:
    st.error(f"Database init failed: {e}")

# ── Page registry ─────────────────────────────────────────────────────────────
home_page = st.Page("ui/pages/0_Home.py",         title="Home",          icon="🏥", default=True)
upload    = st.Page("ui/pages/1_Upload_Parse.py", title="Upload & Parse", icon="📂")
explorer  = st.Page("ui/pages/2_Explorer.py",     title="Data Explorer",  icon="🔍")
export    = st.Page("ui/pages/3_Export.py",        title="Export",         icon="📊")
analytics = st.Page("ui/pages/4_Analytics.py",    title="Analytics",      icon="📈")
cms       = st.Page("ui/pages/5_CMS_Rates.py",    title="CMS Rates",      icon="💊")
settings  = st.Page("ui/pages/6_Settings.py",     title="Settings",       icon="⚙️")

pg = st.navigation({
    " ":        [home_page],
    "Tools":    [upload, explorer, export],
    "Analysis": [analytics, cms],
    "Config":   [settings],
})
pg.run()
