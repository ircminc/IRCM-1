"""820 Payment Order / Remittance Advice parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount


def parse_820(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    header: dict = {}
    remittances: list[dict] = []
    adjustments: list[dict] = []
    current_remittance: dict | None = None

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "BPR":
            header["payment_amount"] = parse_amount(safe_get(seg, 2))
            header["credit_debit"] = safe_get(seg, 3)
            header["payment_method"] = safe_get(seg, 4)
            header["payment_date"] = parse_date(safe_get(seg, 16))

        elif seg_id == "TRN":
            header["trace_number"] = safe_get(seg, 2)
            header["originating_company_id"] = safe_get(seg, 3)

        elif seg_id == "N1":
            qualifier = safe_get(seg, 1)
            if qualifier == "PR":
                header["payer_name"] = safe_get(seg, 2)
                header["payer_id"] = safe_get(seg, 4)
            elif qualifier == "PE":
                header["payee_name"] = safe_get(seg, 2)
                header["payee_id"] = safe_get(seg, 4)

        elif seg_id == "ENT":
            if current_remittance:
                remittances.append(current_remittance)
            current_remittance = {
                "entity_number": safe_get(seg, 1),
                "entity_id_qualifier": safe_get(seg, 2),
                "entity_id": safe_get(seg, 3),
                "entity_name": "",
                "group_policy_number": "",
                "invoice_number": "",
                "amount_paid": None,
                "references": [],
            }

        elif seg_id == "NM1" and current_remittance is not None:
            current_remittance["entity_name"] = f"{safe_get(seg, 3)} {safe_get(seg, 4)}".strip()

        elif seg_id == "REF" and current_remittance is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "38":
                current_remittance["group_policy_number"] = safe_get(seg, 2)
            else:
                current_remittance["references"].append({
                    "qualifier": qualifier, "value": safe_get(seg, 2)
                })

        elif seg_id == "RMR" and current_remittance is not None:
            current_remittance["invoice_number"] = safe_get(seg, 2)
            current_remittance["amount_paid"] = parse_amount(safe_get(seg, 4))

        elif seg_id == "ADX":
            adjustments.append({
                "reason_code": safe_get(seg, 2),
                "amount": parse_amount(safe_get(seg, 1)),
                "reference_id": safe_get(seg, 3),
            })

    if current_remittance:
        remittances.append(current_remittance)

    return {"header": header, "remittances": remittances, "adjustments": adjustments}
