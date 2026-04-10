"""276 Claim Status Request parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date


def parse_276(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    inquiries: list[dict] = []
    current: dict | None = None
    hl_level: str = ""

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "HL":
            hl_level = safe_get(seg, 3)
            if hl_level == "PT":  # patient/claim level
                current = {
                    "trace_number": "",
                    "payer_id": "", "payer_name": "",
                    "provider_npi": "", "provider_name": "",
                    "subscriber_id": "", "subscriber_name": "",
                    "claim_id": "",
                    "dos_from": None, "dos_to": None,
                    "request_date": None,
                }
                inquiries.append(current)

        elif seg_id == "NM1" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "PR":
                current["payer_name"] = safe_get(seg, 3)
                current["payer_id"] = safe_get(seg, 9)
            elif qualifier in ("1P", "FA"):
                current["provider_name"] = f"{safe_get(seg, 3)} {safe_get(seg, 4)}".strip()
                current["provider_npi"] = safe_get(seg, 9)
            elif qualifier == "IL":
                current["subscriber_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")
                current["subscriber_id"] = safe_get(seg, 9)

        elif seg_id == "TRN" and current is not None:
            current["trace_number"] = safe_get(seg, 2)

        elif seg_id == "REF" and current is not None:
            if safe_get(seg, 1) == "1K":
                current["claim_id"] = safe_get(seg, 2)

        elif seg_id == "DTP" and current is not None:
            qualifier = safe_get(seg, 1)
            val = safe_get(seg, 3)
            if qualifier == "232":
                if "-" in val:
                    parts = val.split("-")
                    current["dos_from"] = parse_date(parts[0])
                    current["dos_to"] = parse_date(parts[1]) if len(parts) > 1 else None
                else:
                    current["dos_from"] = parse_date(val)
            elif qualifier == "472":
                current["request_date"] = parse_date(val)

    return {"inquiries": inquiries}
