"""
Provider Performance Analytics

Computes per-NPI (billing and rendering provider) performance metrics:

  Revenue Metrics
    - Total billed / paid / contractual adjustments per provider
    - Net collection rate per provider
    - Average reimbursement rate

  Denial Metrics
    - Denial count and denial rate per provider
    - Top denial reason codes per provider
    - Comparison vs practice average

  CPT Utilization
    - Procedure code frequency per provider
    - Revenue per CPT per provider
    - Comparison of provider's CPT mix vs peers

All functions return DataFrames suitable for Plotly charting and
Excel export (used by 8_Provider_Performance.py page).
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


# ── Revenue metrics per provider ──────────────────────────────────────────────

def provider_revenue_metrics(
    claims_df: pd.DataFrame,
    payments_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate revenue metrics by billing_provider_npi.

    Returns DataFrame with columns:
        provider_npi, provider_name, claim_count, total_billed,
        total_paid, collection_rate_pct, avg_claim_value
    """
    if claims_df.empty:
        return pd.DataFrame()

    npi_col  = "billing_provider_npi"
    name_col = "billing_provider_name"

    if npi_col not in claims_df.columns:
        logger.warning("billing_provider_npi not found in claims DataFrame")
        return pd.DataFrame()

    # ── Claim-level aggregation ────────────────────────────────────────────────
    agg_cols: dict = {
        "claim_id":    ("claim_id", "count"),
        "total_billed": ("total_billed", "sum"),
    }
    if name_col in claims_df.columns:
        agg_cols["provider_name"] = (name_col, "first")

    claim_grp = (
        claims_df.groupby(npi_col)
        .agg(**{k: v for k, v in agg_cols.items()})
        .reset_index()
        .rename(columns={npi_col: "provider_npi", "claim_id": "claim_count"})
    )

    # ── Payment-level aggregation ──────────────────────────────────────────────
    pay_grp = pd.DataFrame()
    if not payments_df.empty and "paid" in payments_df.columns:
        # Try to match payments to providers via payer_claim_number or clp_id
        # Fall back to claim-level join if possible
        if "clp_id" in payments_df.columns and "claim_id" in claims_df.columns:
            pay_merged = payments_df.merge(
                claims_df[[npi_col, "claim_id"]],
                left_on="clp_id", right_on="claim_id",
                how="left",
            )
            if npi_col in pay_merged.columns:
                pay_grp = (
                    pay_merged.groupby(npi_col)
                    .agg(total_paid=("paid", "sum"))
                    .reset_index()
                    .rename(columns={npi_col: "provider_npi"})
                )

    # ── Merge and compute rates ────────────────────────────────────────────────
    result = claim_grp.copy()
    if not pay_grp.empty:
        result = result.merge(pay_grp, on="provider_npi", how="left")
    else:
        result["total_paid"] = None

    result["total_billed"] = pd.to_numeric(result["total_billed"], errors="coerce").fillna(0)
    if "total_paid" in result.columns:
        result["total_paid"] = pd.to_numeric(result["total_paid"], errors="coerce").fillna(0)
        result["collection_rate_pct"] = (
            result["total_paid"] / result["total_billed"].replace(0, float("nan")) * 100
        ).round(2)

    result["avg_claim_value"] = (
        result["total_billed"] / result["claim_count"].replace(0, float("nan"))
    ).round(2)

    return result.sort_values("total_billed", ascending=False).reset_index(drop=True)


# ── Denial analytics per provider ─────────────────────────────────────────────

