from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class ClaimStatusResponse277(BaseModel):
    claim_id: str = ""
    payer_claim_number: str = ""
    clearinghouse_trace: str = ""
    payer_name: str = ""
    provider_npi: str = ""
    subscriber_name: str = ""
    subscriber_id: str = ""
    status_category: str = ""
    status_code: str = ""
    status_description: str = ""
    effective_date: Optional[date] = None
    dos: Optional[date] = None
    amount: Optional[float] = None

    model_config = {"arbitrary_types_allowed": True}
