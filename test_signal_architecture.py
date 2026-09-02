from __future__ import annotations

import copy
import unittest
from unittest.mock import Mock, patch

from olin.api.cases import build_application
from olin.api.synthetic import SYNTHETIC_CASES
from olin.models import Application, BusinessType, ExternalSignalEvidence
from olin.signal_architecture import (
    BY_ID,
    SIGNAL_DEFINITIONS,
    evaluate_signal_architecture,
    signal_catalog,
)
from olin.weather import analyze_weather


class SignalArchitectureTests(unittest.TestCase):
    FULL_METRICS = {
        "fmcg_purchase_volume": {"avg_weekly_purchase_mxn": 9000, "months_of_history": 18, "trend_3m": .08},
        "fmcg_cadence": {"weekly_purchase_rate": .94, "missed_weeks_last_12": 1},
        "fmcg_supplier_diversity": {"supplier_count": 3, "top_supplier_share": .48},
        "bank_cash_flow_snapshot": {"months_connected": 12, "deposit_regularity": .9, "overdrafts_90d": 0, "monthly_deposit_volume_mxn": 120000},
        "bank_flow_90d_trend": {"balance_trend_90d": .1, "min_daily_balance_mxn": 10000},
        "pos_transaction_volume": {"months_of_history": 12, "volume_consistency": .88, "trend_3m": .05, "avg_monthly_volume_mxn": 70000},
        "zone_commerce_density": {"establishment_count": 120, "radius_m": 500, "same_activity_count": 8},
        "foot_traffic_delta": {"foot_traffic_change_90d": .06},
        "neighborhood_permanence": {"active_business_change_12m": .03, "closure_rate_12m": .05, "employment_change_12m": .02},
        "night_time_light_trend": {"radiance_change_12m": .04},
        "neighborhood_closure_rate": {"closure_rate_12m": .05, "comparison_count": 40},
        "business_age_category_risk": {"years_in_operation": 6, "category_benchmark_years": 5},
        "google_maps_activity": {"rating": 4.5, "review_count": 80, "recent_review_sample_count": 4},
        "hours_consistency": {"scheduled_hours_weekly": 60, "observed_open_ratio": .92},
        "whatsapp_business_verification": {"business_account_present": True, "phone_matches_application": True},
        "commercial_neighbor_ecosystem": {"active_neighbor_count": 55, "complementary_business_count": 12, "closure_rate_12m": .05},
        "psychometric_conscientiousness": {"questionnaire_score": .8, "answered_count": 5},
        "psychometric_integrity": {"scenario_score": .75, "answered_count": 3},
        "whatsapp_response_time": {"median_response_minutes": 40, "response_count": 6},
        "onboarding_message_timing": {"within_declared_hours_ratio": .85, "message_count": 8},
        "onboarding_consistency": {"contradiction_count": 1, "fields_compared": 12},
        "codi_dimo_frequency": {"monthly_transaction_count": 18, "regularity": .85},
        "oxxo_pay_deposit_frequency": {"monthly_deposit_count": 12, "regularity": .8},
        "spei_inbound_regularity": {"monthly_inbound_count": 20, "regularity": .9},
        "weather_risk": {"extreme_weather_days_30d": 2, "temperature_anomaly_c": 1.2, "precipitation_anomaly_pct": 10},
        "fmcg_inflation_proxy": {"relevant_inflation_yoy": 6, "estimated_margin_pct": 18},
        "imss_payroll_trajectory": {"employee_count": 6, "employee_change_12m": .15},
        "seasonal_adjustment": {"observed_to_expected_revenue_ratio": .95, "history_months": 18},
    }

    def test_catalog_contains_exactly_28_unique_signals(self):
        self.assertEqual(len(SIGNAL_DEFINITIONS), 28)
        self.assertEqual(len(BY_ID), 28)
        catalog = signal_catalog()
        self.assertEqual(catalog["signal_count"], 28)
        self.assertIn("pos_transaction_volume", BY_ID)
        self.assertIsNone(BY_ID["pos_transaction_volume"].pdf_weight)

    def test_every_supported_sme_type_receives_a_complete_report(self):
        for business_type in BusinessType:
            with self.subTest(business_type=business_type.value):
                app = Application("SME fixture", business_type, 25_000)
                report = evaluate_signal_architecture(app)
                self.assertEqual(report["signal_count"], 28)
                self.assertEqual(len(report["signals"]), 28)
                self.assertEqual(len(report["layers"]), 6)
                self.assertFalse(report["predictive_model"])

    def test_all_28_evaluators_execute_with_complete_verified_evidence(self):
        evidence = {
            signal_id: ExternalSignalEvidence(
                metrics=metrics,
                source="bank_test_fixture",
                verified=True,
                evidence_reference=f"FIXTURE-{signal_id}",
                observed_at="2026-08-20T12:00:00+00:00",
            )
            for signal_id, metrics in self.FULL_METRICS.items()
        }
        app = Application("Universal SME", BusinessType.ABARROTES, 30_000, signal_evidence=evidence)
        report = evaluate_signal_architecture(app)
        self.assertEqual(report["observed_count"], 28)
        self.assertEqual(report["verified_count"], 28)
        self.assertEqual(report["coverage"], 1.0)
        self.assertTrue(all(item["indicator_score"] is not None for item in report["signals"]))

    def test_existing_case_evidence_populates_signals_without_changing_scope(self):
        app = build_application(copy.deepcopy(SYNTHETIC_CASES[0]))
        report = evaluate_signal_architecture(app)
        rows = {item["signal_id"]: item for item in report["signals"]}
        self.assertEqual(rows["bank_cash_flow_snapshot"]["status"], "observed")
        self.assertEqual(rows["fmcg_cadence"]["status"], "observed")
        self.assertEqual(rows["pos_transaction_volume"]["status"], "observed")
        self.assertEqual(rows["bank_cash_flow_snapshot"]["decision_use"], "context_only_not_default_probability")

    def test_verified_provider_evidence_has_provenance_and_high_confidence(self):
        app = Application(
            "Professional SME",
            BusinessType.PROFESSIONAL,
            40_000,
            signal_evidence={
                "spei_inbound_regularity": ExternalSignalEvidence(
                    metrics={"monthly_inbound_count": 18, "regularity": .91},
                    source="partner_bank",
                    verified=True,
                    evidence_reference="BANK-SPEI-001",
                    observed_at="2026-08-20T12:00:00+00:00",
                )
            },
        )
        report = evaluate_signal_architecture(app)
        row = next(item for item in report["signals"] if item["signal_id"] == "spei_inbound_regularity")
        self.assertEqual(row["status"], "observed")
        self.assertEqual(row["confidence"], "high")
        self.assertEqual(row["evidence_reference"], "BANK-SPEI-001")

    def test_api_rejects_unknown_or_unreferenced_verified_signal(self):
        payload = copy.deepcopy(SYNTHETIC_CASES[0])
        payload["signal_evidence"] = {"invented_signal": {"metrics": {"x": 1}}}
        with self.assertRaisesRegex(ValueError, "Unknown signal_evidence"):
            build_application(payload)

        payload = copy.deepcopy(SYNTHETIC_CASES[0])
        payload["signal_evidence"] = {
            "weather_risk": {
                "metrics": {"extreme_weather_days_30d": 2},
                "source": "open_meteo",
                "verified": True,
            }
        }
        with self.assertRaisesRegex(ValueError, "requires evidence_reference"):
            build_application(payload)

        payload["signal_evidence"]["weather_risk"]["evidence_reference"] = "WEATHER-1"
        payload["signal_evidence"]["weather_risk"]["observed_at"] = "last Tuesday"
        with self.assertRaisesRegex(ValueError, "must be ISO 8601"):
            build_application(payload)

        payload = copy.deepcopy(SYNTHETIC_CASES[0])
        payload["signal_evidence"] = {
            "weather_risk": {
                "metrics": {"secret_customer_field": "must-not-be-stored"},
                "source": "partner_bank",
            }
        }
        with self.assertRaisesRegex(ValueError, "is not an allowed metric"):
            build_application(payload)

    @patch("olin.weather.requests.get")
    def test_weather_adapter_returns_ready_to_attach_signal_evidence(self, mocked_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "daily": {
                "temperature_2m_max": [30.0] * 30,
                "temperature_2m_min": [18.0] * 30,
                "precipitation_sum": [2.0] * 30,
            }
        }
        mocked_get.return_value = response
        result = analyze_weather(19.4326, -99.1332, "2026-08-14")
        evidence = result["signal_evidence"]["weather_risk"]
        self.assertTrue(evidence["verified"])
        self.assertTrue(evidence["evidence_reference"].startswith("open-meteo:"))
        self.assertEqual(evidence["metrics"]["extreme_weather_days_30d"], 0)
        self.assertEqual(mocked_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
