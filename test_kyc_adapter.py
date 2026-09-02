import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from olin.evidence_passport import assess_case_evidence_passport
from olin.kyc import KYCVerification, SyntheticKYCVerifier, ingest_kyc_verification
from test_evidence_passport import (
    BUSINESS_HASH,
    NOW,
    PERSON_HASH,
    PassportFixture,
    registry,
)


def verification(**overrides):
    values = {
        "source_id": "kyc_provider",
        "session_id": "session-001",
        "status": "passed",
        "legal_form": "individual_business_owner",
        "identity_subject_hash": PERSON_HASH,
        "business_subject_hash": BUSINESS_HASH,
        "observed_at": (NOW - timedelta(hours=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
        "identity_verified": True,
        "authority_evidence_type": "individual_business_ownership_verified",
        "beneficial_owner_verified": False,
    }
    values.update(overrides)
    return KYCVerification(**values)


class KYCAdapterTests(unittest.TestCase):
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

    def _ingest(self, result):
        verifier = SyntheticKYCVerifier({result.session_id: result})
        return ingest_kyc_verification(
            self.fx.db_path,
            application_id=self.fx.application_id,
            owner_actor=self.fx.owner,
            consent_id=self.fx.consent_id,
            legal_form=result.legal_form,
            session_id=result.session_id,
            verifier=verifier,
        )

    def test_synthetic_adapter_registers_identity_and_correct_authority(self):
        first = self._ingest(verification())
        second = self._ingest(verification())
        self.assertEqual(first["status"], "verified_evidence_registered")
        self.assertTrue(first["authority_verified"])
        self.assertEqual(len(first["evidence_ids"]), 2)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["evidence_ids"], second["evidence_ids"])

    def test_legal_entity_kyc_does_not_invent_representative_authority(self):
        result = verification(
            legal_form="legal_entity",
            authority_evidence_type="",
            beneficial_owner_verified=True,
        )
        ingested = self._ingest(result)
        assessment = assess_case_evidence_passport(
            self.fx.db_path,
            application_id=self.fx.application_id,
            evidence_ids=ingested["evidence_ids"],
            legal_form="legal_entity",
            owner_actor=self.fx.owner,
            now=NOW,
        )
        self.assertFalse(ingested["authority_verified"])
        self.assertIn("authority", assessment["hard_control_gaps"])

    def test_failed_provider_result_creates_no_evidence(self):
        result = self._ingest(verification(status="failed", identity_verified=False))
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["evidence_ids"], [])

    def test_case_and_provider_legal_form_must_match(self):
        result = verification(legal_form="legal_entity", authority_evidence_type="")
        verifier = SyntheticKYCVerifier({result.session_id: result})
        with self.assertRaisesRegex(ValueError, "legal form conflicts"):
            ingest_kyc_verification(
                self.fx.db_path,
                application_id=self.fx.application_id,
                owner_actor=self.fx.owner,
                consent_id=self.fx.consent_id,
                legal_form="individual_business_owner",
                session_id=result.session_id,
                verifier=verifier,
            )

    def test_synthetic_kyc_is_disabled_for_real_modes(self):
        verifier = SyntheticKYCVerifier({"session-001": verification()})
        with patch.dict(os.environ, {"OLIN_MODE": "pilot"}):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                verifier.fetch_verification("session-001")


if __name__ == "__main__":
    unittest.main()
