"""
ANSI X12 Medical Billing Converter — Legacy Entry Point

This file is kept for backward compatibility.
The canonical entry point is now app/main.py which includes all v2 features:
  - New analytics pages (KPI Dashboard, Provider Performance, Denial Intelligence)
  - HIPAA security layer
  - Background processing
  - Centralized logging + audit trail

Run the full application with:
    streamlit run app/main.py

This file delegates to app/main.py automatically.
"""
import runpy
import os
import sys

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Delegate to the v2 entry point
runpy.run_path(os.path.join(_ROOT, "app", "main.py"), run_name="__main__")
