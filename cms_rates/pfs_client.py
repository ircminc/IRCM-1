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
    """
    Scrape CMS PFS page for the RVU ZIP download link for the given year.

    CMS structure (as of 2025/2026):
      Main page  → links to sub-pages like /rvu26a  (NOT direct ZIPs)
      Sub-page   → contains the actual ZIP link, e.g. /files/zip/rvu26a-updated-12-29-2025.zip
    """
    CMS_BASE = "https://www.cms.gov"
    try:
        # ── Step 1: find the sub-page for this year on the main PFS page ──────
        resp = httpx.get(PFS_PAGE, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        yy = str(year)[2:]

        subpage_url = None
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            # Match links like /rvu26a, /rvu26b etc. — sub-pages, not ZIPs
            if f"rvu{yy}" in href and not href.endswith(".zip"):
                full = a["href"] if a["href"].startswith("http") else f"{CMS_BASE}{a['href']}"
                subpage_url = full
                break  # take the first (most recent) match

        if not subpage_url:
            logger.warning(f"No RVU sub-page found for year {year} on PFS page")
            return None

        logger.info(f"Found RVU sub-page: {subpage_url}")

        # ── Step 2: follow sub-page and find the ZIP link ─────────────────────
        sub_resp = httpx.get(subpage_url, timeout=30, follow_redirects=True)
        sub_resp.raise_for_status()
        sub_soup = BeautifulSoup(sub_resp.text, "lxml")

        for a in sub_soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".zip"):
                zip_url = href if href.startswith("http") else f"{CMS_BASE}{href}"
                logger.info(f"Found RVU ZIP: {zip_url}")
                return zip_url

        logger.warning(f"No ZIP found on sub-page {subpage_url}")
        return None

    except Exception as e:
        logger.warning(f"PFS scrape failed: {e}")
        return None


def _download_and_parse_rvu(zip_url: str, year: int) -> pd.DataFrame | None:
    """
    Download the RVU ZIP and parse the PPRRVU CSV into a clean DataFrame.

    CMS file layout (as of 2025/2026):
      - PPRRVU{year}_*.csv inside the ZIP
      - Rows 0-8: copyright notices and multi-row column headers
      - Row 9:    actual column header  →  HCPCS, MOD, DESCRIPTION, CODE,
                  PAYMENT, RVU, PE RVU, INDICATOR, PE RVU, INDICATOR, RVU,
                  TOTAL, TOTAL, PCTC, GLOB, ...
      - Row 10+:  data
      Because pandas auto-deduplicates duplicate names, the positional mapping is:
        col[5]  = WORK_RVU
        col[11] = NON_FAC_TOTAL  (Non-Facility Total)
        col[12] = FAC_TOTAL      (Facility Total)
    """
    try:
        logger.info(f"Downloading PFS RVU file from {zip_url}")
        resp = httpx.get(zip_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        csv_content: str | None = None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            logger.info(f"ZIP contents: {names}")

            # Prefer the non-QPP CSV; fall back to any PPRRVU CSV then any CSV
            csv_name = (
                next((n for n in names if n.upper().startswith("PPRRVU") and "NONQPP" in n.upper().replace("-","").replace("_","") and n.endswith(".csv")), None)
                or next((n for n in names if n.upper().startswith("PPRRVU") and n.endswith(".csv")), None)
                or next((n for n in names if n.endswith(".csv") and "PPRRVU" in n.upper()), None)
            )

            if not csv_name:
                logger.error(f"No PPRRVU CSV found in ZIP. Files: {names}")
                return None

            logger.info(f"Parsing: {csv_name}")
            with zf.open(csv_name) as f:
                csv_content = f.read().decode("utf-8", errors="replace")

        lines = csv_content.splitlines()

        # ── Find the real header row (starts with "HCPCS") ───────────────────
        header_row_idx = next(
            (i for i, line in enumerate(lines) if line.upper().startswith("HCPCS")),
            None,
        )
        if header_row_idx is None:
            logger.error("Could not locate HCPCS header row in CSV")
            return None

        logger.info(f"Header row at index {header_row_idx}: {lines[header_row_idx][:80]}")
        data_str = "\n".join(lines[header_row_idx:])

        df = pd.read_csv(
            io.StringIO(data_str),
            dtype=str,
            on_bad_lines="skip",
            low_memory=False,
        )

        # ── Rename key columns by position (headers are duplicated in raw CSV) ─
        # After pandas deduplication: RVU → RVU, RVU.1 (MP), TOTAL → TOTAL (NF), TOTAL.1 (FAC)
        cols = list(df.columns)

        def _col(idx: int) -> str | None:
            return cols[idx] if idx < len(cols) else None

        rename_map: dict[str, str] = {}

        # HCPCS (col 0), MOD (col 1), DESCRIPTION (col 2) — direct name match
        for c in cols:
            cu = c.upper()
            if cu == "HCPCS":
                rename_map[c] = "HCPCS"
            elif cu in ("MOD", "MODIFIER"):
                rename_map[c] = "MOD"
            elif cu == "DESCRIPTION":
                rename_map[c] = "DESCRIPTION"

        # Work RVU is always the 6th column (index 5)
        if _col(5) and _col(5) not in rename_map.values():
            rename_map[cols[5]] = "WORK_RVU"

        # Non-Facility Total is the 12th column (index 11)
        if _col(11) and cols[11] not in rename_map.values():
            rename_map[cols[11]] = "NON_FAC_TOTAL"

        # Facility Total is the 13th column (index 12)
        if _col(12) and cols[12] not in rename_map.values():
            rename_map[cols[12]] = "FAC_TOTAL"

        df.rename(columns=rename_map, inplace=True)
        logger.info(f"Columns after rename: {list(df.columns[:15])}")

        # ── Validate required columns exist ──────────────────────────────────
        missing = [c for c in ("HCPCS", "NON_FAC_TOTAL", "FAC_TOTAL", "WORK_RVU") if c not in df.columns]
        if missing:
            logger.error(f"Missing required columns after rename: {missing}. All cols: {list(df.columns)}")
            return None

        # ── Cast numerics ─────────────────────────────────────────────────────
        for col in ("WORK_RVU", "NON_FAC_TOTAL", "FAC_TOTAL"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # ── Compute Medicare national payment rates ───────────────────────────
        cf = settings.pfs_conversion_factor
        df["NON_FAC_RATE"] = df["NON_FAC_TOTAL"] * cf
        df["FAC_RATE"]     = df["FAC_TOTAL"]     * cf

        df["HCPCS"] = df["HCPCS"].astype(str).str.strip()

        # Drop rows with no HCPCS code
        df = df[df["HCPCS"].str.len() > 0].reset_index(drop=True)

        logger.info(f"PFS parsed: {len(df):,} codes")
        return df

    except Exception as e:
        logger.error(f"PFS download/parse failed: {e}", exc_info=True)
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
