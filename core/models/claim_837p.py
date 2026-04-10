from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class Provider837P(BaseModel):
    type: str = ""  # billing, rendering, referring
    npi: str = ""
    name: str = ""
    entity_type: str = ""
    tax_id: str = ""
    address: str = ""
    phone: str = ""
    taxonomy: str = ""


class DiagnosisCode(BaseModel):
    qualifier: str = ""
    code: str = ""


class ServiceLine837P(BaseModel):
    line_number: str = ""
    cpt_hcpcs: str = ""
    modifier_1: str = ""
    modifier_2: str = ""
    modifier_3: str = ""
    modifier_4: str = ""
    billed_amount: Optional[float] = None
    units: str = ""
    place_of_service: str = ""
    diagnosis_pointers: str = ""
    ndc: str = ""
    rendering_provider_npi: str = ""
    rendering_provider_name: str = ""


class Claim837P(BaseModel):
    claim_id: str = ""
    total_billed: Optional[float] = None
    place_of_service: str = ""
    claim_frequency: str = ""
    assignment_of_benefits: str = ""
    insurance_type: str = ""
    claim_filing_indicator: str = ""
    group_number: str = ""
    payer_name: str = ""
    payer_id: str = ""
    payer_claim_number: str = ""
    claim_note: str = ""
    dos_from: Optional[date] = None
    dos_to: Optional[date] = None
    billing_provider: dict = {}
    subscriber: dict = {}
    patient: dict = {}
    diagnoses: list[DiagnosisCode] = []
    service_lines: list[ServiceLine837P] = []

    model_config = {"arbitrary_types_allowed": True}
