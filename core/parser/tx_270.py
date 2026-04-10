"""270 Eligibility Inquiry parser."""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date


def parse_270(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    inquiries: list[dict] = []
    current: dict | None = None
    hl_level: str = ""

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        if seg_id == "BHT":
            pass

        elif seg_id == "HL":
            hl_level = safe_get(seg, 3)
            if hl_level == "22":  # subscriber
                current = {
                    "hl_id": safe_get(seg, 1),
                    "subscriber_id": "",
                    "subscriber_name": "",
                    "dob": None,
                    "gender": "",
                    "group_number": "",
                    "payer_id": "",
                    "payer_name": "",
                    "provider_npi": "",
                    "service_types": [],
                    "inquiry_date": None,
                }
                inquiries.append(current)

        elif seg_id == "NM1" and current is not None:
            qualifier = safe_get(seg, 1)
            if qualifier == "IL":
                current["subscriber_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")
                current["subscriber_id"] = safe_get(seg, 9)
            elif qualifier == "PR":
                current["payer_name"] = safe_get(seg, 3)
                current["payer_id"] = safe_get(seg, 9)
            elif qualifier in ("1P", "FA"):
                current["provider_npi"] = safe_get(seg, 9)

        elif seg_id == "REF" and current is not None:
            if safe_get(seg, 1) == "18":
                current["group_number"] = safe_get(seg, 2)

        elif seg_id == "DMG" and current is not None:
            current["dob"] = parse_date(safe_get(seg, 2))
            current["gender"] = safe_get(seg, 3)

        elif seg_id == "DTP" and current is not None:
            if safe_get(seg, 1) in ("291", "307"):
                current["inquiry_date"] = parse_date(safe_get(seg, 3))

        elif seg_id == "EQ" and current is not None:
            current["service_types"].append(safe_get(seg, 1))

    return {"inquiries": inquiries}
