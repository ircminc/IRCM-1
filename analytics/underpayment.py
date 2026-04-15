"""
Underpayment Detection Engine

Compares 835 ERA payment amounts against expected reimbursement rates
(CMS Physician Fee Schedule and/or configurable contracted rates) and
flags service lines where the payer paid LESS than expected.

Underpayment definition used here:
    Paid < (Expected Rate × underpayment_threshold_pct / 100)

Where Expected Rate is resolved in this priority order:
    1. CMS PFS non-facility rate (for E&M / procedure codes)
    2. CMS ASP+6% rate (for J/Q/C drug codes)
    3. Configurable per-payer contracted rate (future: loaded from .env or DB)

Output:
    A DataFrame with one row per underpaid service line, including:
    - cpt_hcpcs, payer_name, billed, paid, expected_rate
    - variance_amount = expected_rate - paid
    - variance_pct    = (variance_amount / expected_rate) * 100
    - underpayment_flag: bool
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Default threshold: flag if paid < 80% of expected
DEFAULT_THRESHOLD_PCT = 80.0


# ── Main detection function ───────────────────────────────────────────────────

def detect_underpayments(
    payments_df: pd.DataFrame,
    service_lines_df: pd.DataFrame | None = None,
    adjustments_df: pd.DataFrame | None = None,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    cms_year: int | None = None,
) -> pd.DataFrame:
    """
    Detect underpaid service lines by comparing 835 payments to CMS rates.

    Args:
        payments_df:      DataFrame from get_payments_df() — 835 claim-level data.
        service_lines_df: DataFrame with CPT-level paid amounts (optional but recommended).
        adjustments_df:   Adjustments for context.
        threshold_pct:    Flag if paid < threshold_pct% of CMS expected rate.
        cms_year:         PFS rate year (defaults to current year).

    Returns:
        DataFrame with underpayment findings, or empty DataFrame if no data.
    """
    if payments_df.empty:
        return pd.DataFrame()

    # ── Build a per-CPT paid amount DataFrame ─────────────────────────────────
    if service_lines_df is not None and not service_lines_df.empty:
        work_df = _build_from_service_lines(service_lines_df, payments_df)
    else:
        # Fall back to claim-level comparison using billed/paid totals
        work_df = _build_from_claim_level(payments_df)

    if work_df.empty:
        return pd.DataFrame()

    # ── Look up CMS expected rates ─────────────────────────────────────────────
    work_df = _enrich_with_cms_rates(work_df, cms_year)

    # ── Flag underpayments ────────────────────────────────────────────────────
    work_df = _apply_underpayment_flag(work_df, threshold_pct)

    return work_df[work_df["underpayment_flag"]].reset_index(drop=True)


# ── Builder helpers ───────────────────────────────────────────────────────────

def _build_from_service_lines(
    sl_df: pd.DataFrame,
    payments_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build analysis DataFrame from service-line level 835 data."""
    rows = []
    payer_map = {}
    if "id" in payments_df.columns and "payer_name" in payments_df.columns:
        payer_map = dict(zip(payments_df["id"], payments_df["payer_name"]))

    for _, row in sl_df.iterrows():
        cpt   = str(row.get("cpt_hcpcs", "")).strip().upper()
        paid  = float(row.get("paid", 0) or 0)
        billed = float(row.get("billed", 0) or 0)
        payment_id = row.get("payment_id")
        payer = payer_map.get(payment_id, row.get("payer_name", "Unknown"))

        if cpt and paid >= 0:
            rows.append({
                "cpt_hcpcs":   cpt,
                "payer_name":  payer,
                "billed":      billed,
                "paid":        paid,
                "payment_id":  payment_id,
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_from_claim_level(payments_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fallback: build a claim-level analysis (no CPT detail).
    Groups by payer and computes avg paid vs avg billed.
    """
    if "billed" not in payments_df.columns or "paid" not in payments_df.columns:
        return pd.DataFrame()

    df = payments_df.copy()
    df["cpt_hcpcs"]  = "CLAIM_LEVEL"
    df["payer_name"] = df.get("payer_name", pd.Series("Unknown", index=df.index))
    return df[["cpt_hcpcs", "payer_name", "billed", "paid"]].copy()


# ── CMS rate enrichment ───────────────────────────────────────────────────────

def _enrich_with_cms_rates(df: pd.DataFrame, cms_year: int | None) -> pd.DataFrame:
    """Add expected_rate and rate_source columns by looking up CMS PFS/ASP rates."""
    try:
        from cms_rates.rate_comparator import compare_service_line
    except ImportError:
        logger.warning("cms_rates not available — underpayment rates will be null")
        df["expected_rate"] = None
        df["rate_source"]   = "N/A"
        return df

    expected_rates: list[float | None] = []
    rate_sources:   list[str]          = []

    for _, row in df.iterrows():
        cpt = str(row.get("cpt_hcpcs", "")).strip()
        if cpt and cpt != "CLAIM_LEVEL":
            try:
                comp = compare_service_line(cpt, year=cms_year)
                rate = comp.pfs_non_facility_rate or comp.asp_payment_limit
                expected_rates.append(rate)
                rate_sources.append(comp.rate_source or "")
            except Exception:
                expected_rates.append(None)
                rate_sources.append("")
        else:
            expected_rates.append(None)
            rate_sources.append("")

    df = df.copy()
    df["expected_rate"] = expected_rates
    df["rate_source"]   = rate_sources
    return df


# ── Underpayment flagging ─────────────────────────────────────────────────────

def _apply_underpayment_flag(df: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    """Compute variance and apply underpayment flag."""
    df = df.copy()

    def _variance_amount(row: Any) -> float | None:
        if row.get("expected_rate") and row["expected_rate"] > 0:
            return round(float(row["expected_rate"]) - float(row["paid"]), 2)
        return None

    def _variance_pct(row: Any) -> float | None:
        if row.get("expected_rate") and row["expected_rate"] > 0:
            return round(
                ((float(row["expected_rate"]) - float(row["paid"])) / float(row["expected_rate"])) * 100, 2
            )
        return None

    def _flag(row: Any) -> bool:
        if row.get("expected_rate") and row["expected_rate"] > 0:
            paid_pct = (float(row["paid"]) / float(row["expected_rate"])) * 100
            return paid_pct < threshold_pct
        return False

    df["variance_amount"]   = df.apply(_variance_amount, axis=1)
    df["variance_pct"]      = df.apply(_variance_pct, axis=1)
    df["underpayment_flag"] = df.apply(_flag, axis=1)

    return df


# ── Summary aggregations ──────────────────────────────────────────────────────

def underpayment_by_payer(underpayment_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate underpayments by payer.
    Returns: payer_name, count, total_variance, avg_variance_pct
    """
    if underpayment_df.empty:
        return pd.DataFrame()
    return (
        underpayment_df.groupby("payer_name")
        .agg(
            count=("variance_amount", "count"),
            total_variance=("variance_amount", "sum"),
            avg_variance_pct=("variance_pct", "mean"),
            total_billed=("billed", "sum"),
            total_paid=("paid", "sum"),
        )
        .round(2)
        .sort_values("total_variance", ascending=False)
        .reset_index()
    )


def underpayment_by_cpt(underpayment_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate underpayments by CPT/HCPCS code.
    Returns: cpt_hcpcs, count, total_variance, avg_variance_pct
    """
    if underpayment_df.empty:
        return pd.DataFrame()
    return (
        underpayment_df.groupby("cpt_hcpcs")
        .agg(
            count=("variance_amount", "count"),
            total_variance=("variance_amount", "sum"),
            avg_variance_pct=("variance_pct", "mean"),
        )
        .round(2)
        .sort_values("total_variance", ascending=False)
        .reset_index()
    )


def underpayment_summary(underpayment_df: pd.DataFrame) -> dict:
    """Return high-level underpayment summary metrics."""
    if underpayment_df.empty:
        return {
            "total_underpaid_claims": 0,
            "total_variance":         0.0,
            "avg_variance_pct":       0.0,
            "top_payer":              "N/A",
            "top_cpt":                "N/A",
        }

    top_payer = (
        underpayment_df.groupby("payer_name")["variance_amount"].sum().idxmax()
        if "payer_name" in underpayment_df.columns else "N/A"
    )
    top_cpt = (
        underpayment_df.groupby("cpt_hcpcs")["variance_amount"].sum().idxmax()
        if "cpt_hcpcs" in underpayment_df.columns else "N/A"
    )

    return {
        "total_underpaid_claims": len(underpayment_df),
        "total_variance":         round(float(underpayment_df["variance_amount"].sum()), 2),
        "avg_variance_pct":       round(float(underpayment_df["variance_pct"].mean()), 2),
        "top_payer":              top_payer,
        "top_cpt":                top_cpt,
    }
