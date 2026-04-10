"""
837P (Professional Claims) parser.
Extracts claims, service lines, providers, diagnoses.
"""
from __future__ import annotations
from typing import Any
from .normalizer import safe_get, parse_date, parse_amount


def parse_837p(segments: list[list[str]], es: str, cs: str) -> dict[str, Any]:
    claims: list[dict] = []
    providers: list[dict] = []
    current_claim: dict | None = None
    current_service_line: dict | None = None
    current_billing_provider: dict = {}
    current_subscriber: dict = {}
    current_patient: dict = {}
    loop_context: str = ""

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()

        # --- Billing Provider (Loop 2000A/2010AA) ---
        if seg_id == "NM1" and safe_get(seg, 1) == "85":
            current_billing_provider = {
                "npi": safe_get(seg, 9),
                "last_name_org": safe_get(seg, 3),
                "first_name": safe_get(seg, 4),
                "entity_type": safe_get(seg, 2),
            }
            loop_context = "billing_provider"

        # --- Subscriber (Loop 2010BA) ---
        elif seg_id == "NM1" and safe_get(seg, 1) == "IL":
            current_subscriber = {
                "last_name": safe_get(seg, 3),
                "first_name": safe_get(seg, 4),
                "member_id": safe_get(seg, 9),
                "id_qualifier": safe_get(seg, 8),
            }
            loop_context = "subscriber"

        # --- Patient (Loop 2010CA) ---
        elif seg_id == "NM1" and safe_get(seg, 1) == "QC":
            current_patient = {
                "last_name": safe_get(seg, 3),
                "first_name": safe_get(seg, 4),
            }
            loop_context = "patient"

        # --- Payer (Loop 2010BB) ---
        elif seg_id == "NM1" and safe_get(seg, 1) == "PR":
            if current_claim is not None:
                current_claim["payer_name"] = safe_get(seg, 3)
                current_claim["payer_id"] = safe_get(seg, 9)
            loop_context = "payer"

        # --- Subscriber demographics ---
        elif seg_id == "DMG":
            dob_raw = safe_get(seg, 2)
            if loop_context == "subscriber":
                current_subscriber["dob"] = parse_date(dob_raw)
                current_subscriber["gender"] = safe_get(seg, 3)
            elif loop_context == "patient":
                current_patient["dob"] = parse_date(dob_raw)
                current_patient["gender"] = safe_get(seg, 3)

        # --- Subscriber group info ---
        elif seg_id == "SBR":
            if current_claim is not None:
                current_claim["insurance_type"] = safe_get(seg, 1)
                current_claim["group_number"] = safe_get(seg, 3)
                current_claim["claim_filing_indicator"] = safe_get(seg, 9)

        # --- Claim (Loop 2300) ---
        elif seg_id == "CLM":
            # Save previous claim
            if current_claim is not None:
                if current_service_line:
                    current_claim.setdefault("service_lines", []).append(current_service_line)
                    current_service_line = None
                claims.append(current_claim)
            current_claim = {
                "claim_id": safe_get(seg, 1),
                "total_billed": parse_amount(safe_get(seg, 2)),
                "place_of_service": safe_get(seg, 5).split(cs)[0] if cs in safe_get(seg, 5) else safe_get(seg, 5),
                "claim_frequency": safe_get(seg, 11),
                "assignment_of_benefits": safe_get(seg, 8),
                "billing_provider": dict(current_billing_provider),
                "subscriber": dict(current_subscriber),
                "patient": dict(current_patient),
                "payer_name": "",
                "payer_id": "",
                "group_number": "",
                "claim_filing_indicator": "",
                "insurance_type": "",
                "dos_from": None,
                "dos_to": None,
                "diagnoses": [],
                "service_lines": [],
                "claim_note": "",
            }
            loop_context = "claim"

        # --- Service dates ---
        elif seg_id == "DTP" and safe_get(seg, 1) == "472":
            date_val = safe_get(seg, 3)
            qualifier = safe_get(seg, 2)
            if current_claim:
                if "-" in date_val:
                    parts = date_val.split("-")
                    current_claim["dos_from"] = parse_date(parts[0])
                    current_claim["dos_to"] = parse_date(parts[1]) if len(parts) > 1 else None
                elif qualifier == "RD8" and "-" not in date_val:
                    current_claim["dos_from"] = parse_date(date_val)
                else:
                    current_claim["dos_from"] = parse_date(date_val)

        # --- Claim reference ---
        elif seg_id == "REF" and safe_get(seg, 1) == "D9":
            if current_claim:
                current_claim["payer_claim_number"] = safe_get(seg, 2)

        # --- Diagnosis codes (HI segment) ---
        elif seg_id == "HI" and current_claim is not None:
            for i in range(1, len(seg)):
                code_composite = seg[i]
                if not code_composite:
                    continue
                parts = code_composite.split(cs)
                qualifier = parts[0] if parts else ""
                code = parts[1] if len(parts) > 1 else ""
                if qualifier in ("ABK", "BK", "ABF", "BF", "ABJ", "BJ") and code:
                    current_claim["diagnoses"].append({"qualifier": qualifier, "code": code})

        # --- Claim note ---
        elif seg_id == "NTE" and current_claim is not None:
            current_claim["claim_note"] = safe_get(seg, 2)

        # --- Rendering provider in service line ---
        elif seg_id == "NM1" and safe_get(seg, 1) in ("82", "DN", "77") and current_service_line is not None:
            current_service_line["rendering_provider_npi"] = safe_get(seg, 9)
            current_service_line["rendering_provider_name"] = f"{safe_get(seg, 3)}, {safe_get(seg, 4)}".strip(", ")

        # --- Service Line (LX counter) ---
        elif seg_id == "LX" and current_claim is not None:
            if current_service_line:
                current_claim["service_lines"].append(current_service_line)
            current_service_line = {
                "line_number": safe_get(seg, 1),
                "cpt_hcpcs": "",
                "modifier_1": "",
                "modifier_2": "",
                "modifier_3": "",
                "modifier_4": "",
                "billed_amount": None,
                "units": None,
                "place_of_service": "",
                "diagnosis_pointers": "",
                "ndc": "",
                "rendering_provider_npi": "",
                "rendering_provider_name": "",
            }

        # --- Service Line detail (SV1) ---
        elif seg_id == "SV1" and current_service_line is not None:
            proc_composite = safe_get(seg, 1)
            parts = proc_composite.split(cs)
            current_service_line["cpt_hcpcs"] = parts[1] if len(parts) > 1 else parts[0]
            if len(parts) > 2:
                current_service_line["modifier_1"] = parts[2]
            if len(parts) > 3:
                current_service_line["modifier_2"] = parts[3]
            if len(parts) > 4:
                current_service_line["modifier_3"] = parts[4]
            if len(parts) > 5:
                current_service_line["modifier_4"] = parts[5]
            current_service_line["billed_amount"] = parse_amount(safe_get(seg, 2))
            current_service_line["units"] = safe_get(seg, 4)
            current_service_line["place_of_service"] = safe_get(seg, 5)
            current_service_line["diagnosis_pointers"] = safe_get(seg, 7)

        # --- NDC for drugs ---
        elif seg_id == "LIN" and current_service_line is not None:
            if safe_get(seg, 2) == "N4":
                current_service_line["ndc"] = safe_get(seg, 3)

        # --- Collect providers ---
        elif seg_id == "NM1" and safe_get(seg, 1) == "85":
            prov = {
                "type": "billing",
                "npi": safe_get(seg, 9),
                "name": f"{safe_get(seg, 3)} {safe_get(seg, 4)}".strip(),
                "entity_type": safe_get(seg, 2),
            }
            if prov not in providers:
                providers.append(prov)

    # Flush last claim/service line
    if current_claim is not None:
        if current_service_line:
            current_claim["service_lines"].append(current_service_line)
        claims.append(current_claim)

    return {"claims": claims, "providers": providers}
