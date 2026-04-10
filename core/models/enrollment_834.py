from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date


class Coverage834(BaseModel):
    maintenance_type: str = ""
    insurance_line_code: str = ""
    plan_coverage_description: str = ""
    coverage_level_code: str = ""
    benefit_begin: Optional[date] = None
    benefit_end: Optional[date] = None
    premium_amount: Optional[float] = None

    model_config = {"arbitrary_types_allowed": True}


class Member834(BaseModel):
    subscriber_indicator: str = ""
    relationship_code: str = ""
    maintenance_type: str = ""
    maintenance_type_desc: str = ""
    maintenance_reason: str = ""
    maintenance_reason_desc: str = ""
    benefit_status: str = ""
    cobra_qualifier: str = ""
    subscriber_id: str = ""
    ssn: str = ""
    last_name: str = ""
    first_name: str = ""
    dob: Optional[date] = None
    gender: str = ""
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    coverages: list[Coverage834] = []
    dependents: list[dict] = []

    model_config = {"arbitrary_types_allowed": True}
