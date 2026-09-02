"""Adversarial controls that must hold before any bank-wide pilot."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.cases import create_case
from olin.api.cases import build_application
from olin.production_storage import assert_real_data_storage_ready, production_storage_readiness
from olin.source_trust import trust_registry_readiness
from olin.store import ScoringLog
from olin.models import BusinessType
from scripts.all_business_bank_acceptance import build_synthetic_case_payload, TRUST_REGISTRY


class BankWideControlTests(unittest.TestCase):
    def test_feature_contract_rejects_too_short_observation_window(self):
        payload = build_synthetic_case_payload(BusinessType.RETAIL, 7)
        payload["bank_features_v2"]["period_start"] = "2026-07-01"
        with self.assertRaisesRegex(ValueError, "90 to 400 days"):
            build_application(payload)

    def test_real_data_cannot_fall_through_to_sqlite_even_with_config_strings(self):
        env = {
            "OLIN_REAL_DATA_ENABLED": "1",
            "OLIN_DATABASE_URL": "postgresql://configured-but-not-connected/olin",
            "OLIN_KMS_KEY_ID": "kms-key",
            "OLIN_DATABASE_ENCRYPTION_AT_REST": "attested",
            "OLIN_BACKUP_RESTORE_EVIDENCE": "restore-ticket-1",
        }
        with patch.dict(os.environ, env, clear=True):
            status = production_storage_readiness()
            with self.assertRaisesRegex(RuntimeError, "postgres_runtime_adapter"):
                assert_real_data_storage_ready()
        self.assertFalse(status["ready"])
        self.assertFalse(status["checks"]["postgres_runtime_adapter"])

    def test_no_v2_contract_means_no_proposed_amount(self):
        payload = build_synthetic_case_payload(BusinessType.RETAIL, 1)
        payload.pop("bank_features_v2")
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {
                "OLIN_MODE": "production", "OLIN_REAL_DATA_ENABLED": "0",
                "OLIN_TRUSTED_SOURCE_REGISTRY": TRUST_REGISTRY,
                "OLIN_VALIDATED_AUTO_APPROVE_TYPES": "",
                "OLIN_ALLOW_LEGACY_CONSENT": "1",
            }):
                result = create_case(payload, tmp.name, "bank_test")
        self.assertIsNone(result["proposed_amount_mxn"])
        self.assertEqual("insufficient_data", result["capacity_v2"]["status"])
        self.assertEqual("COMMITTEE", result["recommendation"])

    def test_registry_file_covers_capacity_and_outcomes(self):
        path = os.path.abspath("config/trusted-sources.example.json")
        with patch.dict(os.environ, {
            "OLIN_TRUSTED_SOURCE_REGISTRY": "",
            "OLIN_TRUSTED_SOURCE_REGISTRY_FILE": path,
        }):
            result = trust_registry_readiness()
        self.assertTrue(result["ready"])
        self.assertEqual([], result["missing_evidence_types"])

    def test_idempotent_outcome_replay_uses_original_trust_snapshot(self):
        event = {
            "event_id": "stable-event", "event_type": "scheduled_observation",
            "observed_at": "2026-10-01T00:00:00+00:00",
            "period_end": "2026-09-30T00:00:00+00:00", "days_past_due": 0,
            "outstanding_balance_mxn": 40000, "scheduled_payment_mxn": 4500,
            "amount_paid_mxn": 4500, "source": "bank_core",
            "evidence_reference": "LOAN-1-M1",
        }
        changed = json.loads(TRUST_REGISTRY)
        changed["bank_core"]["attestation_id"] = "ROTATED-ATTESTATION"
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test", "OLIN_TRUSTED_SOURCE_REGISTRY": TRUST_REGISTRY}):
                case = create_case(build_synthetic_case_payload(BusinessType.RETAIL, 2), tmp.name, "bank_test")
                with ScoringLog(tmp.name) as log:
                    first = log.record_shadow_performance(case["application_id"], event, "bank_test")
            with patch.dict(os.environ, {"OLIN_MODE": "test", "OLIN_TRUSTED_SOURCE_REGISTRY": json.dumps(changed)}):
                with ScoringLog(tmp.name) as log:
                    replay = log.record_shadow_performance(case["application_id"], event, "bank_test")
        self.assertEqual(first, replay)
        self.assertEqual("BANK-OUTCOME-ATTESTATION-1", replay["source_trust"]["attestation_id"])


if __name__ == "__main__":
    unittest.main()
