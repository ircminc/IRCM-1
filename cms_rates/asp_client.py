"""
Medicare Part B Drug ASP Pricing downloader.
Downloads quarterly ASP ZIP from CMS and caches as parquet.
"""
from __future__ import annotations
import io
import re
import zipfile
import logging
from datetime import datetime
from pathlib import Path
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from config import settings

logger = logging.getLogger(__name__)

ASP_PAGE = "https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files"


def _asp_parquet_path(label: str) -> Path:
    return settings.cache_dir / f"asp_{label}.parquet"


def _scrape_latest_asp_info() -> tuple[str, str] | None:
    """
    Scrapes the ASP page for the most recent quarterly pricing ZIP.
    Returns (url, label) e.g. ("https://...ASP4Q2024.zip", "4Q2024")
    """
    try:
        resp = httpx.get(ASP_PAGE, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")
        pattern = re.compile(r"ASP\w*\.zip", re.IGNORECASE)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if pattern.search(href):
                url = href if href.startswith("http") else f"https://www.cms.gov{href}"
                # Extract label from filename like "ASP4Q2024.zip" → "4Q2024"
                match = re.search(r"ASP(\w+)\.zip", href, re.IGNORECASE)
                label = match.group(1) if match else datetime.now().strftime("%YQ%m")
                return url, label
    except Exception as e:
        logger.warning(f"ASP scrape failed: {e}")
    return None


def _download_and_parse_asp(zip_url: str, label: str) -> pd.DataFrame | None:
    """Download ASP ZIP and parse the pricing spreadsheet."""
    try:
        logger.info(f"Downloading ASP pricing file from {zip_url}")
        resp = httpx.get(zip_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        all_rows = []
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                lower = name.lower()
                # Focus on the main ASP pricing file (not NDC crosswalk)
                if ("asp" in lower or "pricing" in lower) and (name.endswith(".xlsx") or name.endswith(".xls") or name.endswith(".txt") or name.endswith(".csv")):
                    with zf.open(name) as f:
                        try:
                            if name.endswith(".xlsx"):
                                df_tmp = pd.read_excel(io.BytesIO(f.read()), header=0, dtype=str)
                            elif name.endswith(".xls"):
                                df_tmp = pd.read_excel(io.BytesIO(f.read()), header=0, dtype=str)
                            else:
                                content = f.read().decode("utf-8", errors="replace")
                                lines = content.splitlines()
                                sep = "," if "," in lines[0] else "\t"
                                df_tmp = pd.read_csv(io.StringIO(content), sep=sep, dtype=str)
                            all_rows.append(df_tmp)
                        except Exception as e:
                            logger.warning(f"Could not parse {name}: {e}")

        if not all_rows:
            return None

        df = pd.concat(all_rows, ignore_index=True)

        # Normalize column names
        df.columns = [str(c).strip().upper().replace(" ", "_") for c in df.columns]

        # Try to find HCPCS and payment limit columns
        hcpcs_col = next((c for c in df.columns if "HCPCS" in c), None)
        limit_col  = next((c for c in df.columns if "PAYMENT" in c and "LIMIT" in c), None)
        desc_col   = next((c for c in df.columns if "DESC" in c or "NAME" in c), None)

        if not hcpcs_col:
            logger.error("No HCPCS column found in ASP file")
            return None

        rename = {hcpcs_col: "HCPCS"}
        if limit_col:
            rename[limit_col] = "PAYMENT_LIMIT"
        if desc_col:
            rename[desc_col] = "DESCRIPTION"
        df.rename(columns=rename, inplace=True)

        df["HCPCS"] = df["HCPCS"].str.strip().str.upper()
        if "PAYMENT_LIMIT" in df.columns:
            df["PAYMENT_LIMIT"] = pd.to_numeric(df["PAYMENT_LIMIT"], errors="coerce")

        return df

    except Exception as e:
        logger.error(f"ASP download/parse failed: {e}")
        return None


def get_asp_dataframe() -> tuple[pd.DataFrame | None, str]:
    """
    Returns (DataFrame, label) for the most recent ASP quarter.
    Uses cache if available and fresh.
    """
    info = _scrape_latest_asp_info()
    if not info:
        return None, ""
    url, label = info

    parquet = _asp_parquet_path(label)
    if parquet.exists():
        try:
            return pd.read_parquet(parquet), label
        except Exception:
            pass

    df = _download_and_parse_asp(url, label)
    if df is not None:
        df.to_parquet(parquet, index=False)
    return df, label


def lookup_asp_rate(hcpcs: str) -> dict | None:
    """
    Look up ASP+6% payment limit for a HCPCS J-code or drug code.
    Returns dict with keys: payment_limit, description, source  or None.
    """
    df, label = get_asp_dataframe()
    if df is None:
        return None

    hcpcs = hcpcs.strip().upper()
    rows = df[df["HCPCS"] == hcpcs]
    if rows.empty:
        return None

    row = rows.iloc[0]
    return {
        "payment_limit": float(row["PAYMENT_LIMIT"]) if pd.notna(row.get("PAYMENT_LIMIT")) else None,
        "description":   str(row.get("DESCRIPTION", "")).strip(),
        "source":        f"ASP_{label}",
    }
