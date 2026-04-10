from pydantic import BaseModel
from typing import Optional


class ISAEnvelopeModel(BaseModel):
    sender_id: str = ""
    receiver_id: str = ""
    date: str = ""
    time: str = ""
    control_number: str = ""
    version: str = ""
    element_sep: str = "*"
    component_sep: str = ":"
    segment_term: str = "~"


class GSGroupModel(BaseModel):
    functional_id: str = ""
    sender_code: str = ""
    receiver_code: str = ""
    date: str = ""
    time: str = ""
    control_number: str = ""
    version: str = ""
