"""
ANSI X12 Medical Billing Converter
Main Streamlit entry point.
"""
import streamlit as st

st.set_page_config(
    page_title="ANSI X12 Medical Billing Converter",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Start CMS rate refresh scheduler in background
try:
    from cms_rates.scheduler import start_scheduler
    start_scheduler()
except Exception:
    pass

# Initialize DB
try:
    from storage.file_store import ensure_db
    ensure_db()
except Exception as e:
    st.error(f"Database init failed: {e}")

st.title("🏥 ANSI X12 Medical Billing Converter")
st.markdown("""
**Supported transaction sets:** 837P · 835 · 270 · 271 · 276 · 277 · 834 · 820

Use the sidebar to navigate between tools. Upload EDI files to parse, export to Excel/PDF,
run denial trend analysis, and compare charges against CMS Medicare rates.
""")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.info("📂 **Upload & Parse**\nDrag-drop EDI files for instant parsing")
with col2:
    st.info("📊 **Export**\nDownload formatted Excel and PDF reports")
with col3:
    st.info("📈 **Analytics**\nDenial trends, volume, payer analysis")
with col4:
    st.info("💊 **CMS Rates**\nCompare charges vs Medicare PFS & ASP")
