"""271 Eligibility Response parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount

BENEFIT_CODES = {
    "1": "Medical Care", "2": "Surgical", "3": "Consultation", "4": "Diagnostic X-Ray",
    "5": "Diagnostic Lab", "6": "Radiation Therapy", "7": "Anesthesia", "8": "Surgical Assistance",
    "30": "Health Benefit Plan Coverage", "33": "Chiropractic", "35": "Dental Care",
    "47": "Hospital", "48": "Hospital - Inpatient", "50": "Hospital - Outpatient",
    "86": "Emergency Services", "88": "Preventive Care", "98": "Professional (Physician) Visit - Office",
    "UC": "Urgent Care",
}

COVERAGE_LEVEL = {
    "FAM": "Family", "IND": "Individual", "EMP": "Employee Only",
    "ESP": "Employee and Spouse", "ECH": "Employee and Children",
}


def parse_271(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    responses: list[dict] = []
    current: dict | None = None
    current_benefit: dict | None = None
    hl_level: str = ""

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "HL":
            hl_level = safe_get(seg, 3)
            if hl_level == "22":
                current = {
                    "hl_id": safe_get(seg, 1),
                    "subscriber_id": "", "subscriber_name": "",
                    "payer_name": "", "payer_id": "",
                    "plan_name": "", "group_number": "",
                    "coverage_active": None,
                    "benefits": [],
                }
                responses.append(current)

        elif seg_id == "NM1" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "IL":
                current["subscriber_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")
                current["subscriber_id"] = safe_get(seg, 9)
            elif qualifier == "PR":
                current["payer_name"] = safe_get(seg, 3)
                current["payer_id"] = safe_get(seg, 9)

        elif seg_id == "EB" and current is not None:
            eb_code = safe_get(seg, 1)
            # EB01=1 means active coverage, 6 means inactive
            if eb_code == "1":
                current["coverage_active"] = True
            elif eb_code == "6":
                current["coverage_active"] = False
            benefit = {
                "benefit_code": eb_code,
                "coverage_level": COVERAGE_LEVEL.get(safe_get(seg, 2), safe_get(seg, 2)),
                "service_type": safe_get(seg, 3),
                "insurance_type": safe_get(seg, 4),
                "plan_coverage_description": safe_get(seg, 5),
                "time_qualifier": safe_get(seg, 6),
                "monetary_amount": parse_amount(safe_get(seg, 7)),
                "percent": parse_amount(safe_get(seg, 8)),
                "in_network": safe_get(seg, 12),
            }
            current["benefits"].append(benefit)
            current_benefit = benefit

        elif seg_id == "MSG" and current_benefit is not None:
            current_benefit["message"] = safe_get(seg, 1)

        elif seg_id == "REF" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "18":
                current["group_number"] = safe_get(seg, 2)
            elif qualifier == "1L":
                current["plan_name"] = safe_get(seg, 2)

    return {"responses": responses}
