from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # App
    app_name: str = "ANSI X12 Medical Billing Converter"
    app_version: str = "1.0.0"
    max_upload_mb: int = 200
    temp_dir: Path = Path.home() / ".ansi_x12_tool" / "tmp"
    cache_dir: Path = Path.home() / ".ansi_x12_tool" / "cms_cache"
    db_path: Path = Path.home() / ".ansi_x12_tool" / "billing.db"

    # CMS rate flags (billed vs Medicare rate thresholds)
    rate_flag_over_pct: float = 300.0   # OVER_300%
    rate_flag_under_pct: float = 100.0  # UNDER_100%

    # CMS refresh
    pfs_cache_days: int = 30
    asp_check_days: int = 7

    # CMS conversion factor (updated annually — CY2025)
    pfs_conversion_factor: float = 32.35

    # Optional PPL API key (developer.cms.gov)
    ppl_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure dirs exist
settings.temp_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
