"""
Medicare Physician Fee Schedule (PFS) RVU file downloader and parser.
Downloads annual RVU ZIP from CMS and caches as parquet.
"""
from __future__ import annotations
import io
import zipfile
import logging
from datetime import date, datetime
from pathlib import Path
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from config import settings
from .cache import cache_get, cache_set

logger = logging.getLogger(__name__)

PFS_PAGE = "https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files"
CURRENT_YEAR = datetime.now().year


def _parquet_path(year: int) -> Path:
    return settings.cache_dir / f"pfs_{year}.parquet"


def _is_cache_fresh(year: int) -> bool:
    p = _parquet_path(year)
    if not p.exists():
        return False
    age_days = (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).days
    return age_days < settings.pfs_cache_days


def _scrape_rvu_zip_url(year: int) -> str | None:
    """Scrape CMS PFS page for the RVU ZIP download link for the given year."""
    try:
        resp = httpx.get(PFS_PAGE, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")
        yy = str(year)[2:]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if f"rvu{yy}" in href.lower() and href.endswith(".zip"):
                return href if href.startswith("http") else f"https://www.cms.gov{href}"
        # Fallback: direct URL pattern
        return f"https://download.cms.gov/medicare/RVU{yy}A.zip"
    except Exception as e:
        logger.warning(f"PFS scrape failed: {e}")
        return None


def _download_and_parse_rvu(zip_url: str, year: int) -> pd.DataFrame | None:
    """Download RVU ZIP and parse the pipe-delimited RVU file into a DataFrame."""
    try:
        logger.info(f"Downloading PFS RVU file from {zip_url}")
        resp = httpx.get(zip_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # Find the PPRRVU*.txt file
            rvu_name = next(
                (n for n in zf.namelist()
                 if n.upper().startswith("PPRRVU") and n.endswith(".txt")),
                None
            )
            if not rvu_name:
                # Try any pipe-delimited text file
                rvu_name = next((n for n in zf.namelist() if n.endswith(".txt")), None)
            if not rvu_name:
                logger.error("No RVU text file found in ZIP")
                return None

            with zf.open(rvu_name) as f:
                raw = f.read().decode("utf-8", errors="replace")

        # Parse pipe-delimited file — first row is header
        lines = raw.strip().splitlines()
        header_line = lines[0]
        cols = [c.strip().upper() for c in header_line.split("|")]

        rows = []
        for line in lines[1:]:
            parts = line.split("|")
            if len(parts) >= len(cols):
                rows.append(parts[:len(cols)])

        df = pd.DataFrame(rows, columns=cols)

        # Normalize key columns
        rename_map = {}
        for c in df.columns:
            if "HCPCS" in c:
                rename_map[c] = "HCPCS"
            elif c in ("MOD", "MODIFIER"):
                rename_map[c] = "MOD"
            elif "WORK" in c and "RVU" in c:
                rename_map[c] = "WORK_RVU"
            elif "NON_FAC" in c and "TOTAL" in c:
                rename_map[c] = "NON_FAC_TOTAL"
            elif "FAC_TOTAL" in c and "NA" not in c:
                rename_map[c] = "FAC_TOTAL"
            elif "DESCRIPTION" in c or "SHORT_DESC" in c:
                rename_map[c] = "DESCRIPTION"
        df.rename(columns=rename_map, inplace=True)

        # Cast numeric columns
        for col in ["WORK_RVU", "NON_FAC_TOTAL", "FAC_TOTAL"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Compute national payment rates
        cf = settings.pfs_conversion_factor
        if "NON_FAC_TOTAL" in df.columns:
            df["NON_FAC_RATE"] = df["NON_FAC_TOTAL"] * cf
        if "FAC_TOTAL" in df.columns:
            df["FAC_RATE"] = df["FAC_TOTAL"] * cf

        df["HCPCS"] = df["HCPCS"].str.strip()
        return df

    except Exception as e:
        logger.error(f"PFS download/parse failed: {e}")
        return None


def get_pfs_dataframe(year: int = CURRENT_YEAR) -> pd.DataFrame | None:
    """Return PFS DataFrame (from cache or fresh download)."""
    if _is_cache_fresh(year):
        try:
            return pd.read_parquet(_parquet_path(year))
        except Exception:
            pass

    zip_url = _scrape_rvu_zip_url(year)
    if not zip_url:
        return None

    df = _download_and_parse_rvu(zip_url, year)
    if df is not None:
        df.to_parquet(_parquet_path(year), index=False)
    return df


def lookup_pfs_rate(cpt: str, modifier: str = "", year: int = CURRENT_YEAR) -> dict | None:
    """
    Look up PFS rates for a single CPT/HCPCS code.
    Returns dict with keys: non_facility_rate, facility_rate, work_rvu, description
    or None if not found.
    """
    df = get_pfs_dataframe(year)
    if df is None:
        return None

    cpt = cpt.strip().upper()
    mask = df["HCPCS"] == cpt
    if modifier and "MOD" in df.columns:
        mod_mask = df["MOD"].str.strip() == modifier.strip().upper()
        if (mask & mod_mask).any():
            mask = mask & mod_mask

    rows = df[mask]
    if rows.empty:
        return None

    row = rows.iloc[0]
    return {
        "non_facility_rate": float(row["NON_FAC_RATE"]) if "NON_FAC_RATE" in row and pd.notna(row["NON_FAC_RATE"]) else None,
        "facility_rate":     float(row["FAC_RATE"])     if "FAC_RATE"     in row and pd.notna(row["FAC_RATE"])     else None,
        "work_rvu":          float(row["WORK_RVU"])     if "WORK_RVU"     in row and pd.notna(row["WORK_RVU"])     else None,
        "description":       str(row.get("DESCRIPTION", "")).strip(),
        "source":            f"PFS_{year}",
    }
