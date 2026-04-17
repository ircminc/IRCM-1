"""
pytest fixtures for ANSI X12 Medical Billing Converter tests.

Provides:
  - Minimal valid ISA/GS/ST/SE/GE/IEA envelope wrapper
  - Sample 837P and 835 EDI strings
  - In-memory parsed result dicts matching what core/parser returns
"""
from __future__ import annotations

import io
import sys
import os

import pytest

# Ensure project root is on sys.path so imports work without install
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── EDI Building Blocks ────────────────────────────────────────────────────────

def _wrap_edi(
    gs_type: str,
    st_type: str,
    tx_segments: str,
    isa_version: str = "00501",
    gs_version: str = "005010X222A2",
) -> str:
    """Wrap transaction segments in a valid ISA/GS/ST envelope.

    isa_version/gs_version default to 5010; pass 00401/004010X098A1 for 4010.
    """
    return (
        f"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
        f"*260101*1200*^*{isa_version}*000000001*0*P*:~"
        f"GS*{gs_type}*SENDERGS*RECEIVERGS*20260101*1200*1*X*{gs_version}~"
        f"ST*{st_type}*0001~"
        f"{tx_segments}"
        "SE*2*0001~"
        "GE*1*1~"
        "IEA*1*000000001~"
    )


SAMPLE_837P_EDI = _wrap_edi(
    "HC", "837",
    (
        "BHT*0019*00*000001*20260101*1200*CH~"
        "NM1*41*2*TEST BILLING*****XX*1234567890~"
        "PER*IC*CONTACT*TE*5551234567~"
        "NM1*40*2*TEST PAYER*****PI*PAYERID~"
        "HL*1**20*1~"
        "PRV*BI*PXC*207Q00000X~"
        "NM1*85*2*BILLING PROVIDER*****XX*1234567890~"
        "N3*123 MAIN ST~"
        "N4*ANYTOWN*CA*90210~"
        "HL*2*1*22*1~"
        "SBR*P*18*******MB~"
        "NM1*IL*1*DOE*JOHN****MI*ABC123456~"
        "N3*456 ELM ST~"
        "N4*ANYTOWN*CA*90210~"
        "DMG*D8*19800101*M~"
        "NM1*PR*2*MEDICARE*****PI*PAYERID~"
        "HL*3*2*23*0~"
        "PAT*19~"
        "NM1*QC*1*DOE*JANE~"
        "CLM*CLAIM001*150.00***11:B:1*Y*A*Y*I~"
        "DTP*472*D8*20260101~"
        "HI*ABK:Z23.0~"
        "LX*1~"
        "SV1*HC:99213*75.00*UN*1***1~"
        "DTP*472*D8*20260101~"
        "LX*2~"
        "SV1*HC:85025*75.00*UN*1***1~"
        "DTP*472*D8*20260101~"
    ),
)

SAMPLE_835_EDI = _wrap_edi(
    "HP", "835",
    (
        "BPR*I*250.00*C*ACH*CCP*01*999999999*DA*1234567890*1122334455**01*"
        "555555555*DA*9876543210*20260115~"
        "TRN*1*CHECK12345*1122334455~"
        "DTM*405*20260115~"
        "N1*PR*MEDICARE*XX*PAYERID~"
        "N1*PE*TEST BILLING GROUP*XX*1234567890~"
        "CLP*CLAIM001*1*150.00*120.00*10.00*MB*PAYERCLAIM001~"
        "NM1*QC*1*DOE*JANE~"
        "SVC*HC:99213*75.00*60.00~"
        "DTM*472*20260101~"
        "CAS*CO*45*15.00~"
        "SVC*HC:85025*75.00*60.00~"
        "DTM*472*20260101~"
        "CAS*CO*45*15.00~"
    ),
)

SAMPLE_270_EDI = _wrap_edi(
    "HS", "270",
    (
        "BHT*0022*13*TRACE001*20260101*1200~"
        "HL*1**20*1~"
        "NM1*PR*2*MEDICARE*****PI*PAYERID~"
        "HL*2*1*21*1~"
        "NM1*1P*2*PROVIDER GROUP*****XX*1234567890~"
        "HL*3*2*22*0~"
        "TRN*1*TRACE001~"
        "NM1*IL*1*DOE*JOHN****MI*ABC123456~"
        "DMG*D8*19800101*M~"
        "DTP*291*D8*20260101~"
        "EQ*30~"
    ),
)


# 4010 variant of the 835 sample — identical segments, older envelope version.
SAMPLE_835_EDI_4010 = _wrap_edi(
    "HP", "835",
    (
        "BPR*I*250.00*C*ACH*CCP*01*999999999*DA*1234567890*1122334455**01*"
        "555555555*DA*9876543210*20260115~"
        "TRN*1*CHECK12345*1122334455~"
        "DTM*405*20260115~"
        "N1*PR*MEDICARE*XX*PAYERID~"
        "N1*PE*TEST BILLING GROUP*XX*1234567890~"
        "CLP*CLAIM001*1*150.00*120.00*10.00*MB*PAYERCLAIM001~"
        "NM1*QC*1*DOE*JANE~"
        "SVC*HC:99213*75.00*60.00~"
        "DTM*472*20260101~"
        "CAS*CO*45*15.00~"
    ),
    isa_version="00401",
    gs_version="004010X091A1",
)


@pytest.fixture
def sample_837p_bytes() -> bytes:
    return SAMPLE_837P_EDI.encode("utf-8")


@pytest.fixture
def sample_835_bytes() -> bytes:
    return SAMPLE_835_EDI.encode("utf-8")


@pytest.fixture
def sample_835_4010_bytes() -> bytes:
    return SAMPLE_835_EDI_4010.encode("utf-8")


@pytest.fixture
def sample_270_bytes() -> bytes:
    return SAMPLE_270_EDI.encode("utf-8")


@pytest.fixture
def sample_837p_io(sample_837p_bytes):
    return io.BytesIO(sample_837p_bytes)


@pytest.fixture
def sample_835_io(sample_835_bytes):
    return io.BytesIO(sample_835_bytes)
