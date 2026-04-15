"""
Eligibility Analytics (270/271)

Analyzes eligibility inquiry/response pairs to surface:

  Coverage Validation Flags
    - Inquiries with no matching response (unanswered)
    - Responses indicating inactive/terminated coverage
    - Missing key benefit information (deductible, OOP)

  Eligibility Success Rates
    - % of inquiries that returned active coverage
    - % with partial vs full benefit details
    - Trend over time

  Benefit Summary
    - Average deductible, OOP max, co-pay by plan
    - Distribution of coverage levels (IND/FAM/EMP)

These analytics help identify:
  - Patients likely to have claim denials due to eligibility issues
  - Coverage verification workflow gaps
  - Payers with slow/incomplete 271 responses
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ── Flags / constants ─────────────────────────────────────────────────────────

class EligibilityFlag:
    ACTIVE            = "ACTIVE"
    INACTIVE          = "INACTIVE"
    UNKNOWN           = "UNKNOWN"
    NO_RESPONSE       = "NO_RESPONSE"
    MISSING_DEDUCTIBLE = "MISSING_DEDUCTIBLE"
    MISSING_OOP       = "MISSING_OOP"


# ── Build analysis DataFrame from parsed 271 responses ───────────────────────

def build_eligibility_df(parsed_271_list: list[Any]) -> pd.DataFrame:
    """
    Convert a list of EligibilityResponse271 objects into a flat DataFrame.

    Each row represents one subscriber's eligibility response.

    Columns:
        subscriber_id, subscriber_name, payer, plan_name, coverage_active,
        deductible_individual, deductible_family, oop_max, copay,
        benefit_count, coverage_flag
    """
    rows = []
    for resp in parsed_271_list:
        # Extract top-level fields
        row: dict[str, Any] = {
            "subscriber_id":   getattr(resp, "subscriber_id", ""),
            "subscriber_name": getattr(resp, "subscriber_name", ""),
            "payer":           getattr(resp, "payer", ""),
            "plan_name":       getattr(resp, "plan_name", ""),
            "group_number":    getattr(resp, "group_number", ""),
            "coverage_active": getattr(resp, "coverage_active", None),
        }

        # Flatten benefit details
        benefits = getattr(resp, "benefits", []) or []
        row["benefit_count"] = len(benefits)

        deductible_ind  = None
        deductible_fam  = None
        oop_max         = None
        copay           = None
        coinsurance     = None

        for b in benefits:
            benefit_code   = getattr(b, "benefit_code", "")
            coverage_level = str(getattr(b, "coverage_level", "") or "").upper()
            amount         = getattr(b, "monetary_amount", None)
            pct            = getattr(b, "percent", None)

            # Benefit code C  = Deductible
            if benefit_code == "C":
                if coverage_level in ("IND", "INDIVIDUAL", ""):
                    deductible_ind = float(amount) if amount else deductible_ind
                elif coverage_level in ("FAM", "FAMILY", "ESP"):
                    deductible_fam = float(amount) if amount else deductible_fam

            # Benefit code G  = Out of Pocket (Stop Loss)
            elif benefit_code == "G":
                oop_max = float(amount) if amount else oop_max

            # Benefit code B  = Co-Payment
            elif benefit_code == "B":
                copay = float(amount) if amount else copay

            # Benefit code A  = Co-Insurance
            elif benefit_code == "A":
                coinsurance = float(pct) if pct else coinsurance

        row["deductible_individual"] = deductible_ind
        row["deductible_family"]     = deductible_fam
        row["oop_max"]               = oop_max
        row["copay"]                 = copay
        row["coinsurance_pct"]       = coinsurance

        # Coverage flag
        row["coverage_flag"] = _compute_coverage_flag(row)
        rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _compute_coverage_flag(row: dict) -> str:
    """Assign a coverage validation flag to a single eligibility record."""
    active = row.get("coverage_active")
    if active is True:
        flag = EligibilityFlag.ACTIVE
        if row.get("deductible_individual") is None:
            flag = EligibilityFlag.MISSING_DEDUCTIBLE
        elif row.get("oop_max") is None:
            flag = EligibilityFlag.MISSING_OOP
        return flag
    elif active is False:
        return EligibilityFlag.INACTIVE
    else:
        return EligibilityFlag.UNKNOWN


# ── Success rate metrics ──────────────────────────────────────────────────────

def eligibility_success_rate(elig_df: pd.DataFrame) -> dict[str, Any]:
    """
    Return a summary dict with eligibility success metrics.

    Keys:
        total_inquiries, active_count, inactive_count, unknown_count,
        success_rate_pct, complete_benefit_pct
    """
    if elig_df.empty or "coverage_flag" not in elig_df.columns:
        return {
            "total_inquiries":      0,
            "active_count":         0,
            "inactive_count":       0,
            "unknown_count":        0,
            "success_rate_pct":     0.0,
            "complete_benefit_pct": 0.0,
        }

    total    = len(elig_df)
    active   = int((elig_df["coverage_flag"] == EligibilityFlag.ACTIVE).sum())
    inactive = int((elig_df["coverage_flag"] == EligibilityFlag.INACTIVE).sum())
    unknown  = total - active - inactive

    # "Complete" = active AND has deductible AND has OOP max
    complete = int(
        (
            (elig_df["coverage_flag"] == EligibilityFlag.ACTIVE) &
            elig_df["deductible_individual"].notna() &
            elig_df["oop_max"].notna()
        ).sum()
    ) if "deductible_individual" in elig_df.columns else 0

    return {
        "total_inquiries":      total,
        "active_count":         active,
        "inactive_count":       inactive,
        "unknown_count":        unknown,
        "success_rate_pct":     round(active / total * 100, 2) if total else 0.0,
        "complete_benefit_pct": round(complete / total * 100, 2) if total else 0.0,
    }


# ── Coverage validation flags summary ────────────────────────────────────────

def coverage_flag_summary(elig_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a DataFrame summarising coverage flags.
    Columns: coverage_flag, count, pct
    """
    if elig_df.empty or "coverage_flag" not in elig_df.columns:
        return pd.DataFrame()

    counts = elig_df["coverage_flag"].value_counts().reset_index()
    counts.columns = ["coverage_flag", "count"]
    counts["pct"] = (counts["count"] / counts["count"].sum() * 100).round(2)
    return counts


