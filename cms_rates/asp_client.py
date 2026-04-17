"""
Medicare Part B Drug ASP Pricing downloader.

Downloads quarterly ASP ZIP from CMS and caches as parquet.

Scraper strategy (CMS restructured the ASP landing page in 2024/2025 to use
quarterly sub-pages rather than direct ZIP links on a single index page):

  1. If settings.asp_zip_url is set, skip scraping and download that URL directly.
  2. Otherwise, fetch the ASP index page and look for:
       a. quarterly sub-page links (containing "asp" + a month/quarter hint),
          follow each and pick the first .zip link;
       b. as a fallback, any .zip link on the index whose URL or text contains
          "asp" (handles both legacy "ASP4Q2024.zip" and newer
          "april-2026-asp-pricing-file.zip" naming).
  3. On failure, ASPDownloadError is raised with a detailed reason so the UI
     can show operators what CMS actually served and what to override.
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
CMS_BASE = "https://www.cms.gov"

# Hints that mark a sub-page or link as "ASP pricing" related.
_ASP_HINT = re.compile(r"asp[-_ ]*(pricing|drug|quarter)", re.IGNORECASE)
_QUARTER_HINT = re.compile(
    r"\b(q[1-4]|[1-4]q|january|april|july|october|"
    r"jan|apr|jul|oct|first|second|third|fourth)\b",
    re.IGNORECASE,
)


class ASPDownloadError(RuntimeError):
    """Raised when ASP pricing data cannot be located or downloaded."""


def _asp_parquet_path(label: str) -> Path:
    return settings.cache_dir / f"asp_{label}.parquet"


def _label_from_href(href: str) -> str:
    """Derive a short label like '4Q2024' or 'apr-2026' from an ASP href."""
    m = re.search(r"ASP(\w+?)\.zip", href, re.IGNORECASE)
    if m:
        return m.group(1)
    # newer style: april-2026-asp-pricing-file.zip
    m = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)[-_ ]*(\d{4})",
        href, re.IGNORECASE,
    )
    if m:
        return f"{m.group(1)[:3].lower()}-{m.group(2)}"
    m = re.search(r"(\d{4})[-_ ]*q([1-4])", href, re.IGNORECASE)
    if m:
        return f"{m.group(2)}Q{m.group(1)}"
    return datetime.now().strftime("%YQ%m")


def _absolute(href: str) -> str:
    return href if href.startswith("http") else f"{CMS_BASE}{href}"


def _find_zip_on_page(url: str) -> tuple[str, str] | None:
    """Fetch `url` and return (zip_url, label) for the first ASP-looking .zip it contains."""
    logger.info(f"ASP scrape: fetching {url}")
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    zips: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".zip"):
            continue
        text = (a.get_text() or "").strip()
        haystack = f"{href} {text}".lower()
        if "asp" in haystack or "pricing" in haystack:
            zips.append((_absolute(href), _label_from_href(href)))

    if not zips:
        return None
    # First match wins — CMS typically orders newest first.
    return zips[0]


def _find_asp_subpage(index_html: str) -> list[str]:
    """Return candidate CMS sub-page URLs that likely host an ASP ZIP."""
    soup = BeautifulSoup(index_html, "lxml")
    subpages: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text() or "").strip()
        if href.lower().endswith(".zip"):
            continue  # already handled by _find_zip_on_page
        full = _absolute(href)
        if full in seen:
            continue
        haystack = f"{href} {text}"
        if _ASP_HINT.search(haystack) or (
            "asp" in haystack.lower() and _QUARTER_HINT.search(haystack)
        ):
            subpages.append(full)
            seen.add(full)
    return subpages


def _scrape_latest_asp_info() -> tuple[str, str]:
    """
    Locate the most recent ASP pricing ZIP on CMS.

    Returns (zip_url, label). Raises ASPDownloadError with a detailed reason on
    failure so the UI can show operators the actual problem.
    """
    # Manual override — bypass scraping entirely.
    if getattr(settings, "asp_zip_url", ""):
        override = settings.asp_zip_url
        logger.info(f"Using ASP_ZIP_URL override: {override}")
        return override, _label_from_href(override)

    try:
        resp = httpx.get(ASP_PAGE, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        raise ASPDownloadError(
            f"Could not fetch CMS ASP index page {ASP_PAGE!r}: {e}"
        ) from e

    # 1) direct .zip link on the index
    try:
        direct = _find_zip_on_page(ASP_PAGE)
    except Exception as e:
        logger.warning(f"Direct ZIP scan on ASP index failed: {e}")
        direct = None
    if direct:
        return direct

    # 2) follow quarterly sub-pages
    subpages = _find_asp_subpage(resp.text)
    logger.info(f"ASP scrape: {len(subpages)} sub-pages to try")
    for sp in subpages:
        try:
            found = _find_zip_on_page(sp)
        except Exception as e:
            logger.warning(f"Sub-page {sp} fetch failed: {e}")
            continue
        if found:
            return found

    raise ASPDownloadError(
        "CMS ASP landing page did not expose a downloadable ZIP. "
        f"Scanned {len(subpages)} sub-pages. "
        "If CMS restructured the page, set ASP_ZIP_URL in .env to override "
        "(e.g. https://www.cms.gov/files/zip/april-2026-asp-pricing-file.zip)."
    )


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
                if ("asp" in lower or "pricing" in lower) and (
                    name.endswith(".xlsx")
                    or name.endswith(".xls")
                    or name.endswith(".txt")
                    or name.endswith(".csv")
                ):
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
            raise ASPDownloadError(
                f"ZIP {zip_url!r} contained no parseable ASP pricing sheet "
                f"(looked for *.xlsx / *.xls / *.csv with 'asp' or 'pricing' in the name)."
            )

        df = pd.concat(all_rows, ignore_index=True)
        df.columns = [str(c).strip().upper().replace(" ", "_") for c in df.columns]

        hcpcs_col = next((c for c in df.columns if "HCPCS" in c), None)
        limit_col = next((c for c in df.columns if "PAYMENT" in c and "LIMIT" in c), None)
        desc_col  = next((c for c in df.columns if "DESC" in c or "NAME" in c), None)

        if not hcpcs_col:
            raise ASPDownloadError(
                f"Downloaded ASP file has no HCPCS column. Columns seen: {list(df.columns)[:12]}"
            )

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

    except ASPDownloadError:
        raise
    except Exception as e:
        logger.error(f"ASP download/parse failed: {e}")
        raise ASPDownloadError(f"ASP download/parse failed: {e}") from e


def get_asp_dataframe() -> tuple[pd.DataFrame | None, str]:
    """
    Returns (DataFrame, label) for the most recent ASP quarter.
    Uses cache if available and fresh.

    Raises ASPDownloadError when scraping or download fails with a
    human-readable reason so the UI can show it to operators.
    """
    zip_url, label = _scrape_latest_asp_info()

    parquet = _asp_parquet_path(label)
    if parquet.exists():
        try:
            return pd.read_parquet(parquet), label
        except Exception as e:
            logger.warning(f"ASP parquet cache read failed, re-downloading: {e}")

    df = _download_and_parse_asp(zip_url, label)
    if df is not None:
        try:
            df.to_parquet(parquet, index=False)
        except Exception as e:
            logger.warning(f"Could not write ASP parquet cache: {e}")
    return df, label


def lookup_asp_rate(hcpcs: str) -> dict | None:
    """
    Look up ASP+6% payment limit for a HCPCS J-code or drug code.
    Returns dict with keys: payment_limit, description, source  or None.
    """
    try:
        df, label = get_asp_dataframe()
    except ASPDownloadError:
        return None

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
