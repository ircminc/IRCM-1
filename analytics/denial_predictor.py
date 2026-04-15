"""
Rule-Based Denial Prediction Engine

Evaluates 837P claims BEFORE submission and assigns a risk score (0.0–1.0)
for each service line based on configurable rules that mirror common payer
denial patterns observed in RCM practice.

Architecture:
  - Rules are independent functions that return (triggered: bool, risk_delta: float, reason: str)
  - The engine applies all rules and sums risk_deltas, capping at 1.0
  - Each result includes a list of triggered rules and recommended actions

Risk score interpretation:
  0.00–0.29  LOW    — Clean claim, submit with confidence
  0.30–0.59  MEDIUM — Review before submission
  0.60–1.00  HIGH   — Likely denial — correct before submission

ML-Ready Structure:
  The RuleEngine class is designed so that ML model integration requires
  only replacing the score() method with a model.predict() call while
  keeping the same input/output interface.

Usage:
    from analytics.denial_predictor import DenialPredictor

    predictor = DenialPredictor()
    predictions = predictor.predict_claim(claim_dict)
    for pred in predictions:
        print(pred.cpt_hcpcs, pred.risk_score, pred.risk_level, pred.risk_factors)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class DenialPrediction:
    """Predicted denial risk for a single service line."""
    cpt_hcpcs:          str
    modifier_1:         str
    risk_score:         float           # 0.0 – 1.0
    risk_level:         str             # LOW | MEDIUM | HIGH
    risk_factors:       list[str]       = field(default_factory=list)
    recommendations:    list[str]       = field(default_factory=list)
    historical_denial_rate: float | None = None   # % from past 835 data


# ── Rule helpers ──────────────────────────────────────────────────────────────

# Type alias for a rule function
RuleFn = Callable[[dict], tuple[bool, float, str, str]]
# (triggered, risk_delta, reason_text, recommendation_text)


def _rule(fn: RuleFn) -> RuleFn:
    """Decorator that marks a function as a denial prediction rule."""
    fn._is_rule = True  # type: ignore[attr-defined]
    return fn


# ── Individual Rules ──────────────────────────────────────────────────────────

@_rule
def rule_unlisted_procedure(svc: dict) -> tuple[bool, float, str, str]:
    """CPT codes ending in 99 are unlisted — require supporting documentation."""
    cpt = str(svc.get("cpt_hcpcs", ""))
    if re.match(r"^\d+99$", cpt):
        return (
            True, 0.55,
            f"CPT {cpt} is an unlisted procedure code",
            "Attach supporting documentation and clinical narrative before submission",
        )
    return False, 0.0, "", ""


@_rule
def rule_modifier_59_overuse(svc: dict) -> tuple[bool, float, str, str]:
    """Modifier 59 should only be used when no more specific modifier applies."""
    mods = [str(svc.get(f"modifier_{i}", "") or "").strip() for i in range(1, 5)]
    if "59" in mods:
        specific = {"XE", "XP", "XS", "XU"}
        if not any(m in specific for m in mods):
            return (
                True, 0.30,
                "Modifier 59 used — consider more specific X modifier (XE/XP/XS/XU)",
                "Review CMS Modifier 59 Article; replace with appropriate X modifier if applicable",
            )
    return False, 0.0, "", ""


@_rule
def rule_missing_modifier_bilateral(svc: dict) -> tuple[bool, float, str, str]:
    """Certain procedure codes require Modifier 50 (bilateral) when performed bilaterally."""
    BILATERAL_REQUIRED_RANGE = range(27000, 28000)   # ortho procedures example
    cpt = str(svc.get("cpt_hcpcs", ""))
    mods = [str(svc.get(f"modifier_{i}", "") or "") for i in range(1, 5)]
    try:
        if int(cpt) in BILATERAL_REQUIRED_RANGE and "50" not in mods:
            # Only flag if units > 1 (suggests bilateral intent)
            if float(svc.get("units", 1) or 1) > 1:
                return (
                    True, 0.35,
                    f"CPT {cpt} may require Modifier 50 for bilateral procedure",
                    "Verify if procedure was bilateral and add Modifier 50 if appropriate",
                )
    except (ValueError, TypeError):
        pass
    return False, 0.0, "", ""


@_rule
def rule_place_of_service_mismatch(svc: dict) -> tuple[bool, float, str, str]:
    """
    Some CPTs are only covered in specific places of service.
    Examples:
      - Office-only codes (POS 11) billed in facility setting
      - Inpatient-only procedures (CMS Inpatient Only list)
    """
    cpt = str(svc.get("cpt_hcpcs", ""))
    pos = str(svc.get("place_of_service", "") or "")

    # Telehealth codes without POS 02/10/95 modifier
    TELEHEALTH_CPTS = {"99441", "99442", "99443", "98966", "98967", "98968", "G0425", "G0426", "G0427"}
    if cpt in TELEHEALTH_CPTS and pos not in ("02", "10") :
        return (
            True, 0.40,
            f"Telehealth CPT {cpt} requires POS 02 or 10",
            "Update Place of Service to 02 (Telehealth Off-Premises) or 10 (Telehealth On-Premises)",
        )

    return False, 0.0, "", ""


@_rule
def rule_diagnosis_pointer_missing(svc: dict) -> tuple[bool, float, str, str]:
    """SV1 diagnosis pointers (SV107) should reference at least one diagnosis code."""
    ptrs = str(svc.get("diagnosis_pointers", "") or "").strip()
    if not ptrs or ptrs in ("", "0", "None"):
        return (
            True, 0.45,
            "No diagnosis code pointer (SV107) — claim will likely be rejected",
            "Ensure SV107 references the applicable diagnosis code positions (A, B, C, D...)",
        )
    return False, 0.0, "", ""


@_rule
def rule_high_billed_vs_cms(svc: dict) -> tuple[bool, float, str, str]:
    """
    Billed amounts > 300% of CMS fee schedule are flagged.
    Some payers auto-deny or request ADR letters for high-charge outliers.
    """
    billed   = float(svc.get("billed_amount", 0) or 0)
    cms_rate = float(svc.get("_cms_non_fac_rate", 0) or 0)
    if cms_rate > 0 and billed > cms_rate * 4:
        pct = round(billed / cms_rate * 100)
        return (
            True, 0.30,
            f"Billed (${billed:.2f}) is {pct}% of CMS rate (${cms_rate:.2f}) — high outlier",
            "Review charge amount; some payers trigger ADR letters or auto-denials for outlier charges",
        )
    return False, 0.0, "", ""


@_rule
def rule_ndc_required_drug_code(svc: dict) -> tuple[bool, float, str, str]:
    """J-codes and certain HCPCS drug codes require an NDC number."""
    cpt = str(svc.get("cpt_hcpcs", "")).upper()
    ndc = str(svc.get("ndc", "") or "").strip()
    if cpt.startswith("J") and not ndc:
        return (
            True, 0.60,
            f"J-code {cpt} requires National Drug Code (NDC) — mandatory for most payers",
            "Add NDC in LIN segment format: qualifier N4 + 11-digit NDC",
        )
    return False, 0.0, "", ""


@_rule
def rule_global_surgery_period(svc: dict) -> tuple[bool, float, str, str]:
    """
    Post-operative visit codes billed within the global surgery period
    without appropriate modifier will be denied as bundled.
    """
    cpt = str(svc.get("cpt_hcpcs", ""))
    mods = [str(svc.get(f"modifier_{i}", "") or "") for i in range(1, 5)]

    # E&M codes commonly denied when billed same day as surgery without modifier 25
    EM_CODES = {str(c) for c in range(99202, 99216)}
    if cpt in EM_CODES and "25" not in mods:
        # Flag only if also has a surgery code on same claim (heuristic)
        other_cpts = svc.get("_other_cpts_on_claim", [])
        surgery_codes = [c for c in other_cpts if c.startswith(("1", "2", "3", "4", "5", "6", "7"))]
        if surgery_codes:
            return (
                True, 0.50,
                f"E&M code {cpt} billed same day as procedure without Modifier 25",
                "Add Modifier 25 to E&M code to indicate significant, separately identifiable service",
            )
    return False, 0.0, "", ""


@_rule
def rule_duplicate_cpt_same_claim(svc: dict) -> tuple[bool, float, str, str]:
    """Duplicate CPT codes on the same claim without distinct modifiers are commonly denied."""
    cpt  = str(svc.get("cpt_hcpcs", ""))
    dups = svc.get("_duplicate_cpts", [])
    mods = [str(svc.get(f"modifier_{i}", "") or "").strip() for i in range(1, 5)]
    mods = [m for m in mods if m]

    if cpt in dups and not mods:
        return (
            True, 0.55,
            f"CPT {cpt} appears more than once on this claim without distinguishing modifiers",
            "Add appropriate modifier (59, 76, 77, XE/XP/XS/XU) to distinguish each service",
        )
    return False, 0.0, "", ""


# ── All rules registry ────────────────────────────────────────────────────────

ALL_RULES: list[RuleFn] = [
    rule_unlisted_procedure,
    rule_modifier_59_overuse,
    rule_missing_modifier_bilateral,
    rule_place_of_service_mismatch,
    rule_diagnosis_pointer_missing,
    rule_high_billed_vs_cms,
    rule_ndc_required_drug_code,
    rule_global_surgery_period,
    rule_duplicate_cpt_same_claim,
]


# ── Main predictor class ──────────────────────────────────────────────────────

class DenialPredictor:
    """
    Rule-based denial risk predictor.

    To integrate a trained ML model in the future:
      1. Subclass DenialPredictor
      2. Override _score_service_line() to call model.predict_proba()
      3. Keep the predict_claim() interface unchanged
    """

    def __init__(self, rules: list[RuleFn] | None = None) -> None:
        self.rules = rules or ALL_RULES

    def predict_claim(self, claim: dict[str, Any]) -> list[DenialPrediction]:
        """
        Evaluate all service lines on a claim and return predictions.

        Args:
            claim: Dict with keys:
                - claim_id, place_of_service, diagnoses (list)
                - service_lines: list of dicts (cpt_hcpcs, modifier_1–4,
                    billed_amount, units, diagnosis_pointers, ndc)

        Returns:
            List of DenialPrediction, one per service line.
        """
        service_lines = claim.get("service_lines", [])
        if not service_lines:
            return []

        # Pre-compute claim-level context
        all_cpTs = [svc.get("cpt_hcpcs", "") for svc in service_lines]
        cpt_counts = {}
        for c in all_cpTs:
            cpt_counts[c] = cpt_counts.get(c, 0) + 1
        duplicate_cpTs = {c for c, n in cpt_counts.items() if n > 1}

        predictions = []
        for svc in service_lines:
            # Inject claim-level context into svc for rules to access
            svc_ctx = dict(svc)
            svc_ctx["_other_cpTs_on_claim"] = [c for c in all_cpTs if c != svc.get("cpt_hcpcs")]
            svc_ctx["_duplicate_cpTs"] = duplicate_cpTs
            svc_ctx["place_of_service"] = svc.get("place_of_service") or claim.get("place_of_service", "")

            pred = self._score_service_line(svc_ctx)
            predictions.append(pred)

        return predictions

    def _score_service_line(self, svc: dict) -> DenialPrediction:
        """Apply all rules to a single service line and aggregate the score."""
        risk_score    = 0.0
        risk_factors  = []
        recommendations = []

        for rule in self.rules:
            try:
                triggered, delta, reason, recommendation = rule(svc)
                if triggered and delta > 0:
                    risk_score += delta
                    risk_factors.append(reason)
                    if recommendation:
                        recommendations.append(recommendation)
            except Exception as exc:
                logger.debug(f"Rule {rule.__name__} error: {exc}")

        # Cap at 1.0
        risk_score = min(round(risk_score, 3), 1.0)

        return DenialPrediction(
            cpt_hcpcs        = str(svc.get("cpt_hcpcs", "")),
            modifier_1       = str(svc.get("modifier_1", "") or ""),
            risk_score       = risk_score,
            risk_level       = _risk_level(risk_score),
            risk_factors     = risk_factors,
            recommendations  = recommendations,
        )

    def enrich_with_history(
        self,
        predictions: list[DenialPrediction],
        adjustments_df: Any,   # pd.DataFrame
    ) -> list[DenialPrediction]:
        """
        Enrich predictions with historical denial rates from past 835 data.
        Modifies predictions in-place.
        """
        try:
            import pandas as pd
            if adjustments_df is None or (hasattr(adjustments_df, "empty") and adjustments_df.empty):
                return predictions
            if "reason_code" not in adjustments_df.columns:
                return predictions

            # Build CPT → historical denial rate lookup from service-level adjustments
            if "cpt_hcpcs" in adjustments_df.columns:
                co_adj = adjustments_df[adjustments_df.get("group_code", pd.Series()) == "CO"]
                hist = (
                    co_adj.groupby("cpt_hcpcs")
                    .agg(denial_count=("amount", "count"))
                    .reset_index()
                )
                total_per_cpt = (
                    adjustments_df.groupby("cpt_hcpcs")
                    .agg(total=("amount", "count"))
                    .reset_index()
                )
                merged = hist.merge(total_per_cpt, on="cpt_hcpcs")
                merged["denial_rate"] = (merged["denial_count"] / merged["total"] * 100).round(1)
                rate_map = dict(zip(merged["cpt_hcpcs"], merged["denial_rate"]))

                for pred in predictions:
                    pred.historical_denial_rate = rate_map.get(pred.cpt_hcpcs)
        except Exception as exc:
            logger.warning(f"History enrichment failed: {exc}")

        return predictions


# ── Helpers ───────────────────────────────────────────────────────────────────

def _risk_level(score: float) -> str:
    if score >= 0.60:
        return "HIGH"
    if score >= 0.30:
        return "MEDIUM"
    return "LOW"


# ── Convenience: predict from ParseResult.data ────────────────────────────────

def predict_from_837p(parsed_data: dict, adjustments_df: Any = None) -> list[DenialPrediction]:
    """
    Run denial prediction on all claims from a parsed 837P result.

    Args:
        parsed_data:    The .data dict from a ParseResult (tx_type=837P).
                        This is the inner payload: {"claims": [...], "providers": [...]}
        adjustments_df: Optional historical 835 adjustments for enrichment.

    Returns:
        Flat list of DenialPrediction objects across all service lines.
    """
    predictor = DenialPredictor()
    # Support both inner payload {"claims": [...]} and full dict {"data": {"claims": [...]}}
    claims = parsed_data.get("claims") or parsed_data.get("data", {}).get("claims", [])
    all_predictions: list[DenialPrediction] = []

    for claim in claims:
        claim_dict: dict[str, Any] = {
            "claim_id":         getattr(claim, "claim_id", ""),
            "place_of_service": getattr(claim, "place_of_service", ""),
            "diagnoses":        [
                {"code": getattr(d, "code", ""), "qualifier": getattr(d, "qualifier", "")}
                for d in (getattr(claim, "diagnoses", []) or [])
            ],
            "service_lines": [],
        }

        for sl in (getattr(claim, "service_lines", []) or []):
            svc: dict[str, Any] = {
                "cpt_hcpcs":          getattr(sl, "cpt_hcpcs", ""),
                "billed_amount":      float(getattr(sl, "billed_amount", 0) or 0),
                "units":              float(getattr(sl, "units", 1) or 1),
                "diagnosis_pointers": getattr(sl, "diagnosis_pointers", ""),
                "ndc":                getattr(sl, "ndc", ""),
                "place_of_service":   getattr(sl, "place_of_service", "") or getattr(claim, "place_of_service", ""),
            }
            mods = getattr(sl, "modifiers", []) or []
            for i, m in enumerate(mods[:4], 1):
                svc[f"modifier_{i}"] = m
            claim_dict["service_lines"].append(svc)

        preds = predictor.predict_claim(claim_dict)
        all_predictions.extend(preds)

    if adjustments_df is not None:
        all_predictions = predictor.enrich_with_history(all_predictions, adjustments_df)

    return all_predictions


# ── Summary aggregation ───────────────────────────────────────────────────────

def prediction_summary(predictions: list[DenialPrediction]) -> dict[str, Any]:
    """Return high-level summary of prediction results."""
    if not predictions:
        return {"total": 0, "high": 0, "medium": 0, "low": 0, "top_factors": []}

    factor_counts: dict[str, int] = {}
    for p in predictions:
        for f in p.risk_factors:
            factor_counts[f] = factor_counts.get(f, 0) + 1

    top_factors = sorted(factor_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total":       len(predictions),
        "high":        sum(1 for p in predictions if p.risk_level == "HIGH"),
        "medium":      sum(1 for p in predictions if p.risk_level == "MEDIUM"),
        "low":         sum(1 for p in predictions if p.risk_level == "LOW"),
        "top_factors": [{"factor": f, "count": c} for f, c in top_factors],
    }