def provider_denial_analysis(
    claims_df: pd.DataFrame,
    adjustments_df: pd.DataFrame,
    payments_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Compute denial metrics by billing provider NPI.

    Returns DataFrame with columns:
        provider_npi, provider_name, total_claims, denied_claims,
        denial_rate_pct, top_denial_reason, top_denial_amount
    """
    if claims_df.empty or adjustments_df.empty:
        return pd.DataFrame()

    npi_col = "billing_provider_npi"
    if npi_col not in claims_df.columns:
        return pd.DataFrame()

    # ── Identify denied claims from adjustments ─────────────────────────────
    co_adj = adjustments_df[
        adjustments_df["group_code"].isin(["CO", "CR"])
    ] if "group_code" in adjustments_df.columns else pd.DataFrame()

    if co_adj.empty:
        return pd.DataFrame()

    # Join: adjustment payment_id → payment clp_id → claim claim_id
    claim_denial_map = pd.DataFrame()
    if (
        "payment_id" in co_adj.columns
        and payments_df is not None
        and not payments_df.empty
        and "id" in payments_df.columns
        and "clp_id" in payments_df.columns
        and "claim_id" in claims_df.columns
    ):
        merged = (
            co_adj[["payment_id", "reason_code", "amount"]]
            .merge(payments_df[["id", "clp_id"]], left_on="payment_id", right_on="id", how="left")
            .merge(claims_df[["claim_id", npi_col]], left_on="clp_id", right_on="claim_id", how="left")
        )
        claim_denial_map = merged

    # ── Aggregate per NPI ──────────────────────────────────────────────────────
    claim_totals = (
        claims_df.groupby(npi_col)
        .agg(total_claims=("claim_id", "count"))
        .reset_index()
        .rename(columns={npi_col: "provider_npi"})
    )

    if claim_denial_map.empty or npi_col not in claim_denial_map.columns:
        claim_totals["denied_claims"]    = 0
        claim_totals["denial_rate_pct"]  = 0.0
        claim_totals["top_denial_reason"] = "N/A"
        claim_totals["top_denial_amount"] = 0.0
        return claim_totals

    denied_per_npi = (
        claim_denial_map.groupby(npi_col)
        .agg(
            denied_claims=("clp_id", "nunique"),
            top_denial_reason=("reason_code", lambda x: x.value_counts().idxmax() if not x.empty else "N/A"),
            top_denial_amount=("amount", "sum"),
        )
        .reset_index()
        .rename(columns={npi_col: "provider_npi"})
    )

    result = claim_totals.merge(denied_per_npi, on="provider_npi", how="left")
    result["denied_claims"]   = result["denied_claims"].fillna(0).astype(int)
    result["denial_rate_pct"] = (
        result["denied_claims"] / result["total_claims"].replace(0, float("nan")) * 100
    ).round(2).fillna(0)

    # Add names if available
    if "billing_provider_name" in claims_df.columns:
        name_map = dict(zip(claims_df[npi_col], claims_df["billing_provider_name"]))
        result["provider_name"] = result["provider_npi"].map(name_map)

    return result.sort_values("denial_rate_pct", ascending=False).reset_index(drop=True)


# ── CPT utilization per provider ──────────────────────────────────────────────

def provider_cpt_utilization(
    service_lines_df: pd.DataFrame,
    claims_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Compute CPT code utilization by rendering provider NPI.

    Returns DataFrame with columns:
        rendering_provider_npi, cpt_hcpcs, procedure_count,
        total_billed, avg_billed
    """
    if service_lines_df.empty:
        return pd.DataFrame()

    npi_col = "rendering_provider_npi"
    cpt_col = "cpt_hcpcs"

    if cpt_col not in service_lines_df.columns:
        return pd.DataFrame()

    # If no rendering NPI, fall back to billing NPI via claim join
    if npi_col not in service_lines_df.columns:
        if (
            claims_df is not None
            and not claims_df.empty
            and "billing_provider_npi" in claims_df.columns
            and "claim_id" in service_lines_df.columns
        ):
            merged = service_lines_df.merge(
                claims_df[["claim_id", "billing_provider_npi"]],
                on="claim_id", how="left",
            )
            merged = merged.rename(columns={"billing_provider_npi": npi_col})
            work_df = merged
        else:
            logger.warning("No rendering or billing NPI available for CPT utilization")
            return pd.DataFrame()
    else:
        work_df = service_lines_df.copy()

    agg = (
        work_df.groupby([npi_col, cpt_col])
        .agg(
            procedure_count=("line_number", "count") if "line_number" in work_df.columns else ("cpt_hcpcs", "count"),
            total_billed=("billed_amount", "sum") if "billed_amount" in work_df.columns else (cpt_col, "count"),
        )
        .reset_index()
        .rename(columns={npi_col: "provider_npi"})
    )

    if "total_billed" in agg.columns:
        agg["avg_billed"] = (agg["total_billed"] / agg["procedure_count"].replace(0, float("nan"))).round(2)

    return agg.sort_values(["provider_npi", "total_billed"], ascending=[True, False]).reset_index(drop=True)


# ── Provider comparison table ─────────────────────────────────────────────────

def provider_comparison(
    revenue_df: pd.DataFrame,
    denial_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge revenue and denial metrics into a single comparison table.
    Adds practice-average columns for benchmarking.
    """
    if revenue_df.empty:
        return pd.DataFrame()

    result = revenue_df.copy()

    if not denial_df.empty and "provider_npi" in denial_df.columns:
        result = result.merge(
            denial_df[["provider_npi", "denied_claims", "denial_rate_pct", "top_denial_reason"]],
            on="provider_npi",
            how="left",
        )

    # Practice averages
    if "collection_rate_pct" in result.columns:
        avg_ncr = result["collection_rate_pct"].mean()
        result["vs_avg_collection"] = (result["collection_rate_pct"] - avg_ncr).round(2)

    if "denial_rate_pct" in result.columns:
        avg_dr = result["denial_rate_pct"].mean()
        result["vs_avg_denial"] = (result["denial_rate_pct"] - avg_dr).round(2)

    return result.reset_index(drop=True)
