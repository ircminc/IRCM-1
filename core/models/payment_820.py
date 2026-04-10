from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class Remittance820(BaseModel):
    entity_number: str = ""
    entity_id_qualifier: str = ""
    entity_id: str = ""
    entity_name: str = ""
    group_policy_number: str = ""
    invoice_number: str = ""
    amount_paid: Optional[float] = None
    references: list[dict] = []


class Adjustment820(BaseModel):
    reason_code: str = ""
    amount: Optional[float] = None
    reference_id: str = ""


class Payment820Header(BaseModel):
    payment_amount: Optional[float] = None
    credit_debit: str = ""
    payment_method: str = ""
    payment_date: Optional[date] = None
    trace_number: str = ""
    originating_company_id: str = ""
    payer_name: str = ""
    payer_id: str = ""
    payee_name: str = ""
    payee_id: str = ""

    model_config = {"arbitrary_types_allowed": True}
