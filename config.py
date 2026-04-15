from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "ANSI X12 Medical Billing Converter"
    app_version: str = "2.0.0"
    max_upload_mb: int = 200

    # ── Storage paths (overridable via .env) ──────────────────────────────────
    temp_dir:  Path = Path.home() / ".ansi_x12_tool" / "tmp"
    cache_dir: Path = Path.home() / ".ansi_x12_tool" / "cms_cache"
    db_path:   Path = Path.home() / ".ansi_x12_tool" / "billing.db"

    # ── Audit logging ─────────────────────────────────────────────────────────
    audit_log_path: Path = Path.home() / ".ansi_x12_tool" / "audit.jsonl"
    log_level: str = "INFO"          # DEBUG | INFO | WARNING | ERROR
    log_json: bool = False           # True → JSON lines (for log aggregators)

    # ── CMS rate flags (billed vs Medicare rate thresholds) ───────────────────
    rate_flag_over_pct: float  = 300.0   # OVER_300%  — possible compliance issue
    rate_flag_under_pct: float = 100.0   # UNDER_100% — possible underbilling

    # ── CMS refresh ───────────────────────────────────────────────────────────
    pfs_cache_days: int = 30
    asp_check_days: int = 7

    # ── CMS conversion factor (update each January) ───────────────────────────
    pfs_conversion_factor: float = 32.35   # CY2025

    # ── Optional CMS API key (developer.cms.gov) ──────────────────────────────
    ppl_api_key: str = ""

    # ── HIPAA Mode ────────────────────────────────────────────────────────────
    # When hipaa_mode=True, ALL sub-flags below are automatically activated.
    # Individual flags can also be toggled independently for partial control.
    hipaa_mode: bool = False

    # Encrypt uploaded files in memory using Fernet (session-scoped key)
    hipaa_encrypt_uploads: bool = False

    # Mask PHI fields (names, DOB, IDs) in all displayed tables and exports
    hipaa_mask_phi: bool = False

    # Never write uploaded files or parsed data to disk (memory-only processing)
    hipaa_no_persistence: bool = False

    # Auto-delete temp files when session ends
    hipaa_session_cleanup: bool = True

    # ── Performance ───────────────────────────────────────────────────────────
    # Files larger than this threshold are parsed in a background thread
    background_processing_threshold_mb: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def effective_mask_phi(self) -> bool:
        """Returns True if PHI masking should be applied (hipaa_mode OR explicit flag)."""
        return self.hipaa_mode or self.hipaa_mask_phi

    def effective_no_persistence(self) -> bool:
        """Returns True if data should NOT be persisted to SQLite."""
        return self.hipaa_mode or self.hipaa_no_persistence

    def effective_encrypt(self) -> bool:
        """Returns True if uploaded files should be encrypted in memory."""
        return self.hipaa_mode or self.hipaa_encrypt_uploads


settings = Settings()

# Ensure dirs exist (skip if no-persistence mode)
if not settings.effective_no_persistence():
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
else:
    # Still need cache dir for CMS rate parquet files
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
