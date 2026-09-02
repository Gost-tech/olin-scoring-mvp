from __future__ import annotations

import unittest

from olin.evidence_governance import (
    CAPACITY_EVIDENCE,
    CONTEXT_ONLY,
    RESEARCH_ONLY,
    evidence_governance,
    governance_summary,
)
from olin.models import Application, BusinessType, ExternalSignalEvidence
from olin.signal_architecture import evaluate_signal_architecture


class EvidenceGovernanceTests(unittest.TestCase):
    def test_verified_financial_evidence_can_enter_shadow_capacity_review(self):
        result = evidence_governance(
            "bank_cash_flow_snapshot",
            verified=True,
            evidence_reference="bank:case-1:features-v2",
        )
        self.assertEqual(result["evidenceClass"], CAPACITY_EVIDENCE)
        self.assertTrue(result["eligibleForShadowPolicy"])
        self.assertFalse(result["mayAutoDecide"])

    def test_context_and_research_signals_never_enter_credit_policy(self):
        weather = evidence_governance(
            "weather_risk", verified=True, evidence_reference="open-meteo:1"
        )
        behavior = evidence_governance(
            "whatsapp_response_time", verified=True, evidence_reference="wa:1"
        )
        self.assertEqual(weather["evidenceClass"], CONTEXT_ONLY)
        self.assertEqual(behavior["evidenceClass"], RESEARCH_ONLY)
        self.assertFalse(weather["eligibleForShadowPolicy"])
        self.assertFalse(behavior["eligibleForShadowPolicy"])

    def test_unverified_financial_observation_is_not_policy_eligible(self):
        result = evidence_governance(
            "pos_transaction_volume", verified=False, evidence_reference="upload:1"
        )
        self.assertEqual(result["evidenceClass"], CAPACITY_EVIDENCE)
        self.assertFalse(result["eligibleForShadowPolicy"])
        self.assertIn(
            "verified_provider_or_bank_evidence_required",
            result["blockingReasons"],
        )

    def test_signal_report_exposes_governance_for_every_signal(self):
        app = Application(
            "Abarrotes fixture",
            BusinessType.ABARROTES,
            25_000,
            signal_evidence={
                "bank_cash_flow_snapshot": ExternalSignalEvidence(
                    metrics={
                        "months_connected": 12,
                        "deposit_regularity": .92,
                        "overdrafts_90d": 0,
                        "monthly_deposit_volume_mxn": 120_000,
                    },
                    source="partner_bank",
                    verified=True,
                    evidence_reference="bank:case-1",
                    observed_at="2026-09-01T12:00:00+00:00",
                )
            },
        )
        report = evaluate_signal_architecture(app)
        rows = {row["signal_id"]: row for row in report["signals"]}
        self.assertEqual(
            rows["bank_cash_flow_snapshot"]["governance"]["evidenceClass"],
            CAPACITY_EVIDENCE,
        )
        self.assertEqual(
            rows["weather_risk"]["governance"]["evidenceClass"], CONTEXT_ONLY
        )
        self.assertEqual(
            rows["psychometric_integrity"]["governance"]["evidenceClass"],
            RESEARCH_ONLY,
        )
        self.assertEqual(
            report["governance"]["classCounts"], governance_summary()["classCounts"]
        )


if __name__ == "__main__":
    unittest.main()
