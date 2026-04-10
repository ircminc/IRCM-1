from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class ClaimStatusInquiry276(BaseModel):
    trace_number: str = ""
    payer_id: str = ""
    payer_name: str = ""
    provider_npi: str = ""
    provider_name: str = ""
    subscriber_id: str = ""
    subscriber_name: str = ""
    claim_id: str = ""
    dos_from: Optional[date] = None
    dos_to: Optional[date] = None
    request_date: Optional[date] = None

    model_config = {"arbitrary_types_allowed": True}
