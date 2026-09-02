from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.cases import build_application, create_case
from olin.capacity_v2 import calculate_capacity
from olin.store import ScoringLog


def pharmacy_payload() -> dict:
    return {
        "merchant_name": "Farmacia Salud Centro",
        "business_type": "pharmacy",
        "requested_mxn": 50_000,
        "funding_purpose": "inventory",
        "evidence_route": "bank_flow_led",
        "pharmacy": {
            "subtype": "community_pharmacy",
            "scian_code": "464111",
            "sells_controlled_medicines": True,
            "license_status": "active",
            "license_reference": "BANK-LIC-009",
            "supplier_count": 4,
            "top_supplier_share": .44,
            "inventory_days": 38,
            "expiry_writeoff_ratio": .018,
            "gross_margin_pct": .27,
            "stockout_rate": .05,
            "source": "bank_pharmacy_review",
            "evidence_reference": "PHARM-009",
            "observed_at": "2026-08-20T12:00:00+00:00",
        },
        "facility": {
            "term_months": 12,
            "monthly_rate": .03,
            "existing_monthly_debt_service_mxn": 3_000,
            "policy_max_amount_mxn": 45_000,
            "target_dscr": 1.25,
            "revenue_stress_pct": .15,
            "cost_stress_pct": .10,
        },
        "operating_profile": {
            "metrics": {
                "inventory_days": 38, "gross_margin": 0.27,
                "expiry_writeoffs": 0.018, "stockout_rate": 0.05
            },
            "source": "bank_operating_review",
            "evidence_reference": "OPERATING-PHARM-009",
            "observed_at": "2026-08-20T12:00:00+00:00"
        },
        "bank_features_v2": {
            "contract_version": "bank-feature-contract-2.0",
            "calculation_version": "bank-cashflow-2.0",
            "currency": "MXN",
            "period_start": "2026-02-01",
            "period_end": "2026-07-31",
            "account_count": 2,
            "account_coverage_ratio": .98,
            "account_holder_match": True,
            "classification_coverage_ratio": .96,
            "operating_inflows_mxn": 190_000,
            "operating_outflows_mxn": 125_000,
            "internal_transfer_inflows_mxn": 25_000,
            "debt_proceeds_mxn": 15_000,
            "refunds_mxn": 2_000,
            "existing_monthly_debt_service_mxn": 3_000,
            "end_of_day_avg_balance_mxn": 24_000,
            "end_of_day_min_balance_mxn": 4_200,
            "inflow_volatility": .21,
            "top_payer_share": .08,
            "source": "bank_cashflow_service",
            "evidence_reference": "BFC2-009",
            "observed_at": "2026-08-01T12:00:00+00:00",
        },
        "bank": {
            "months_connected": 6,
            "monthly_deposit_volume_mxn": 190_000,
            "monthly_outflow_volume_mxn": 125_000,
            "source": "bank_cashflow_service",
            "verified": True,
            "evidence_reference": "BFC2-009",
            "observed_at": "2026-08-01T12:00:00+00:00",
        },
    }


REGISTRY = json.dumps({
    "bank_cashflow_service": {
        "status": "active", "evidence_types": ["bank_feature_contract_v2"],
        "valid_until": "2030-01-01", "attestation_id": "ATT-BANK-1"
    },
    "bank_pharmacy_review": {
        "status": "active", "evidence_types": ["pharmacy_evidence"],
        "valid_until": "2030-01-01", "attestation_id": "ATT-PHARM-1"
    },
    "bank_core": {
        "status": "active", "evidence_types": ["repayment_outcome"],
        "valid_until": "2030-01-01", "attestation_id": "ATT-OUTCOME-1"
    },
    "bank_operating_review": {
        "status": "active", "evidence_types": ["operating_profile"],
        "valid_until": "2030-01-01", "attestation_id": "ATT-OPERATING-1"
    },
})


class PharmacyVerticalAcceptanceTests(unittest.TestCase):
    def test_payload_cannot_self_assert_independent_verification(self):
        payload = pharmacy_payload()
        payload["signal_evidence"] = {
            "spei_inbound_regularity": {
                "metrics": {"monthly_inbound_count": 20, "regularity": .9},
                "source": "unregistered_partner_upload", "verified": True,
                "evidence_reference": "SELF-1",
                "observed_at": "2026-08-20T12:00:00+00:00",
            }
        }
        with patch.dict(os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": "{}"}):
            app = build_application(payload)
        self.assertFalse(app.signal_evidence["spei_inbound_regularity"].verified)

    def test_capacity_uses_stress_and_separates_amounts(self):
        with patch.dict(os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": REGISTRY}):
            app = build_application(pharmacy_payload())
            result = calculate_capacity(app)
        self.assertEqual("pharmacy", app.business_type.value)
        self.assertEqual(50_000, result["requested_amount_mxn"])
        self.assertEqual(45_000, result["amount_evaluated_mxn"])
        self.assertTrue(result["source_trust"]["trusted"])
        self.assertLess(result["stressed_monthly_cash_flow_mxn"], result["normalized_monthly_cash_flow_mxn"])
        self.assertGreaterEqual(result["proposed_amount_mxn"], 0)

    def test_loss_is_not_rewritten_as_positive_income(self):
        payload = pharmacy_payload()
        payload["bank_features_v2"]["operating_outflows_mxn"] = 205_000
        with patch.dict(os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": REGISTRY}):
            result = calculate_capacity(build_application(payload))
        self.assertLess(result["normalized_monthly_cash_flow_mxn"], 0)
        self.assertEqual(0, result["proposed_amount_mxn"])

    def test_full_shadow_response_is_committee_only_and_explainable(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test", "OLIN_TRUSTED_SOURCE_REGISTRY": REGISTRY}):
                response = create_case(pharmacy_payload(), tmp.name, "bank_partner")
        self.assertEqual("COMMITTEE", response["recommendation"])
        self.assertIsNone(response["statistical_confidence_interval"])
        self.assertFalse(response["heuristic_sensitivity_range"]["statistical"])
        self.assertEqual(50_000, response["requested_amount_mxn"])
        self.assertEqual(45_000, response["amount_evaluated_mxn"])
        self.assertEqual("classified", response["enrichment_report"]["pharmacy"]["status"])

    def test_performance_events_are_derived_and_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test", "OLIN_TRUSTED_SOURCE_REGISTRY": REGISTRY}):
                case = create_case(pharmacy_payload(), tmp.name, "bank_partner")
                event = {
                    "event_id": "OUT-001", "observed_at": "2026-10-01T00:00:00+00:00",
                    "period_end": "2026-09-30T00:00:00+00:00", "days_past_due": 35,
                    "outstanding_balance_mxn": 31000, "scheduled_payment_mxn": 5100,
                    "amount_paid_mxn": 0, "source": "bank_core",
                    "evidence_reference": "LOAN-99-M2",
                }
                with ScoringLog(tmp.name) as log:
                    bank_decision = log.record_partner_outcome(
                        case["application_id"], "approved",
                        "Bank committee accepted the reduced stressed amount",
                        "2026-08-25T00:00:00+00:00", "bank_partner",
                    )
                    first = log.record_shadow_performance(case["application_id"], event, "bank_partner")
                    second = log.record_shadow_performance(case["application_id"], event, "bank_partner")
                    stored = log.list_shadow_performance(case["application_id"])
        self.assertEqual("dpd_30_59", first["status"])
        self.assertEqual("approved", bank_decision["partner_decision"])
        self.assertEqual(first, second)
        self.assertTrue(first["source_trust"]["trusted"])
        self.assertEqual(1, len(stored))


if __name__ == "__main__":
    unittest.main()