# ── Benefit summary stats ─────────────────────────────────────────────────────

def benefit_summary_stats(elig_df: pd.DataFrame) -> dict[str, Any]:
    """
    Return average financial benefit values across all active eligibility records.
    """
    if elig_df.empty:
        return {}

    active = elig_df[elig_df.get("coverage_flag", pd.Series()) == EligibilityFlag.ACTIVE] \
        if "coverage_flag" in elig_df.columns else elig_df

    def _avg(col: str) -> float | None:
        if col in active.columns:
            vals = pd.to_numeric(active[col], errors="coerce").dropna()
            return round(float(vals.mean()), 2) if not vals.empty else None
        return None

    return {
        "avg_deductible_individual": _avg("deductible_individual"),
        "avg_deductible_family":     _avg("deductible_family"),
        "avg_oop_max":               _avg("oop_max"),
        "avg_copay":                 _avg("copay"),
        "avg_coinsurance_pct":       _avg("coinsurance_pct"),
    }


# ── Payer-level eligibility analytics ────────────────────────────────────────

def eligibility_by_payer(elig_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate eligibility metrics by payer name.

    Returns: payer, inquiry_count, active_rate_pct, avg_deductible
    """
    if elig_df.empty or "payer" not in elig_df.columns:
        return pd.DataFrame()

    active_map = elig_df["coverage_flag"] == EligibilityFlag.ACTIVE \
        if "coverage_flag" in elig_df.columns else pd.Series(False, index=elig_df.index)

    result = (
        elig_df.groupby("payer")
        .apply(lambda g: pd.Series({
            "inquiry_count":    len(g),
            "active_count":     int(active_map.loc[g.index].sum()),
            "avg_deductible":   round(float(pd.to_numeric(g.get("deductible_individual", pd.Series()), errors="coerce").mean()), 2)
                               if "deductible_individual" in g.columns else None,
        }))
        .reset_index()
    )

    result["active_rate_pct"] = (
        result["active_count"] / result["inquiry_count"].replace(0, float("nan")) * 100
    ).round(2)

    return result.sort_values("inquiry_count", ascending=False).reset_index(drop=True)
