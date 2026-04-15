"""
Unit tests for EDI parsers.

Tests:
  - Delimiter detection from ISA segment
  - TX type detection (837P, 835, 270)
  - 837P: claims count, service lines, diagnoses
  - 835: claim payments, adjustments, header
  - parse_service.ParseResult structure
  - Error handling for malformed input
"""
from __future__ import annotations

import io
import pytest


# ── Delimiter detection ────────────────────────────────────────────────────────

class TestDelimiterDetection:
    def test_standard_delimiters(self, sample_837p_io):
        from core.parser.envelope import detect_delimiters
        delims = detect_delimiters(sample_837p_io)
        assert delims["element_sep"]   == "*"
        assert delims["segment_term"]  == "~"
        assert delims["component_sep"] == ":"

    def test_returns_none_for_garbage(self):
        from core.parser.envelope import detect_delimiters
        result = detect_delimiters(io.BytesIO(b"NOT AN EDI FILE"))
        # Should not raise; may return None or defaults
        assert result is None or isinstance(result, dict)


# ── TX type detection ─────────────────────────────────────────────────────────

class TestTxTypeDetection:
    def test_detects_837p(self, sample_837p_bytes):
        from core.parser.base_parser import detect_tx_type
        tx = detect_tx_type(io.BytesIO(sample_837p_bytes))
        assert tx == "837P"

    def test_detects_835(self, sample_835_bytes):
        from core.parser.base_parser import detect_tx_type
        tx = detect_tx_type(io.BytesIO(sample_835_bytes))
        assert tx == "835"

    def test_detects_270(self, sample_270_bytes):
        from core.parser.base_parser import detect_tx_type
        tx = detect_tx_type(io.BytesIO(sample_270_bytes))
        assert tx == "270"

    def test_unknown_on_empty(self):
        from core.parser.base_parser import detect_tx_type
        result = detect_tx_type(io.BytesIO(b""))
        assert result in ("UNKNOWN", None, "")


# ── 837P Parser ───────────────────────────────────────────────────────────────

class TestParser837P:
    def test_parse_returns_claims(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        assert result["tx_type"] == "837P"
        claims = result["data"].get("claims", [])
        assert len(claims) == 1

    def test_claim_has_id(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        assert getattr(claim, "claim_id", None) == "CLAIM001"

    def test_claim_billed_amount(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        billed = float(getattr(claim, "total_billed", 0))
        assert billed == pytest.approx(150.00)

    def test_service_lines(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        lines = getattr(claim, "service_lines", [])
        assert len(lines) == 2

    def test_service_line_cpt(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        cpts = [getattr(sl, "cpt_hcpcs", "") for sl in claim.service_lines]
        assert "99213" in cpts
        assert "85025" in cpts

    def test_diagnosis_present(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        diagnoses = getattr(claim, "diagnoses", [])
        assert len(diagnoses) >= 1
        codes = [getattr(d, "code", "") for d in diagnoses]
        assert "Z23.0" in codes

    def test_provider_npi(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        claim = result["data"]["claims"][0]
        bp = getattr(claim, "billing_provider", None)
        if bp:
            assert getattr(bp, "npi", "") == "1234567890"

    def test_envelope_present(self, sample_837p_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_837p_io)
        envelope = result.get("envelope")
        assert envelope is not None


# ── 835 Parser ────────────────────────────────────────────────────────────────

class TestParser835:
    def test_parse_returns_payments(self, sample_835_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_835_io)
        assert result["tx_type"] == "835"
        payments = result["data"].get("claim_payments", [])
        assert len(payments) == 1

    def test_payment_amounts(self, sample_835_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_835_io)
        payment = result["data"]["claim_payments"][0]
        assert float(getattr(payment, "billed", 0)) == pytest.approx(150.00)
        assert float(getattr(payment, "paid", 0)) == pytest.approx(120.00)

    def test_adjustments_present(self, sample_835_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_835_io)
        payment = result["data"]["claim_payments"][0]
        # Adjustments can be at claim or service level
        claim_adj = getattr(payment, "adjustments", []) or []
        svc_adj = [
            adj
            for svc in (getattr(payment, "services", []) or [])
            for adj in (getattr(svc, "adjustments", []) or [])
        ]
        total_adj = len(claim_adj) + len(svc_adj)
        assert total_adj >= 1

    def test_header_payment_total(self, sample_835_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_835_io)
        header = result["data"].get("header")
        if header:
            assert float(getattr(header, "total_payment", 0)) == pytest.approx(250.00)

    def test_clp_id(self, sample_835_io):
        from core.parser.base_parser import parse_edi_file
        result = parse_edi_file(sample_835_io)
        payment = result["data"]["claim_payments"][0]
        assert getattr(payment, "clp_id", "") == "CLAIM001"


# ── Parse Service ─────────────────────────────────────────────────────────────

class TestParseService:
    def test_parse_service_success(self, sample_837p_bytes):
        from app.services.parse_service import parse_edi, ParseResult
        result = parse_edi(sample_837p_bytes, "test.edi")
        assert isinstance(result, ParseResult)
        assert result.success is True
        assert result.tx_type == "837P"
        assert result.record_count == 1
        assert result.duration_ms > 0

    def test_parse_service_835(self, sample_835_bytes):
        from app.services.parse_service import parse_edi
        result = parse_edi(sample_835_bytes, "era.835")
        assert result.success is True
        assert result.tx_type == "835"
        assert result.record_count == 1

    def test_parse_service_bad_input(self):
        from app.services.parse_service import parse_edi
        result = parse_edi(b"GARBAGE DATA", "bad.edi")
        assert result.success is False
        assert result.error is not None

    def test_parse_service_empty(self):
        from app.services.parse_service import parse_edi
        result = parse_edi(b"", "empty.edi")
        assert result.success is False

    def test_parse_result_summary(self, sample_837p_bytes):
        from app.services.parse_service import parse_edi
        result = parse_edi(sample_837p_bytes, "test.edi")
        summary = result.summary
        assert "837P" in summary
        assert "1" in summary


# ── Normalizer ────────────────────────────────────────────────────────────────

class TestNormalizer:
    def test_parse_date_yyyymmdd(self):
        from core.parser.normalizer import parse_date
        d = parse_date("20260101")
        assert d is not None
        assert d.year == 2026
        assert d.month == 1
        assert d.day == 1

    def test_parse_date_iso(self):
        from core.parser.normalizer import parse_date
        d = parse_date("2026-01-01")
        assert d is not None
        assert d.year == 2026

    def test_parse_amount(self):
        from core.parser.normalizer import parse_amount
        assert parse_amount("150.00") == pytest.approx(150.0)
        assert parse_amount("0") == pytest.approx(0.0)
        assert parse_amount("") is None or parse_amount("") == 0.0

    def test_safe_get(self):
        from core.parser.normalizer import safe_get
        elements = ["ISA", "00", "sender"]
        assert safe_get(elements, 0) == "ISA"
        assert safe_get(elements, 5) == ""
        assert safe_get(elements, 5, "DEFAULT") == "DEFAULT"
