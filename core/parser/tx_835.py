"""
835 (Electronic Remittance Advice) parser.
"""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount

# CAS group code descriptions
CAS_GROUP = {
    "CO": "Contractual Obligation",
    "PR": "Patient Responsibility",
    "OA": "Other Adjustment",
    "PI": "Payer Initiated",
    "CR": "Correction/Reversal",
}


def parse_835(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    header: dict = {}
    claim_payments: list[dict] = []
    provider_adjustments: list[dict] = []
    current_claim: dict | None = None
    current_service: dict | None = None

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "BPR":
            header["total_payment"] = parse_amount(safe_get(seg, 2))
            header["payment_method"] = safe_get(seg, 4)
            header["payment_date"] = parse_date(safe_get(seg, 16))
            header["transaction_handling"] = safe_get(seg, 1)

        elif seg_id == "TRN":
            header["check_eft_number"] = safe_get(seg, 2)
            header["payer_id"] = safe_get(seg, 3)

        elif seg_id == "DTM" and safe_get(seg, 1) == "405":
            header["production_date"] = parse_date(safe_get(seg, 2))

        elif seg_id == "N1" and safe_get(seg, 1) == "PR":
            header["payer_name"] = safe_get(seg, 2)
            header["payer_id_qualifier"] = safe_get(seg, 3)
            header["payer_id_value"] = safe_get(seg, 4)

        elif seg_id == "N1" and safe_get(seg, 1) == "PE":
            header["payee_name"] = safe_get(seg, 2)
            header["payee_npi"] = safe_get(seg, 4)

        # Claim payment (CLP)
        elif seg_id == "CLP":
            if current_claim is not None:
                if current_service:
                    current_claim.setdefault("services", []).append(current_service)
                    current_service = None
                claim_payments.append(current_claim)
            current_claim = {
                "clp_id": safe_get(seg, 1),
                "status_code": safe_get(seg, 2),
                "billed": parse_amount(safe_get(seg, 3)),
                "paid": parse_amount(safe_get(seg, 4)),
                "patient_responsibility": parse_amount(safe_get(seg, 5)),
                "claim_filing_indicator": safe_get(seg, 6),
                "payer_claim_number": safe_get(seg, 7),
                "facility_type": safe_get(seg, 8),
                "patient_name": "",
                "adjustments": [],
                "services": [],
            }

        elif seg_id == "NM1" and safe_get(seg, 1) == "QC" and current_claim is not None:
            current_claim["patient_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")
            current_claim["patient_id"] = safe_get(seg, 9)

        # Claim-level adjustments
        elif seg_id == "CAS" and current_claim is not None and current_service is None:
            group_code = safe_get(seg, 1)
            # CAS can have up to 6 reason code/amount pairs (elements 2-3, 4-5, 6-7, 8-9, 10-11, 12-13)
            for i in range(0, 6):
                rc = safe_get(seg, 2 + i * 3)
                amt = safe_get(seg, 3 + i * 3)
                if rc:
                    current_claim["adjustments"].append({
                        "group_code": group_code,
                        "group_description": CAS_GROUP.get(group_code, group_code),
                        "reason_code": rc,
                        "amount": parse_amount(amt),
                    })

        # Service line (SVC)
        elif seg_id == "SVC" and current_claim is not None:
            if current_service:
                current_claim["services"].append(current_service)
            proc_composite = safe_get(seg, 1)
            parts = proc_composite.split(cs)
            current_service = {
                "cpt_hcpcs": parts[1] if len(parts) > 1 else parts[0],
                "billed": parse_amount(safe_get(seg, 2)),
                "paid": parse_amount(safe_get(seg, 3)),
                "ndc": safe_get(seg, 6),
                "adjustments": [],
            }

        # Service line adjustments
        elif seg_id == "CAS" and current_service is not None:
            group_code = safe_get(seg, 1)
            for i in range(0, 6):
                rc = safe_get(seg, 2 + i * 3)
                amt = safe_get(seg, 3 + i * 3)
                if rc:
                    current_service["adjustments"].append({
                        "group_code": group_code,
                        "group_description": CAS_GROUP.get(group_code, group_code),
                        "reason_code": rc,
                        "amount": parse_amount(amt),
                    })

        # Provider-level adjustments (PLB)
        elif seg_id == "PLB":
            provider_adjustments.append({
                "provider_npi": safe_get(seg, 1),
                "fiscal_period": safe_get(seg, 2),
                "reason_code": safe_get(seg, 3).split(cs)[0] if cs in safe_get(seg, 3) else safe_get(seg, 3),
                "reference_id": safe_get(seg, 3).split(cs)[1] if cs in safe_get(seg, 3) else "",
                "amount": parse_amount(safe_get(seg, 4)),
            })

    # Flush
    if current_claim is not None:
        if current_service:
            current_claim["services"].append(current_service)
        claim_payments.append(current_claim)

    return {
        "header": header,
        "claim_payments": claim_payments,
        "provider_adjustments": provider_adjustments,
    }
