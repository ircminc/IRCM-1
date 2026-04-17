"""
ISA/IEA and GS/GE envelope parsing with automatic delimiter detection.
The ISA segment is always exactly 106 characters; delimiters are at fixed byte positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field


# HIPAA version classification from the raw ISA12 value.
# ISA12 uses "00401" for X12 4010 and "00501" for X12 5010; other values are unknown.
SUPPORTED_HIPAA_VERSIONS = ("4010", "5010")


def classify_hipaa_version(raw_version: str) -> str:
    """Map the raw ISA12 value to '4010' / '5010' / 'unknown'."""
    if not raw_version:
        return "unknown"
    v = raw_version.strip()
    if v.startswith("004"):
        return "4010"
    if v.startswith("005"):
        return "5010"
    return "unknown"


@dataclass
class ISAEnvelope:
    isa_id: str = ""
    sender_id: str = ""
    receiver_id: str = ""
    date: str = ""
    time: str = ""
    control_number: str = ""
    version: str = ""          # raw ISA12 value, e.g. "00401" / "00501"
    hipaa_version: str = ""    # classified: "4010" | "5010" | "unknown"
    element_sep: str = "*"
    component_sep: str = ":"
    segment_term: str = "~"


@dataclass
class GSGroup:
    functional_id: str = ""
    sender_code: str = ""
    receiver_code: str = ""
    date: str = ""
    time: str = ""
    control_number: str = ""
    version: str = ""
    transaction_sets: list[dict] = field(default_factory=list)


def detect_delimiters(raw: bytes | str) -> tuple[str, str, str]:
    """
    Reads the first 106 bytes of an EDI stream to extract delimiters.
    Returns (element_sep, component_sep, segment_terminator).
    """
    if isinstance(raw, bytes):
        header = raw[:106].decode("ascii", errors="replace")
    else:
        header = raw[:106]
    if not header.startswith("ISA"):
        raise ValueError("File does not begin with ISA segment")
    element_sep = header[3]
    component_sep = header[104]
    segment_term = header[105]
    return element_sep, component_sep, segment_term


def parse_isa(segment_elements: list[str]) -> ISAEnvelope:
    env = ISAEnvelope()
    if len(segment_elements) < 16:
        return env
    env.sender_id = segment_elements[6].strip()
    env.receiver_id = segment_elements[8].strip()
    env.date = segment_elements[9]
    env.time = segment_elements[10]
    env.control_number = segment_elements[13]
    env.version = segment_elements[12]
    env.hipaa_version = classify_hipaa_version(env.version)
    return env


def parse_gs(segment_elements: list[str]) -> GSGroup:
    grp = GSGroup()
    if len(segment_elements) < 9:
        return grp
    grp.functional_id = segment_elements[1]
    grp.sender_code = segment_elements[2]
    grp.receiver_code = segment_elements[3]
    grp.date = segment_elements[4]
    grp.time = segment_elements[5]
    grp.control_number = segment_elements[6]
    grp.version = segment_elements[8]
    return grp
