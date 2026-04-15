"""
ANSI X12 Medical Billing Converter — v2 Entry Point
Run with: streamlit run app/main.py

This is the enhanced entry point that adds:
  - Centralized logging setup
  - HIPAA mode banner
  - Three new analytics pages (KPI Dashboard, Provider Performance, Denial Intelligence)
  - Background scheduler for CMS rate auto-refresh
"""
import sys
import os

# ── Ensure project root is on sys.path regardless of where streamlit is invoked
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(
    page_title="ANSI X12 Medical Billing Converter",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Logging setup (runs once per interpreter process) ────────────────────────
try:
    from app.utils.logging_config import setup_logging
    from config import settings
    setup_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        audit_log_path=settings.audit_log_path,
    )
except Exception as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).warning(f"Logging setup error: {e}")

# ── Background CMS scheduler ──────────────────────────────────────────────────
try:
    from cms_rates.scheduler import start_scheduler
    start_scheduler()
except Exception:
    pass

# ── Database init ─────────────────────────────────────────────────────────────
try:
    from storage.file_store import ensure_db
    from config import settings as _s
    if not _s.effective_no_persistence():
        ensure_db()
except Exception as e:
    st.error(f"Database init failed: {e}")

# ── HIPAA mode session initialisation ─────────────────────────────────────────
try:
    from config import settings as _s
    if _s.effective_encrypt():
        from app.security.encryption import get_session_key
        get_session_key()   # generates and stores key in session_state

    if "session_manager" not in st.session_state and _s.hipaa_session_cleanup:
        from app.security.session_manager import SessionManager
        SessionManager.get()   # initialise session-scoped temp dir

    from app.security.audit_logger import log_event, AuditEvent
    if "audit_session_started" not in st.session_state:
        import uuid
        st.session_state["session_id"] = str(uuid.uuid4())[:8]
        log_event(AuditEvent.SESSION_START, session_id=st.session_state["session_id"])
        st.session_state["audit_session_started"] = True
except Exception:
    pass

# ── Page registry ─────────────────────────────────────────────────────────────
# Pages are discovered from ui/pages/ relative to project root.
# New pages (7, 8, 9) are registered here alongside existing ones.

_pages_dir = os.path.join(_ROOT, "ui", "pages")

def _page(file: str, title: str, icon: str, default: bool = False) -> st.Page:
    return st.Page(
        os.path.join(_pages_dir, file),
        title=title,
        icon=icon,
        default=default,
    )

home    = _page("0_Home.py",              "Home",                   "🏥", default=True)
upload  = _page("1_Upload_Parse.py",      "Upload & Parse",         "📂")
explore = _page("2_Explorer.py",          "Data Explorer",          "🔍")
export  = _page("3_Export.py",            "Export",                 "📊")
analyt  = _page("4_Analytics.py",         "Denial Analytics",       "📈")
cms     = _page("5_CMS_Rates.py",         "CMS Rates",              "💊")
kpi     = _page("7_KPI_Dashboard.py",     "KPI Dashboard",          "🎯")
provdr  = _page("8_Provider_Performance.py", "Provider Performance","👨‍⚕️")
denial  = _page("9_Denial_Intelligence.py",  "Denial Intelligence", "🤖")
sett    = _page("6_Settings.py",          "Settings",               "⚙️")

pg = st.navigation({
    " ":           [home],
    "Tools":       [upload, explore, export],
    "Analytics":   [analyt, kpi, provdr, denial],
    "CMS Rates":   [cms],
    "Config":      [sett],
})

# ── HIPAA mode sidebar banner ─────────────────────────────────────────────────
try:
    from config import settings as _cfg
    if _cfg.hipaa_mode or _cfg.effective_mask_phi():
        with st.sidebar:
            st.error("🔒 **HIPAA Mode Active**\nPHI is masked in all outputs.")
except Exception:
    pass

pg.run()
