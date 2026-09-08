from __future__ import annotations

import json
import os
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from olin.investigator.evidence import (
    EvidenceClass,
    EvidenceLifecycle,
    EvidenceUsability,
    UnusableReason,
    VerificationStatus,
)
from olin.investigator_evidence_adapter import (
    CanonicalArtifactRecord,
    CanonicalConsentAuthorization,
    CanonicalPropositionVerification,
    EvidencePassportReadAdapter,
    ExistingEvidencePassportReadPort,
    ExistingPassportCaseBinding,
)
from olin.source_trust import assess_source_attestation

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
TENANT = UUID(int=1)
CASE = UUID(int=10)


class Port:
    def __init__(self):
        self.artifact_record = CanonicalArtifactRecord(
            tenant_id=TENANT,
            case_id=CASE,
            subject_id="business-1",
            subject_digest="1" * 64,
            subject_controller_id="business-controller",
            namespace="evidence_passport",
            evidence_id="artifact-1",
            version="1",
            artifact_digest="2" * 64,
            data_class="bank_transaction_metadata",
            origin_class=EvidenceClass.EXTERNAL_EVIDENCE,
            lifecycle=EvidenceLifecycle.ACCEPTED,
            observed_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=30),
            source_id="bank_api",
            issuer_id="bank-issuer",
            acquisition_method="signed_webhook",
            consent_namespace="intake_consent",
            consent_id="consent-1",
            integrity_reference="passport-integrity:artifact-1",
            integrity_valid=True,
        )
        self.consent_record = CanonicalConsentAuthorization(
            namespace="intake_consent",
            consent_id="consent-1",
            version="receipt-1",
            tenant_id=TENANT,
            case_id=CASE,
            subject_id="business-1",
            subject_digest="1" * 64,
            purpose="investigator_analysis",
            data_class="bank_transaction_metadata",
            use_scope="case_evidence_analysis",
            status="ACTIVE",
            expires_at=NOW + timedelta(days=30),
            retention_until=NOW + timedelta(days=60),
        )
        self.proposition_record = CanonicalPropositionVerification(
            proposition_type="bank_reported_transaction",
            schema_version=1,
            value="opaque-transaction-1",
            unit="event",
            verification_method="signed_provider_record_match",
            period_start=NOW - timedelta(days=1),
            period_end=NOW - timedelta(days=1),
        )

    def artifact(self, namespace, evidence_id):
        self.assert_key(namespace, evidence_id)
        return self.artifact_record

    def consent(self, namespace, consent_id):
        if (namespace, consent_id) != ("intake_consent", "consent-1"):
            raise LookupError("consent not found")
        return self.consent_record

    def proposition(self, namespace, evidence_id):
        self.assert_key(namespace, evidence_id)
        return self.proposition_record

    @staticmethod
    def assert_key(namespace, evidence_id):
        if (namespace, evidence_id) != ("evidence_passport", "artifact-1"):
            raise LookupError("artifact not found")


def registry(**changes):
    entry = {
        "status": "active",
        "environment": "production",
        "issuer_id": "bank-issuer",
        "source_class": "regulated_financial_institution",
        "acquisition_methods": ["signed_webhook"],
        "proposition_types": ["bank_reported_transaction"],
        "tenant_ids": [str(TENANT)],
        "valid_until": "2026-12-31",
        "attestation_id": "attestation-1",
        "attestation_version": "1",
        "attestation_issuer_id": "olin-source-governance",
        "controller_id": "bank-controller",
        "independence_class": "independent_from_subject",
        "freshness_max_age_days": 90,
    }
    entry.update(changes)
    return json.dumps({"bank_api": entry})


