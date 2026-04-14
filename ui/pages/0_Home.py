"""Home / landing page."""
import streamlit as st

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
