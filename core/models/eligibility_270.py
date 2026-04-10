from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class EligibilityInquiry270(BaseModel):
    hl_id: str = ""
    subscriber_id: str = ""
    subscriber_name: str = ""
    dob: Optional[date] = None
    gender: str = ""
    group_number: str = ""
    payer_id: str = ""
    payer_name: str = ""
    provider_npi: str = ""
    service_types: list[str] = []
    inquiry_date: Optional[date] = None

    model_config = {"arbitrary_types_allowed": True}
