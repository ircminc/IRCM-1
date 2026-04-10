"""834 Benefit Enrollment parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount

MAINTENANCE_TYPE = {
    "001": "Change", "021": "Addition", "024": "Cancellation or Termination",
    "025": "Reinstatement", "030": "Audit or Compare", "032": "Employee Information Not Applicable",
}
MAINTENANCE_REASON = {
    "01": "Divorce", "02": "Birth", "03": "Death", "04": "Retirement",
    "05": "Adoption", "06": "Strike", "07": "Termination of Benefits",
    "08": "Termination of Employment", "09": "Voluntary Withdrawal",
    "AA": "Change in Identifying Data Elements", "AB": "Other",
}


def parse_834(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    members: list[dict] = []
    current_member: dict | None = None
    current_coverage: dict | None = None

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "INS":
            if current_member:
                if current_coverage:
                    current_member.setdefault("coverages", []).append(current_coverage)
                    current_coverage = None
                members.append(current_member)
            current_member = {
                "subscriber_indicator": safe_get(seg, 1),
                "relationship_code": safe_get(seg, 2),
                "maintenance_type": safe_get(seg, 3),
                "maintenance_type_desc": MAINTENANCE_TYPE.get(safe_get(seg, 3), safe_get(seg, 3)),
                "maintenance_reason": safe_get(seg, 4),
                "maintenance_reason_desc": MAINTENANCE_REASON.get(safe_get(seg, 4), safe_get(seg, 4)),
                "benefit_status": safe_get(seg, 5),
                "cobra_qualifier": safe_get(seg, 8),
                "subscriber_id": "",
                "ssn": "",
                "last_name": "", "first_name": "",
                "dob": None, "gender": "",
                "address_line1": "", "address_line2": "",
                "city": "", "state": "", "zip": "",
                "coverages": [],
                "dependents": [],
            }

        elif seg_id == "REF" and current_member is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "0F":
                current_member["subscriber_id"] = safe_get(seg, 2)
            elif qualifier == "ZZ":
                current_member["ssn"] = safe_get(seg, 2)

        elif seg_id == "NM1" and current_member is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "IL":
                current_member["last_name"] = safe_get(seg, 3)
                current_member["first_name"] = safe_get(seg, 4)

        elif seg_id == "N3" and current_member is not None:
            current_member["address_line1"] = safe_get(seg, 1)
            current_member["address_line2"] = safe_get(seg, 2)

        elif seg_id == "N4" and current_member is not None:
            current_member["city"] = safe_get(seg, 1)
            current_member["state"] = safe_get(seg, 2)
            current_member["zip"] = safe_get(seg, 3)

        elif seg_id == "DMG" and current_member is not None:
            current_member["dob"] = parse_date(safe_get(seg, 2))
            current_member["gender"] = safe_get(seg, 3)

        elif seg_id == "HD" and current_member is not None:
            if current_coverage:
                current_member["coverages"].append(current_coverage)
            current_coverage = {
                "maintenance_type": safe_get(seg, 1),
                "insurance_line_code": safe_get(seg, 3),
                "plan_coverage_description": safe_get(seg, 4),
                "coverage_level_code": safe_get(seg, 5),
                "benefit_begin": None,
                "benefit_end": None,
                "premium_amount": None,
            }

        elif seg_id == "DTP" and current_coverage is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "348":
                current_coverage["benefit_begin"] = parse_date(safe_get(seg, 3))
            elif qualifier == "349":
                current_coverage["benefit_end"] = parse_date(safe_get(seg, 3))

        elif seg_id == "AMT" and current_coverage is not None:
            if safe_get(seg, 1) == "P3":
                current_coverage["premium_amount"] = parse_amount(safe_get(seg, 2))

    if current_member:
        if current_coverage:
            current_member["coverages"].append(current_coverage)
        members.append(current_member)

    return {"members": members}
