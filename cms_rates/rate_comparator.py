"""
Compare 837P billed amounts against CMS PFS and ASP rates.
Rate flags:
  OVER_300PCT  — billed > 300% of Medicare non-facility rate (possible compliance issue)
  UNDER_100PCT — billed < 100% of Medicare rate (possible underbilling)
  WITHIN_RANGE — billed between 100% and 300% of Medicare rate
  NO_RATE      — no CMS rate data available
"""
from __future__ import annotations
from dataclasses import dataclass
from config import settings
from .pfs_client import lookup_pfs_rate
from .asp_client import lookup_asp_rate

DRUG_PREFIXES = ("J", "Q", "C")  # Common drug/biologic code prefixes


@dataclass
class RateComparison:
    cpt_hcpcs: str
    modifier: str
    description: str
    billed_amount: float | None
    pfs_non_facility_rate: float | None
    pfs_facility_rate: float | None
    work_rvu: float | None
    asp_payment_limit: float | None
    vs_non_facility_pct: float | None   # (billed / pfs_nf) * 100
    vs_facility_pct: float | None
    flag: str                            # OVER_300PCT | UNDER_100PCT | WITHIN_RANGE | NO_RATE
    rate_source: str

    def to_dict(self) -> dict:
        return {
            "cpt_hcpcs":             self.cpt_hcpcs,
            "modifier":              self.modifier,
            "description":           self.description,
            "billed_amount":         self.billed_amount,
            "pfs_non_facility_rate": self.pfs_non_facility_rate,
            "pfs_facility_rate":     self.pfs_facility_rate,
            "work_rvu":              self.work_rvu,
            "asp_payment_limit":     self.asp_payment_limit,
            "vs_non_facility_pct":   self.vs_non_facility_pct,
            "vs_facility_pct":       self.vs_facility_pct,
            "flag":                  self.flag,
            "rate_source":           self.rate_source,
        }


def _classify_flag(billed: float | None, reference_rate: float | None) -> str:
    if billed is None or reference_rate is None or reference_rate == 0:
        return "NO_RATE"
    pct = (billed / reference_rate) * 100
    if pct > settings.rate_flag_over_pct:      # > 300%
        return "OVER_300PCT"
    elif pct < settings.rate_flag_under_pct:   # < 100%
        return "UNDER_100PCT"
    return "WITHIN_RANGE"


def compare_service_line(
    cpt_hcpcs: str,
    modifier: str = "",
    billed_amount: float | None = None,
) -> RateComparison:
    """
    Compare a single service line's billed amount against CMS rates.
    Checks PFS for procedure codes, ASP for drug J-codes.
    """
    cpt = cpt_hcpcs.strip().upper()
    mod = modifier.strip().upper()

    pfs_data = lookup_pfs_rate(cpt, mod)
    asp_data = None
    if cpt[:1] in DRUG_PREFIXES:
        asp_data = lookup_asp_rate(cpt)

    nf_rate  = pfs_data["non_facility_rate"] if pfs_data else None
    fac_rate = pfs_data["facility_rate"]     if pfs_data else None
    work_rvu = pfs_data["work_rvu"]          if pfs_data else None
    desc     = (pfs_data["description"]      if pfs_data else "") or (asp_data["description"] if asp_data else "")
    asp_lim  = asp_data["payment_limit"]     if asp_data else None

    # Use non-facility rate as primary reference; fall back to ASP for drug codes
    reference = nf_rate or asp_lim
    flag = _classify_flag(billed_amount, reference)

    vs_nf  = ((billed_amount / nf_rate)  * 100) if billed_amount and nf_rate  else None
    vs_fac = ((billed_amount / fac_rate) * 100) if billed_amount and fac_rate else None

    source_parts = []
    if pfs_data:
        source_parts.append(pfs_data["source"])
    if asp_data:
        source_parts.append(asp_data["source"])

    return RateComparison(
        cpt_hcpcs=cpt, modifier=mod, description=desc,
        billed_amount=billed_amount,
        pfs_non_facility_rate=nf_rate, pfs_facility_rate=fac_rate, work_rvu=work_rvu,
        asp_payment_limit=asp_lim,
        vs_non_facility_pct=vs_nf, vs_facility_pct=vs_fac,
        flag=flag,
        rate_source=", ".join(source_parts) if source_parts else "NO_DATA",
    )


def compare_claims(claims: list[dict]) -> list[dict]:
    """
    Run rate comparison for all service lines across a list of 837P claims.
    Returns a flat list of RateComparison.to_dict() records.
    """
    results = []
    seen: dict[tuple, RateComparison] = {}
    for claim in claims:
        for sl in claim.get("service_lines", []):
            cpt = sl.get("cpt_hcpcs", "")
            mod = sl.get("modifier_1", "")
            billed = sl.get("billed_amount")
            key = (cpt, mod)
            if key not in seen:
                comp = compare_service_line(cpt, mod, billed)
                seen[key] = comp
            else:
                # Update billed amount to latest seen (or average — use latest for simplicity)
                comp = seen[key]
            results.append({**comp.to_dict(), "claim_id": claim.get("claim_id",""), "line_number": sl.get("line_number","")})
    return results
