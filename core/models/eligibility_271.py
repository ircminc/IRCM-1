from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class BenefitInfo271(BaseModel):
    benefit_code: str = ""
    coverage_level: str = ""
    service_type: str = ""
    insurance_type: str = ""
    plan_coverage_description: str = ""
    time_qualifier: str = ""
    monetary_amount: Optional[float] = None
    percent: Optional[float] = None
    in_network: str = ""
    message: str = ""


class EligibilityResponse271(BaseModel):
    hl_id: str = ""
    subscriber_id: str = ""
    subscriber_name: str = ""
    payer_name: str = ""
    payer_id: str = ""
    plan_name: str = ""
    group_number: str = ""
    coverage_active: Optional[bool] = None
    benefits: list[BenefitInfo271] = []
