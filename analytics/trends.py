"""Time-series trend calculations: volume, payments, AR aging."""
from __future__ import annotations
import pandas as pd
from .aggregator import get_claims_df, get_payments_df


def claims_by_period(
    period: str = "M",  # "W"=weekly, "M"=monthly, "Q"=quarterly
    file_ids: list[int] | None = None,
    dos_from: str | None = None,
    dos_to: str | None = None,
) -> pd.DataFrame:
    """Claim counts and total billed by time period."""
    df = get_claims_df(file_ids=file_ids, dos_from=dos_from, dos_to=dos_to)
    if df.empty:
        return pd.DataFrame(columns=["period", "claim_count", "total_billed"])
    df["dos_from"] = pd.to_datetime(df["dos_from"], errors="coerce")
    df = df.dropna(subset=["dos_from"])
    df["period"] = df["dos_from"].dt.to_period(period).astype(str)
    return (
        df.groupby("period")
        .agg(claim_count=("claim_id", "count"), total_billed=("total_billed", "sum"))
        .reset_index()
        .sort_values("period")
    )


def payment_trend(
    period: str = "M",
    file_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Total paid and denial rate by time period (from 835 data)."""
    df = get_payments_df(file_ids=file_ids)
    if df.empty:
        return pd.DataFrame(columns=["period", "total_paid", "denied_count", "total_count", "denial_rate_pct"])
    df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce")
    df = df.dropna(subset=["payment_date"])
    df["period"] = df["payment_date"].dt.to_period(period).astype(str)
    grp = df.groupby("period").agg(
        total_paid=("paid", "sum"),
        denied_count=("status_code", lambda x: (x == "4").sum()),
        total_count=("clp_id", "count"),
    ).reset_index()
    grp["denial_rate_pct"] = (grp["denied_count"] / grp["total_count"] * 100).round(1)
    return grp.sort_values("period")


def ar_aging(file_ids: list[int] | None = None) -> pd.DataFrame:
    """
    AR aging buckets: counts and billed amounts in 0-30, 31-60, 61-90, 90+ days.
    Uses 837P DOS vs today as a proxy for outstanding AR.
    """
    df = get_claims_df(file_ids=file_ids)
    if df.empty:
        return pd.DataFrame(columns=["bucket", "claim_count", "total_billed"])
    df["dos_from"] = pd.to_datetime(df["dos_from"], errors="coerce")
    df = df.dropna(subset=["dos_from"])
    today = pd.Timestamp.now().normalize()
    df["age_days"] = (today - df["dos_from"]).dt.days

    def bucket(d):
        if d <= 30:   return "0-30 days"
        elif d <= 60: return "31-60 days"
        elif d <= 90: return "61-90 days"
        else:         return "90+ days"

    df["bucket"] = df["age_days"].apply(bucket)
    order = ["0-30 days", "31-60 days", "61-90 days", "90+ days"]
    result = (
        df.groupby("bucket")
        .agg(claim_count=("claim_id","count"), total_billed=("total_billed","sum"))
        .reindex(order)
        .reset_index()
    )
    return result


def payer_metrics(file_ids: list[int] | None = None) -> pd.DataFrame:
    """Per-payer: claim count, denial rate, avg payment rate."""
    claims_df  = get_claims_df(file_ids=file_ids)
    payments_df = get_payments_df(file_ids=file_ids)
    if claims_df.empty:
        return pd.DataFrame()

    claim_summary = claims_df.groupby("payer_id").agg(
        claim_count=("claim_id","count"),
        total_billed=("total_billed","sum"),
        payer_name=("payer_name","first"),
    ).reset_index()

    if not payments_df.empty:
        pay_summary = payments_df.groupby("payer_id").agg(
            total_paid=("paid","sum"),
            denied_count=("status_code", lambda x: (x=="4").sum()),
            payment_count=("clp_id","count"),
        ).reset_index()
        merged = claim_summary.merge(pay_summary, on="payer_id", how="left")
        merged["denial_rate_pct"]   = (merged["denied_count"] / merged["payment_count"] * 100).round(1)
        merged["avg_payment_rate"]  = (merged["total_paid"] / merged["total_billed"] * 100).round(1)
    else:
        merged = claim_summary
        merged["total_paid"] = None
        merged["denial_rate_pct"] = None
        merged["avg_payment_rate"] = None

    return merged
