import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from olin.evidence_passport import (
    EvidenceRecord,
    assess_case_evidence_passport,
    assess_evidence_passport,
    evidence_catalog,
    register_verified_evidence,
    revoke_evidence,
)
from olin.scorecard import score_application
from olin.store import ScoringLog
from test_pilot_safety import healthy_app
from test_shadow_mvp import request, running_server


NOW = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)
PERSON_HASH = sha256(b"person-001").hexdigest()
BUSINESS_HASH = sha256(b"business-001").hexdigest()
OTHER_BUSINESS_HASH = sha256(b"business-002").hexdigest()

SOURCE_TYPES = {
    "kyc_provider": [
        "government_identity_verified",
        "individual_business_ownership_verified",
        "beneficial_owner_verified",
        "account_holder_match",
    ],
    "corporate_authority_review": ["legal_representative_authority_verified"],
    "bank_feed": ["verified_bank_feed"],
    "merchant_log_review": ["cash_sales_log_observed"],
    "supplier_feed": ["supplier_confirmed_invoices"],
    "site_visit_team": ["site_visit_verified"],
    "inventory_review": ["inventory_count_verified"],
}


def registry(attestation_suffix="v1"):
    return json.dumps({
        source: {
            "status": "active",
            "evidence_types": types,
            "valid_until": "2099-12-31",
            "attestation_id": f"{source}-{attestation_suffix}",
        }
        for source, types in SOURCE_TYPES.items()
    })


class PassportFixture:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.directory.name) / "passport.db")
        app = healthy_app()
        result = score_application(app)
        self.application_id = result.application_id
        self.owner = "partner_a"
        with ScoringLog(self.db_path) as log:
            log.log(app, result)
            log.conn.execute(
                "UPDATE scoring_log SET owner_actor=?,case_mode='shadow',is_demo=0 "
                "WHERE application_id=?", (self.owner, self.application_id),
            )
            log.conn.commit()
            log.record_consent(
                self.application_id, "in_person",
                "Autorizo esta evaluación controlada.", actor=self.owner,
            )
            self.consent_id = str(log.conn.execute(
                "SELECT consent_id FROM consent_record WHERE application_id=? "
                "AND status='active'", (self.application_id,),
            ).fetchone()[0])

    def close(self):
        self.directory.cleanup()

    def add(
        self, evidence_type, source_id, origin_id, subject_key,
        subject_hash=BUSINESS_HASH, evidence_id=None, source_reference=None,
    ):
        evidence_id = evidence_id or f"ev-{evidence_type}-{origin_id}"
        return register_verified_evidence(
            self.db_path,
            application_id=self.application_id,
            owner_actor=self.owner,
            evidence_type=evidence_type,
            source_id=source_id,
            origin_id=origin_id,
            subject_key=subject_key,
            subject_hash=subject_hash,
            verification_method="signed_test_adapter",
            source_reference=source_reference or f"ref-{evidence_id}",
            consent_id=self.consent_id,
            observed_at=(NOW - timedelta(days=1)).isoformat(),
            expires_at=(NOW + timedelta(days=30)).isoformat(),
            created_by="test_adapter",
            evidence_id=evidence_id,
            now=NOW,
        )


class EvidencePassportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "OLIN_MODE": "demo",
            "OLIN_TRUSTED_SOURCE_REGISTRY": registry(),
        }, clear=True)
        self.env.start()
        self.fx = PassportFixture()

    def tearDown(self):
        self.fx.close()
        self.env.stop()

    def _individual_hard_controls(self):
        identity = self.fx.add(
            "government_identity_verified", "kyc_provider", "kyc-session-1",
            "applicant_person", PERSON_HASH, "ev-identity",
        )
        authority = self.fx.add(
            "individual_business_ownership_verified", "kyc_provider", "kyc-session-1",
            "applicant_business", BUSINESS_HASH, "ev-owner-authority",
        )
        return [identity["evidence_id"], authority["evidence_id"]]

    def test_catalog_separates_identity_authority_consent_and_capacity(self):
        catalog = evidence_catalog()
        self.assertEqual(catalog["engine_version"], "evidence-passport-2.0.0")
        self.assertEqual(
            catalog["non_substitutable"]["authority"]["legal_entity"],
            "legal_representative_authority_verified",
        )
        self.assertIn("account_holder_match", catalog["supporting_evidence"]["authority_context_not_authority"])

    def test_self_asserted_labels_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "server-registered"):
            assess_evidence_passport(
                "retail", ["government_identity_verified"],
                legal_form="individual_business_owner", consent_active=True,
            )

    def test_verified_case_bound_records_enable_human_review_not_approval(self):
        ids = self._individual_hard_controls()
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-account-1",
            "applicant_business", evidence_id="ev-bank",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids + [bank["evidence_id"]],
            legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertEqual(result["status"], "READY_FOR_HUMAN_PARTNER_REVIEW")
        self.assertIn("bank_flow_led", result["ready_routes"])
        self.assertTrue(result["requires_human_credit_decision"])
        self.assertNotIn("approved", result)

    def test_untrusted_source_cannot_register_evidence(self):
        with self.assertRaisesRegex(PermissionError, "not trusted"):
            self.fx.add(
                "verified_bank_feed", "caller_claimed_bank", "origin-1",
                "applicant_business", evidence_id="ev-fake",
            )

    def test_beneficial_owner_and_account_match_do_not_prove_authority(self):
        identity = self.fx.add(
            "government_identity_verified", "kyc_provider", "kyc-1",
            "applicant_person", PERSON_HASH, "ev-id",
        )
        beneficial = self.fx.add(
            "beneficial_owner_verified", "kyc_provider", "kyc-2",
            "applicant_business", BUSINESS_HASH, "ev-beneficial",
        )
        account = self.fx.add(
            "account_holder_match", "kyc_provider", "kyc-3",
            "applicant_business", BUSINESS_HASH, "ev-account",
        )
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-1",
            "applicant_business", evidence_id="ev-bank-2",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=[item["evidence_id"] for item in (identity, beneficial, account, bank)],
            legal_form="legal_entity", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertEqual(result["status"], "BLOCKED_NON_SUBSTITUTABLE_CONTROL")
        self.assertIn("authority", result["hard_control_gaps"])

    def test_cash_route_counts_distinct_types_and_origins(self):
        ids = self._individual_hard_controls()
        cash = self.fx.add(
            "cash_sales_log_observed", "merchant_log_review", "same-origin",
            "applicant_business", evidence_id="ev-cash",
        )
        supplier = self.fx.add(
            "supplier_confirmed_invoices", "supplier_feed", "same-origin",
            "applicant_business", evidence_id="ev-supplier",
        )
        site = self.fx.add(
            "site_visit_verified", "site_visit_team", "same-origin",
            "applicant_business", evidence_id="ev-site",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids + [cash["evidence_id"], supplier["evidence_id"], site["evidence_id"]],
            legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertNotIn("cash_business_observed", result["ready_routes"])
        cash_route = next(r for r in result["routes"] if r["route_id"] == "cash_business_observed")
        self.assertEqual(cash_route["independent_origin_count"], 1)

    def test_three_independent_cash_origins_are_ready(self):
        ids = self._individual_hard_controls()
        records = [
            self.fx.add("cash_sales_log_observed", "merchant_log_review", "merchant-ledger", "applicant_business", evidence_id="cash-1"),
            self.fx.add("supplier_confirmed_invoices", "supplier_feed", "supplier-42", "applicant_business", evidence_id="cash-2"),
            self.fx.add("site_visit_verified", "site_visit_team", "visit-team-7", "applicant_business", evidence_id="cash-3"),
        ]
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids + [r["evidence_id"] for r in records],
            legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertIn("cash_business_observed", result["ready_routes"])

    def test_subject_conflict_blocks_routing(self):
        ids = self._individual_hard_controls()
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-foreign",
            "applicant_business", OTHER_BUSINESS_HASH, "ev-wrong-business",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids + [bank["evidence_id"]],
            legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertEqual(result["status"], "BLOCKED_SUBJECT_CONFLICT")
        self.assertEqual(result["subject_conflicts"][0]["subject_key"], "applicant_business")

    def test_expired_revoked_and_unknown_records_fail_closed(self):
        ids = self._individual_hard_controls()
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-1", "applicant_business",
            evidence_id="ev-expiring",
        )
        revoke_evidence(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_id=bank["evidence_id"], owner_actor=self.fx.owner,
            reason="provider correction", actor="ops",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids + [bank["evidence_id"], "not-a-real-record"],
            legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
        )
        self.assertEqual(result["status"], "BLOCKED_EVIDENCE_INTEGRITY")
        self.assertEqual(
            {item["reason"] for item in result["invalid_records"]},
            {"revoked", "not_found_or_not_accessible"},
        )

    def test_record_expiry_is_rechecked_at_assessment_time(self):
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-expiring",
            "applicant_business", evidence_id="ev-short-lived",
        )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=[bank["evidence_id"]],
            legal_form="individual_business_owner", owner_actor=self.fx.owner,
            now=NOW + timedelta(days=31),
        )
        self.assertEqual(result["status"], "BLOCKED_EVIDENCE_INTEGRITY")
        self.assertEqual(result["invalid_records"][0]["reason"], "expired")

    def test_registration_rejects_wrong_subject_binding(self):
        with self.assertRaisesRegex(ValueError, "subject_key=applicant_person"):
            self.fx.add(
                "government_identity_verified", "kyc_provider", "kyc-wrong",
                "applicant_business", PERSON_HASH, "ev-wrong-subject",
            )

    def test_assessment_rejects_duplicate_or_non_string_ids(self):
        identity = self._individual_hard_controls()[0]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            assess_case_evidence_passport(
                self.fx.db_path, application_id=self.fx.application_id,
                evidence_ids=[identity, identity], legal_form="individual_business_owner",
                owner_actor=self.fx.owner, now=NOW,
            )
        with self.assertRaisesRegex(ValueError, "must be a string"):
            assess_case_evidence_passport(
                self.fx.db_path, application_id=self.fx.application_id,
                evidence_ids=[123], legal_form="individual_business_owner",
                owner_actor=self.fx.owner, now=NOW,
            )

    def test_withdrawn_consent_invalidates_bound_evidence(self):
        ids = self._individual_hard_controls()
        with ScoringLog(self.fx.db_path) as log:
            log.withdraw_consent(
                self.fx.application_id, self.fx.consent_id,
                "applicant requested withdrawal", self.fx.owner,
            )
        result = assess_case_evidence_passport(
            self.fx.db_path, application_id=self.fx.application_id,
            evidence_ids=ids, legal_form="individual_business_owner",
            owner_actor=self.fx.owner, now=NOW,
        )
        self.assertEqual(result["status"], "BLOCKED_EVIDENCE_INTEGRITY")
        self.assertTrue(all(r["reason"] == "consent_not_active" for r in result["invalid_records"]))

    def test_changed_provider_attestation_invalidates_old_record(self):
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-1",
            "applicant_business", evidence_id="ev-attested",
        )
        with patch.dict(os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry("v2")}):
            result = assess_case_evidence_passport(
                self.fx.db_path, application_id=self.fx.application_id,
                evidence_ids=[bank["evidence_id"]],
                legal_form="individual_business_owner", owner_actor=self.fx.owner, now=NOW,
            )
        self.assertEqual(result["invalid_records"][0]["reason"], "source_attestation_changed")

    def test_http_accepts_ids_and_rejects_old_self_assertion_contract(self):
        ids = self._individual_hard_controls()
        bank = self.fx.add(
            "verified_bank_feed", "bank_feed", "bank-1",
            "applicant_business", evidence_id="ev-http-bank",
        )
        with running_server(self.fx.db_path) as base:
            status, raw, _ = request(
                base, "/api/v1/evidence-passport/assessments", "POST", {
                    "application_id": self.fx.application_id,
                    "legal_form": "individual_business_owner",
                    "evidence_ids": ids + [bank["evidence_id"]],
                },
            )
            old_status, old_raw, _ = request(
                base, "/api/v1/evidence-passport/assessments", "POST", {
                    "business_type": "retail",
                    "available_evidence": ["government_identity_verified"],
                },
            )
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["data"]["status"], "READY_FOR_HUMAN_PARTNER_REVIEW")
        self.assertEqual(old_status, 422, old_raw)

    def test_production_partner_cannot_assess_another_tenant_case(self):
        identity = self._individual_hard_controls()[0]
        users = json.dumps({
            "partner_a": {"token": "a" * 32, "role": "partner"},
            "partner_b": {"token": "b" * 32, "role": "partner"},
        })
        with patch.dict(os.environ, {"OLIN_MODE": "production", "OLIN_USERS": users}):
            with running_server(self.fx.db_path) as base:
                status, raw, _ = request(
                    base, "/api/v1/evidence-passport/assessments", "POST", {
                        "application_id": self.fx.application_id,
                        "legal_form": "individual_business_owner",
                        "evidence_ids": [identity],
                    }, token="b" * 32,
                )
        self.assertEqual(status, 404, raw)


if __name__ == "__main__":
    unittest.main()
