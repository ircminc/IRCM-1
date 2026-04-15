"""
Unit tests for analytics modules.

Tests:
  - KPI engine: NCR, FPRR, denial rate, DAR, aging buckets
  - Underpayment detection
  - Provider performance metrics
  - Denial predictor rules
  - PHI masker
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest


# ── KPI Engine ────────────────────────────────────────────────────────────────

class TestKPIEngine:
    """Tests for analytics/kpi_engine.py"""

    @pytest.fixture
    def sample_claims_df(self):
        today = date.today()
        return pd.DataFrame([
            {"id": 1, "claim_id": "CLM001", "total_billed": 500.0,
             "dos_from": str(today - timedelta(days=10))},
            {"id": 2, "claim_id": "CLM002", "total_billed": 300.0,
             "dos_from": str(today - timedelta(days=45))},
            {"id": 3, "claim_id": "CLM003", "total_billed": 200.0,
             "dos_from": str(today - timedelta(days=75))},
            {"id": 4, "claim_id": "CLM004", "total_billed": 400.0,
             "dos_from": str(today - timedelta(days=100))},
        ])

    @pytest.fixture
    def sample_payments_df(self):
        return pd.DataFrame([
            {"id": 1, "clp_id": "CLM001", "billed": 500.0, "paid": 400.0,
             "patient_responsibility": 50.0, "status_code": "1",
             "payer_name": "MEDICARE", "payment_date": "2026-01-15"},
            {"id": 2, "clp_id": "CLM002", "billed": 300.0, "paid": 240.0,
             "patient_responsibility": 30.0, "status_code": "4",
             "payer_name": "MEDICAID", "payment_date": "2026-01-20"},
        ])

    @pytest.fixture
    def sample_adj_df(self):
        return pd.DataFrame([
            {"id": 1, "payment_id": 1, "group_code": "CO", "reason_code": "45",
             "amount": 100.0, "level": "claim", "cpt_hcpcs": "99213"},
            {"id": 2, "payment_id": 2, "group_code": "CO", "reason_code": "50",
             "amount": 60.0,  "level": "claim", "cpt_hcpcs": "85025"},
        ])

    def test_compute_kpis_returns_result(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis, KPIResult
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        assert isinstance(result, KPIResult)

    def test_total_billed(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        assert result.total_billed == pytest.approx(1400.0)

    def test_total_claims_count(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        assert result.total_claims == 4

    def test_denial_rate_computed(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        # 1 denied out of 2 payments = 50%
        assert result.denial_rate == pytest.approx(50.0)

    def test_net_collection_rate_reasonable(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        # Paid = 640, Billed = 800, Contractual = 160 → Collectible = 640 → NCR = 100%
        if result.net_collection_rate is not None:
            assert 0 < result.net_collection_rate <= 100

    def test_aging_buckets_populated(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        aging = result.aging
        assert "0–30 days" in aging
        assert "90+ days" in aging
        # Our fixture has claims at 10, 45, 75, 100 days
        assert aging["0–30 days"]["count"] == 1
        assert aging["31–60 days"]["count"] == 1
        assert aging["61–90 days"]["count"] == 1
        assert aging["90+ days"]["count"] == 1

    def test_days_in_ar_positive(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        if result.days_in_ar is not None:
            assert result.days_in_ar > 0

    def test_grade_function(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        grade = result.grade("denial_rate")
        assert grade in ("🟢 Good", "🟡 Review", "🔴 High", "⚪ N/A")

    def test_empty_dataframes(self):
        from analytics.kpi_engine import compute_kpis
        result = compute_kpis(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert result.total_claims == 0
        assert result.total_billed == 0.0

    def test_aging_dataframe_shape(self, sample_claims_df, sample_payments_df, sample_adj_df):
        from analytics.kpi_engine import compute_kpis, aging_dataframe
        result = compute_kpis(sample_claims_df, sample_payments_df, sample_adj_df)
        df = aging_dataframe(result)
        assert len(df) == 4
        assert "bucket" in df.columns
        assert "count" in df.columns


# ── Underpayment Detection ────────────────────────────────────────────────────

class TestUnderpayment:
    @pytest.fixture
    def payments_with_low_paid(self):
        return pd.DataFrame([
            {"id": 1, "clp_id": "CLM001", "billed": 100.0, "paid": 10.0,
             "status_code": "1", "payer_name": "CHEAP PAYER"},
            {"id": 2, "clp_id": "CLM002", "billed": 100.0, "paid": 90.0,
             "status_code": "1", "payer_name": "FAIR PAYER"},
        ])

    def test_detect_returns_dataframe(self, payments_with_low_paid):
        from analytics.underpayment import detect_underpayments
        # Without CMS rates (no enrichment), should return empty (no expected_rate)
        result = detect_underpayments(payments_with_low_paid)
        assert isinstance(result, pd.DataFrame)

    def test_underpayment_summary_empty(self):
        from analytics.underpayment import underpayment_summary
        summary = underpayment_summary(pd.DataFrame())
        assert summary["total_underpaid_claims"] == 0
        assert summary["total_variance"] == 0.0

    def test_underpayment_by_payer_empty(self):
        from analytics.underpayment import underpayment_by_payer
        result = underpayment_by_payer(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ── Provider Performance ──────────────────────────────────────────────────────

class TestProviderPerformance:
    @pytest.fixture
    def claims_with_npi(self):
        return pd.DataFrame([
            {"id": 1, "claim_id": "CLM001", "billing_provider_npi": "1111111111",
             "billing_provider_name": "DR SMITH", "total_billed": 500.0},
            {"id": 2, "claim_id": "CLM002", "billing_provider_npi": "1111111111",
             "billing_provider_name": "DR SMITH", "total_billed": 300.0},
            {"id": 3, "claim_id": "CLM003", "billing_provider_npi": "2222222222",
             "billing_provider_name": "DR JONES", "total_billed": 400.0},
        ])

    def test_revenue_metrics_by_npi(self, claims_with_npi):
        from analytics.provider_perf import provider_revenue_metrics
        result = provider_revenue_metrics(claims_with_npi, pd.DataFrame())
        assert len(result) == 2  # 2 unique NPIs

    def test_revenue_totals_correct(self, claims_with_npi):
        from analytics.provider_perf import provider_revenue_metrics
        result = provider_revenue_metrics(claims_with_npi, pd.DataFrame())
        dr_smith = result[result["provider_npi"] == "1111111111"]
        assert not dr_smith.empty
        assert float(dr_smith["total_billed"].iloc[0]) == pytest.approx(800.0)

    def test_claim_count_correct(self, claims_with_npi):
        from analytics.provider_perf import provider_revenue_metrics
        result = provider_revenue_metrics(claims_with_npi, pd.DataFrame())
        dr_smith = result[result["provider_npi"] == "1111111111"]
        assert int(dr_smith["claim_count"].iloc[0]) == 2

    def test_empty_claims_returns_empty(self):
        from analytics.provider_perf import provider_revenue_metrics
        result = provider_revenue_metrics(pd.DataFrame(), pd.DataFrame())
        assert result.empty


# ── Denial Predictor ──────────────────────────────────────────────────────────

class TestDenialPredictor:
    @pytest.fixture
    def clean_service_line(self):
        return {
            "cpt_hcpcs": "99213",
            "modifier_1": "",
            "billed_amount": 75.0,
            "units": 1,
            "diagnosis_pointers": "A",
            "ndc": "",
            "place_of_service": "11",
        }

    @pytest.fixture
    def j_code_no_ndc(self):
        return {
            "cpt_hcpcs": "J0171",
            "modifier_1": "",
            "billed_amount": 50.0,
            "units": 1,
            "diagnosis_pointers": "A",
            "ndc": "",   # Missing NDC — should trigger rule
            "place_of_service": "11",
        }

    @pytest.fixture
    def unlisted_procedure(self):
        return {
            "cpt_hcpcs": "99199",
            "modifier_1": "",
            "billed_amount": 200.0,
            "units": 1,
            "diagnosis_pointers": "A",
            "ndc": "",
            "place_of_service": "11",
        }

    def test_clean_claim_low_risk(self, clean_service_line):
        from analytics.denial_predictor import DenialPredictor
        predictor = DenialPredictor()
        pred = predictor._score_service_line(clean_service_line)
        assert pred.risk_level == "LOW"
        assert pred.risk_score < 0.30

    def test_j_code_triggers_ndc_rule(self, j_code_no_ndc):
        from analytics.denial_predictor import DenialPredictor
        predictor = DenialPredictor()
        pred = predictor._score_service_line(j_code_no_ndc)
        assert pred.risk_score >= 0.60
        assert pred.risk_level == "HIGH"
        assert any("NDC" in f or "J-code" in f for f in pred.risk_factors)

    def test_unlisted_procedure_triggers(self, unlisted_procedure):
        from analytics.denial_predictor import DenialPredictor
        predictor = DenialPredictor()
        pred = predictor._score_service_line(unlisted_procedure)
        assert pred.risk_score >= 0.30
        assert any("unlisted" in f.lower() for f in pred.risk_factors)

    def test_missing_diagnosis_pointer(self):
        from analytics.denial_predictor import DenialPredictor
        svc = {
            "cpt_hcpcs": "99213",
            "modifier_1": "",
            "billed_amount": 75.0,
            "units": 1,
            "diagnosis_pointers": "",   # Missing
            "ndc": "",
            "place_of_service": "11",
        }
        predictor = DenialPredictor()
        pred = predictor._score_service_line(svc)
        assert pred.risk_score >= 0.30
        assert any("pointer" in f.lower() or "SV107" in f for f in pred.risk_factors)

    def test_predict_claim_returns_per_line(self):
        from analytics.denial_predictor import DenialPredictor
        predictor = DenialPredictor()
        claim = {
            "claim_id": "TEST001",
            "place_of_service": "11",
            "service_lines": [
                {"cpt_hcpcs": "99213", "modifier_1": "", "billed_amount": 75.0,
                 "units": 1, "diagnosis_pointers": "A", "ndc": ""},
                {"cpt_hcpcs": "J0171", "modifier_1": "", "billed_amount": 50.0,
                 "units": 1, "diagnosis_pointers": "A", "ndc": ""},
            ],
        }
        preds = predictor.predict_claim(claim)
        assert len(preds) == 2

    def test_prediction_summary(self):
        from analytics.denial_predictor import DenialPredictor, prediction_summary
        predictor = DenialPredictor()
        claim = {
            "claim_id": "TEST001",
            "place_of_service": "11",
            "service_lines": [
                {"cpt_hcpcs": "J0171", "modifier_1": "", "billed_amount": 50.0,
                 "units": 1, "diagnosis_pointers": "A", "ndc": ""},
            ],
        }
        preds = predictor.predict_claim(claim)
        summary = prediction_summary(preds)
        assert summary["total"] == 1
        assert summary["high"] + summary["medium"] + summary["low"] == 1


# ── PHI Masker ────────────────────────────────────────────────────────────────

class TestPHIMasker:
    def test_mask_name(self):
        from app.security.phi_masker import mask_name
        result = mask_name("John Smith")
        assert result == "J*** S***"

    def test_mask_name_single_word(self):
        from app.security.phi_masker import mask_name
        result = mask_name("Madonna")
        assert result == "M***"

    def test_mask_dob_iso(self):
        from app.security.phi_masker import mask_dob
        result = mask_dob("1985-07-22")
        assert result == "1985-**-**"

    def test_mask_dob_yyyymmdd(self):
        from app.security.phi_masker import mask_dob
        result = mask_dob("19850722")
        assert result == "1985****"

    def test_mask_id_keeps_last_4(self):
        from app.security.phi_masker import mask_id
        result = mask_id("ABC123456789")
        assert result.endswith("6789")
        assert "*" in result

    def test_mask_npi(self):
        from app.security.phi_masker import mask_npi
        result = mask_npi("1234567890")
        assert result.endswith("7890")
        assert result.startswith("NPI-")

    def test_mask_dataframe(self):
        from app.security.phi_masker import mask_dataframe
        df = pd.DataFrame([{
            "patient_last":  "Smith",
            "patient_first": "John",
            "claim_id":      "CLM001",
            "total_billed":  150.0,
        }])
        phi_cols = {"patient_last": "name_part", "patient_first": "name_part"}
        masked = mask_dataframe(df, phi_cols)

        # Non-PHI column unchanged
        assert float(masked["total_billed"].iloc[0]) == 150.0
        # PHI columns masked
        assert masked["patient_last"].iloc[0] != "Smith"
        assert masked["patient_last"].iloc[0].startswith("S")
        assert "*" in masked["patient_last"].iloc[0]

    def test_mask_empty_value(self):
        from app.security.phi_masker import mask_name
        assert mask_name("") == "" or mask_name("") is None or mask_name(None) is None