class EvidencePassportAdapterTests(unittest.TestCase):
    def resolve(self, port=None):
        adapter = EvidencePassportReadAdapter(port or Port())
        with patch.dict(os.environ, {"OLIN_MODE": "pilot"}, clear=False):
            return adapter.resolve(
                tenant_id=TENANT,
                case_id=CASE,
                evidence_namespace="evidence_passport",
                evidence_id="artifact-1",
                purpose="investigator_analysis",
                as_of=NOW,
            )

    def test_production_source_and_narrow_proposition_resolve_verified_fact(self):
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            result = self.resolve()
        self.assertEqual(result.evidence_class, EvidenceClass.VERIFIED_FACT)
        self.assertEqual(
            result.verification_status, VerificationStatus.VERIFIED_FOR_PROPOSITION
        )
        self.assertEqual(result.proposition_type, "bank_reported_transaction")
        self.assertEqual(result.usability, EvidenceUsability.USABLE)

    def test_authentic_artifact_without_proposition_stays_external_unverified(self):
        port = Port()
        port.proposition_record = None
        configured = registry(proposition_types=["artifact_submission_recorded"])
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": configured}, clear=False
        ):
            result = self.resolve(port)
        self.assertEqual(result.evidence_class, EvidenceClass.EXTERNAL_EVIDENCE)
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertIsNone(result.proposition_type)

    def test_subject_mismatch_and_withdrawal_are_unusable_not_adverse(self):
        port = Port()
        port.consent_record = replace(
            port.consent_record,
            subject_digest="9" * 64,
            status="WITHDRAWN",
        )
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            result = self.resolve(port)
        self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)
        self.assertEqual(result.unusable_reason, UnusableReason.SUBJECT_MISMATCH)

    def test_consent_data_class_and_use_scope_are_enforced(self):
        for changes in (
            {"data_class": "unrelated_geolocation"},
            {"use_scope": "marketing_only"},
        ):
            port = Port()
            port.consent_record = replace(port.consent_record, **changes)
            with (
                self.subTest(changes=changes),
                patch.dict(
                    os.environ,
                    {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()},
                    clear=False,
                ),
            ):
                result = self.resolve(port)
                self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)
                self.assertEqual(
                    result.unusable_reason, UnusableReason.CONSENT_OUT_OF_SCOPE
                )

    def test_missing_consent_fails_closed_explicitly(self):
        port = Port()

        def missing_consent(namespace, consent_id):
            del namespace, consent_id
            raise LookupError("canonical consent not found")

        port.consent = missing_consent
        with (
            patch.dict(
                os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
            ),
            self.assertRaisesRegex(LookupError, "canonical consent not found"),
        ):
            self.resolve(port)

    def test_issuer_impersonation_wildcard_and_placeholder_fail_closed(self):
        attempts = (
            registry(issuer_id="other-issuer"),
            registry(proposition_types=["*"]),
            json.dumps(
                {
                    "bank_api": json.loads(registry())["bank_api"]
                    | {"attestation_id": "placeholder-attestation"}
                }
            ),
        )
        for configured in attempts:
            with (
                self.subTest(configured=configured),
                patch.dict(
                    os.environ,
                    {"OLIN_TRUSTED_SOURCE_REGISTRY": configured},
                    clear=False,
                ),
            ):
                result = self.resolve()
                self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)
                self.assertEqual(
                    result.unusable_reason, UnusableReason.SOURCE_NOT_TRUSTED
                )

    def test_attestation_rotation_changes_authoritative_reference(self):
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            first = self.resolve()
        with patch.dict(
            os.environ,
            {
                "OLIN_TRUSTED_SOURCE_REGISTRY": registry(
                    attestation_id="attestation-2", attestation_version="2"
                )
            },
            clear=False,
        ):
            second = self.resolve()
        self.assertNotEqual(first.source_attestation_id, second.source_attestation_id)
        self.assertNotEqual(
            first.source_attestation_version, second.source_attestation_version
        )

    def test_unrelated_registry_change_does_not_stale_source_attestation(self):
        configured = json.loads(registry())
        configured["unrelated_inactive_source"] = {"status": "inactive"}
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            first = self.resolve()
        with patch.dict(
            os.environ,
            {"OLIN_TRUSTED_SOURCE_REGISTRY": json.dumps(configured)},
            clear=False,
        ):
            second = self.resolve()
        self.assertEqual(first.source_registry_digest, second.source_registry_digest)

    def test_source_attestation_requires_exact_tenant_and_acquisition(self):
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            denied = assess_source_attestation(
                "bank_api",
                issuer_id="bank-issuer",
                acquisition_method="merchant_upload",
                proposition_type="bank_reported_transaction",
                tenant_id=str(TENANT),
                subject_controller_id="business-controller",
                as_of=NOW.date(),
                production=True,
            )
        self.assertFalse(denied.trusted)
        self.assertEqual(denied.reason, "acquisition_method_not_authorized")

    def test_future_stale_and_missing_freshness_policy_fail_closed(self):
        attempts = (
            (
                replace(Port().artifact_record, observed_at=NOW + timedelta(days=1)),
                registry(),
            ),
            (
                replace(Port().artifact_record, observed_at=NOW - timedelta(days=91)),
                registry(),
            ),
            (Port().artifact_record, registry(freshness_max_age_days=None)),
        )
        for artifact, configured in attempts:
            port = Port()
            port.artifact_record = artifact
            with (
                self.subTest(observed_at=artifact.observed_at, registry=configured),
                patch.dict(
                    os.environ,
                    {"OLIN_TRUSTED_SOURCE_REGISTRY": configured},
                    clear=False,
                ),
            ):
                result = self.resolve(port)
                self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)

    def test_merchant_or_collusive_source_cannot_self_verify(self):
        for changes in (
            {
                "source_class": "merchant_controlled",
                "controller_id": "merchant-controller",
                "independence_class": "subject_controlled",
            },
            {
                "source_class": "collusive_source",
                "controller_id": "review-ring",
            },
        ):
            port = Port()
            port.artifact_record = replace(
                port.artifact_record,
                origin_class=EvidenceClass.MERCHANT_SUPPLIED_ARTIFACT,
            )
            with (
                self.subTest(changes=changes),
                patch.dict(
                    os.environ,
                    {"OLIN_TRUSTED_SOURCE_REGISTRY": registry(**changes)},
                    clear=False,
                ),
            ):
                result = self.resolve(port)
                self.assertNotEqual(result.evidence_class, EvidenceClass.VERIFIED_FACT)
                self.assertNotEqual(
                    result.verification_status,
                    VerificationStatus.VERIFIED_FOR_PROPOSITION,
                )
                self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)

    def test_subject_controlled_shell_source_cannot_launder_independence(self):
        for changes in (
            {
                "controller_id": "business-controller",
                "attestation_issuer_id": "olin-source-governance",
            },
            {
                "controller_id": "shell-controller",
                "attestation_issuer_id": "shell-controller",
            },
            {
                "controller_id": "shell-controller",
                "attestation_issuer_id": "business-controller",
            },
        ):
            with (
                self.subTest(changes=changes),
                patch.dict(
                    os.environ,
                    {"OLIN_TRUSTED_SOURCE_REGISTRY": registry(**changes)},
                    clear=False,
                ),
            ):
                result = self.resolve()
                self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)
                self.assertEqual(
                    result.verification_status, VerificationStatus.UNVERIFIED
                )

    def test_integrity_reference_is_authority_derived_and_digest_covered(self):
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            first = self.resolve()
            port = Port()
            port.artifact_record = replace(
                port.artifact_record,
                integrity_reference="passport-integrity:corrected",
            )
            second = self.resolve(port)
        self.assertNotEqual(first.authority_digest(), second.authority_digest())

    def test_existing_passport_port_is_read_only_and_never_promotes_legacy_verified(
        self,
    ):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE scoring_log(application_id TEXT PRIMARY KEY, owner_actor TEXT);
            CREATE TABLE evidence_record(
              evidence_id TEXT, application_id TEXT, owner_actor TEXT,
              evidence_type TEXT, source_id TEXT, origin_id TEXT, subject_key TEXT,
              subject_hash TEXT, verification_method TEXT, source_reference TEXT,
              attestation_id TEXT, consent_id TEXT, status TEXT, observed_at TEXT,
              expires_at TEXT, metadata_sha256 TEXT, created_at TEXT
            );
            CREATE TABLE consent_record(
              consent_id TEXT, application_id TEXT, purpose TEXT,
              policy_version TEXT, text_sha256 TEXT, status TEXT, captured_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO scoring_log VALUES (?,?)", ("legacy-app", "bank-owner")
        )
        connection.execute(
            "INSERT INTO consent_record VALUES (?,?,?,?,?,?,?)",
            (
                "legacy-consent",
                "legacy-app",
                "credit_assessment",
                "v1",
                "4" * 64,
                "active",
                NOW.isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO evidence_record VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-evidence",
                "legacy-app",
                "bank-owner",
                "verified_bank_feed",
                "bank_api",
                "origin-1",
                "applicant_business",
                "1" * 64,
                "legacy_document_check",
                "source-ref-1",
                "legacy-attestation",
                "legacy-consent",
                "verified",
                (NOW - timedelta(days=1)).isoformat(),
                (NOW + timedelta(days=30)).isoformat(),
                "5" * 64,
                (NOW - timedelta(days=1)).isoformat(),
            ),
        )
        port = ExistingEvidencePassportReadPort(
            connection,
            binding=ExistingPassportCaseBinding(
                tenant_id=TENANT,
                case_id=CASE,
                application_id="legacy-app",
                owner_actor="bank-owner",
            ),
        )
        self.assertIsNone(port.proposition("evidence_passport", "legacy-evidence"))
        with patch.dict(
            os.environ, {"OLIN_TRUSTED_SOURCE_REGISTRY": registry()}, clear=False
        ):
            result = EvidencePassportReadAdapter(port).resolve(
                tenant_id=TENANT,
                case_id=CASE,
                evidence_namespace="evidence_passport",
                evidence_id="legacy-evidence",
                purpose="credit_assessment",
                as_of=NOW,
            )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertEqual(result.evidence_class, EvidenceClass.EXTERNAL_EVIDENCE)
        self.assertEqual(result.usability, EvidenceUsability.UNUSABLE)
        connection.close()


if __name__ == "__main__":
    unittest.main()
