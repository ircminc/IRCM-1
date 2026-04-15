"""
Revenue Cycle KPI Engine

Calculates the core financial KPIs used in medical billing:

  Net Collection Rate (NCR)
      Measures how much of collectible revenue was actually collected.
      Formula: Total Payments / (Total Billed − Contractual Adjustments)
      Target: > 95%

  First Pass Resolution Rate (FPRR)
      Claims paid on first submission without denial or rework.
      Formula: Claims paid without CO/PR adjustments / Total Claims
      Target: > 90%

  Days in Accounts Receivable (DAR)
      Average number of days claims remain outstanding.
      Formula: (Total Outstanding Billed / Avg Daily Billed)
      Target: < 40 days

  Aging Buckets
      Distribution of outstanding claims by age (0–30, 31–60, 61–90, 90+ days).

  Denial Rate
      Percentage of claims denied on first submission.
      Formula: Denied Claims / Total Claims Submitted
      Target: < 5%

  Average Reimbursement Rate
      Ratio of amount paid to amount billed.
      Formula: Total Paid / Total Billed
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ── KPI result container ───────────────────────────────────────────────────────

class KPIResult:
    """Holds all computed KPI values with metadata."""

    def __init__(self, **kwargs: Any) -> None:
        # Revenue metrics
        self.total_billed: float      = kwargs.get("total_billed", 0.0)
        self.total_paid: float        = kwargs.get("total_paid", 0.0)
        self.total_contractual: float = kwargs.get("total_contractual", 0.0)
        self.total_patient_resp: float= kwargs.get("total_patient_resp", 0.0)

        # Core KPIs
        self.net_collection_rate: float | None    = kwargs.get("net_collection_rate")
        self.first_pass_rate: float | None        = kwargs.get("first_pass_rate")
        self.days_in_ar: float | None             = kwargs.get("days_in_ar")
        self.denial_rate: float | None            = kwargs.get("denial_rate")
        self.avg_reimbursement_rate: float | None = kwargs.get("avg_reimbursement_rate")

        # AR aging
        self.aging: dict[str, dict] = kwargs.get("aging", {})

        # Counts
        self.total_claims: int     = kwargs.get("total_claims", 0)
        self.denied_claims: int    = kwargs.get("denied_claims", 0)
        self.clean_claims: int     = kwargs.get("clean_claims", 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_billed":           self.total_billed,
            "total_paid":             self.total_paid,
            "total_contractual":      self.total_contractual,
            "net_collection_rate":    self.net_collection_rate,
            "first_pass_rate":        self.first_pass_rate,
            "days_in_ar":             self.days_in_ar,
            "denial_rate":            self.denial_rate,
            "avg_reimbursement_rate": self.avg_reimbursement_rate,
            "total_claims":           self.total_claims,
            "denied_claims":          self.denied_claims,
            "clean_claims":           self.clean_claims,
            "aging":                  self.aging,
        }

    def grade(self, kpi: str) -> str:
        """Return a traffic-light grade (🟢 / 🟡 / 🔴) for a given KPI."""
        thresholds = {
            "net_collection_rate":    [(95, "🟢"), (85, "🟡"), (0, "🔴")],
            "first_pass_rate":        [(90, "🟢"), (75, "🟡"), (0, "🔴")],
            "days_in_ar":             [(40, "🟢 Good"), (60, "🟡 Review"), (999, "🔴 High")],
            "denial_rate":            [(5,  "🟢 Good"), (10, "🟡 Review"), (100, "🔴 High")],
            "avg_reimbursement_rate": [(70, "🟢"), (50, "🟡"), (0, "🔴")],
        }
        val = getattr(self, kpi, None)
        if val is None:
            return "⚪ N/A"

        rules = thresholds.get(kpi, [])
        # Days in AR and Denial Rate: lower is better
        if kpi in ("days_in_ar", "denial_rate"):
            for threshold, label in rules:
                if val <= threshold:
                    return label
        else:
            for threshold, label in rules:
                if val >= threshold:
                    return label
        return "⚪"


# ── Main computation functions ─────────────────────────────────────────────────

def compute_kpis(
    claims_df: pd.DataFrame,
    payments_df: pd.DataFrame,
    adjustments_df: pd.DataFrame,
    as_of: date | None = None,
) -> KPIResult:
    """
    Compute all Revenue Cycle KPIs from the given DataFrames.

    Args:
        claims_df:      DataFrame from analytics.aggregator.get_claims_df()
        payments_df:    DataFrame from analytics.aggregator.get_payments_df()
        adjustments_df: DataFrame from analytics.aggregator.get_adjustments_df()
        as_of:          Reference date for DAR calculation (defaults to today).

    Returns:
        KPIResult with all computed values.
    """
    as_of = as_of or date.today()
    kwargs: dict[str, Any] = {}

    # ── Total billed (from 837P claims) ───────────────────────────────────────
    kwargs["total_claims"] = len(claims_df)
    kwargs["total_billed"] = float(
        claims_df["total_billed"].sum() if "total_billed" in claims_df.columns else 0
    )

    # ── Payment + adjustment totals (from 835) ─────────────────────────────────
    if not payments_df.empty:
        kwargs["total_paid"] = float(payments_df["paid"].sum() if "paid" in payments_df.columns else 0)
        kwargs["total_patient_resp"] = float(
            payments_df["patient_responsibility"].sum()
            if "patient_responsibility" in payments_df.columns else 0
        )

    if not adjustments_df.empty:
        # Contractual adjustments = CO group code (Contractual Obligation)
        co_adj = adjustments_df[adjustments_df["group_code"] == "CO"]["amount"].sum() \
            if "group_code" in adjustments_df.columns else 0
        kwargs["total_contractual"] = float(co_adj)

    # ── Net Collection Rate ────────────────────────────────────────────────────
    #   NCR = Paid / (Billed − Contractual)
    collectible = kwargs.get("total_billed", 0) - kwargs.get("total_contractual", 0)
    if collectible > 0:
        kwargs["net_collection_rate"] = round(
            (kwargs.get("total_paid", 0) / collectible) * 100, 2
        )

    # ── Average Reimbursement Rate ─────────────────────────────────────────────
    if kwargs.get("total_billed", 0) > 0 and "total_paid" in kwargs:
        kwargs["avg_reimbursement_rate"] = round(
            (kwargs["total_paid"] / kwargs["total_billed"]) * 100, 2
        )

    # ── Denial Rate ───────────────────────────────────────────────────────────
    if not payments_df.empty and "status_code" in payments_df.columns:
        denied = int(payments_df["status_code"].isin(["4", "4 "]).sum())
        total  = len(payments_df)
        kwargs["denied_claims"] = denied
        if total > 0:
            kwargs["denial_rate"] = round((denied / total) * 100, 2)
    elif not adjustments_df.empty and "group_code" in adjustments_df.columns:
        # Fallback: claims with any CO denial adjustment
        if not claims_df.empty and "id" in claims_df.columns:
            denied_ids = adjustments_df[
                adjustments_df["group_code"].isin(["CO", "CR"])
            ]["payment_id"].unique() if "payment_id" in adjustments_df.columns else []
            kwargs["denied_claims"] = len(denied_ids)
            if kwargs["total_claims"] > 0:
                kwargs["denial_rate"] = round(
                    (len(denied_ids) / kwargs["total_claims"]) * 100, 2
                )

    # ── First Pass Resolution Rate ────────────────────────────────────────────
    #   Claims paid without any CO or denial adjustment on first attempt
    if not adjustments_df.empty and "payment_id" in adjustments_df.columns and not payments_df.empty:
        denied_payment_ids = set(
            adjustments_df[adjustments_df["group_code"].isin(["CO"])]["payment_id"].dropna().unique()
        )
        clean = len(payments_df[~payments_df["id"].isin(denied_payment_ids)]) \
            if "id" in payments_df.columns else 0
        kwargs["clean_claims"]   = clean
        total_payments = len(payments_df)
        if total_payments > 0:
            kwargs["first_pass_rate"] = round((clean / total_payments) * 100, 2)

    # ── Days in AR ────────────────────────────────────────────────────────────
    kwargs["days_in_ar"]  = _compute_days_in_ar(claims_df, payments_df, as_of)

    # ── AR Aging buckets ──────────────────────────────────────────────────────
    kwargs["aging"]       = _compute_aging(claims_df, as_of)

    return KPIResult(**kwargs)


# ── Days in AR ────────────────────────────────────────────────────────────────

def _compute_days_in_ar(
    claims_df: pd.DataFrame,
    payments_df: pd.DataFrame,
    as_of: date,
) -> float | None:
    """
    Calculate average Days in AR.

    For each claim with a service date, we compute age = (as_of - dos_from).
    We only include claims that have NOT been fully paid.
    """
    if claims_df.empty or "dos_from" not in claims_df.columns:
        return None

    try:
        df = claims_df.copy()
        df["dos_from"] = pd.to_datetime(df["dos_from"], errors="coerce")
        df = df.dropna(subset=["dos_from"])
        if df.empty:
            return None

        # Exclude fully paid claims (those that appear in payments with status != 4)
        paid_claim_ids: set = set()
        if not payments_df.empty and "clp_id" in payments_df.columns:
            paid_claim_ids = set(
                payments_df[payments_df["status_code"] != "4"]["clp_id"].dropna()
            )

        if paid_claim_ids and "claim_id" in df.columns:
            outstanding = df[~df["claim_id"].isin(paid_claim_ids)]
        else:
            outstanding = df

        if outstanding.empty:
            return None

        as_of_ts = pd.Timestamp(as_of)
        ages = (as_of_ts - outstanding["dos_from"]).dt.days
        ages = ages[ages >= 0]
        return round(float(ages.mean()), 1) if not ages.empty else None

    except Exception as exc:
        logger.warning(f"DAR calculation error: {exc}")
        return None


# ── AR Aging ──────────────────────────────────────────────────────────────────

_AGING_BUCKETS = [
    ("0–30 days",    0,  30),
    ("31–60 days",  31,  60),
    ("61–90 days",  61,  90),
    ("90+ days",    91, 9999),
]

def _compute_aging(claims_df: pd.DataFrame, as_of: date) -> dict[str, dict]:
    """
    Return aging bucket summary: { bucket_label: {count, total_billed} }
    """
    result = {b[0]: {"count": 0, "total_billed": 0.0} for b in _AGING_BUCKETS}

    if claims_df.empty or "dos_from" not in claims_df.columns:
        return result

    try:
        df = claims_df.copy()
        df["dos_from"] = pd.to_datetime(df["dos_from"], errors="coerce")
        df = df.dropna(subset=["dos_from"])
        as_of_ts = pd.Timestamp(as_of)
        df["age_days"] = (as_of_ts - df["dos_from"]).dt.days
        df = df[df["age_days"] >= 0]

        billed_col = "total_billed" if "total_billed" in df.columns else None

        for label, lo, hi in _AGING_BUCKETS:
            bucket = df[(df["age_days"] >= lo) & (df["age_days"] <= hi)]
            result[label]["count"] = int(len(bucket))
            if billed_col:
                result[label]["total_billed"] = float(bucket[billed_col].sum())

    except Exception as exc:
        logger.warning(f"Aging calculation error: {exc}")

    return result


# ── KPI trend over time ────────────────────────────────────────────────────────

def kpi_trend(
    payments_df: pd.DataFrame,
    adjustments_df: pd.DataFrame,
    period: str = "M",
) -> pd.DataFrame:
    """
    Compute monthly/quarterly KPI trend data.

    Returns DataFrame with columns:
        period, total_paid, total_billed_835, denial_rate_pct, avg_reimb_pct
    """
    if payments_df.empty or "payment_date" not in payments_df.columns:
        return pd.DataFrame()

    try:
        df = payments_df.copy()
        df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce")
        df = df.dropna(subset=["payment_date"])
        df["period"] = df["payment_date"].dt.to_period(period).astype(str)

        grp = df.groupby("period").agg(
            total_paid=("paid", "sum"),
            total_billed=("billed", "sum"),
            total_claims=("id", "count"),
            denied_count=("status_code", lambda x: (x == "4").sum()),
        ).reset_index()

        grp["denial_rate_pct"] = (grp["denied_count"] / grp["total_claims"] * 100).round(2)
        grp["avg_reimb_pct"]   = (grp["total_paid"] / grp["total_billed"].replace(0, float("nan")) * 100).round(2)

        return grp.sort_values("period")

    except Exception as exc:
        logger.error(f"KPI trend error: {exc}")
        return pd.DataFrame()


# ── Aging DataFrame (for charting) ────────────────────────────────────────────

def aging_dataframe(kpi_result: KPIResult) -> pd.DataFrame:
    """Convert KPIResult.aging dict to a DataFrame suitable for Plotly."""
    rows = [
        {"bucket": label, "count": v["count"], "total_billed": v["total_billed"]}
        for label, v in kpi_result.aging.items()
    ]
    return pd.DataFrame(rows)
