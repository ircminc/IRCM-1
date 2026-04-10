from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class Adjustment835(BaseModel):
    group_code: str = ""
    group_description: str = ""
    reason_code: str = ""
    amount: Optional[float] = None


class ServicePayment835(BaseModel):
    cpt_hcpcs: str = ""
    billed: Optional[float] = None
    paid: Optional[float] = None
    ndc: str = ""
    adjustments: list[Adjustment835] = []


class ClaimPayment835(BaseModel):
    clp_id: str = ""
    status_code: str = ""
    billed: Optional[float] = None
    paid: Optional[float] = None
    patient_responsibility: Optional[float] = None
    claim_filing_indicator: str = ""
    payer_claim_number: str = ""
    facility_type: str = ""
    patient_name: str = ""
    patient_id: str = ""
    adjustments: list[Adjustment835] = []
    services: list[ServicePayment835] = []


class ProviderAdjustment835(BaseModel):
    provider_npi: str = ""
    fiscal_period: str = ""
    reason_code: str = ""
    reference_id: str = ""
    amount: Optional[float] = None


class Remittance835Header(BaseModel):
    total_payment: Optional[float] = None
    payment_method: str = ""
    payment_date: Optional[date] = None
    transaction_handling: str = ""
    check_eft_number: str = ""
    payer_id: str = ""
    payer_name: str = ""
    payer_id_qualifier: str = ""
    payer_id_value: str = ""
    payee_name: str = ""
    payee_npi: str = ""
    production_date: Optional[date] = None

    model_config = {"arbitrary_types_allowed": True}
