"""277 Claim Status Response parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount

STATUS_CATEGORY = {
    "A0": "Acknowledged", "A1": "Acknowledged/In Process",
    "A2": "Acknowledged – Returned as unprocessable",
    "A3": "Acknowledged – Returned to provider",
    "A4": "Acknowledged/In Process - Waiting",
    "A6": "Accepted",
    "A7": "Accepted – Waiting for additional information",
    "A8": "Accepted – Waiting for document",
    "E0": "Response not possible – System status",
    "F0": "Finalized", "F1": "Finalized/Payment", "F2": "Finalized/Denial",
    "F3": "Finalized/Revised", "F4": "Finalized/Adjudication Complete",
    "P0": "Pending", "P1": "Pending/In Process",
    "P2": "Pending – Waiting for additional information",
    "P3": "Pending – Waiting for document",
    "R0": "Requests for additional information",
    "R3": "Returned to provider – Unprocessable",
}


def parse_277(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    responses: list[dict] = []
    current: dict | None = None

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "HL":
            hl_level = safe_get(seg, 3)
            if hl_level in ("PT", "23"):  # patient/claim level
                current = {
                    "claim_id": "", "payer_claim_number": "",
                    "clearinghouse_trace": "",
                    "payer_name": "", "provider_npi": "",
                    "subscriber_name": "", "subscriber_id": "",
                    "status_category": "", "status_code": "",
                    "status_description": "",
                    "effective_date": None, "dos": None,
                    "amount": None,
                }
                responses.append(current)

        elif seg_id == "NM1" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "PR":
                current["payer_name"] = safe_get(seg, 3)
            elif qualifier in ("1P", "FA"):
                current["provider_npi"] = safe_get(seg, 9)
            elif qualifier == "IL":
                current["subscriber_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")
                current["subscriber_id"] = safe_get(seg, 9)

        elif seg_id == "TRN" and current is not None:
            current["claim_id"] = safe_get(seg, 2)

        elif seg_id == "REF" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "1K":
                current["payer_claim_number"] = safe_get(seg, 2)
            elif qualifier == "D9":
                current["clearinghouse_trace"] = safe_get(seg, 2)

        elif seg_id == "STC" and current is not None:
            composite = safe_get(seg, 1)
            parts = composite.split(":")
            cat_code = parts[0] if parts else ""
            status_code = parts[1] if len(parts) > 1 else ""
            current["status_category"] = cat_code
            current["status_code"] = status_code
            current["status_description"] = STATUS_CATEGORY.get(cat_code, cat_code)
            current["effective_date"] = parse_date(safe_get(seg, 2))
            current["amount"] = parse_amount(safe_get(seg, 3))

        elif seg_id == "DTP" and current is not None:
            if safe_get(seg, 1) == "472":
                current["dos"] = parse_date(safe_get(seg, 3))

    return {"responses": responses, "status_category_map": STATUS_CATEGORY}
