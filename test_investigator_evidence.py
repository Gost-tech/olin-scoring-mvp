from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import UUID

from olin.investigator.actor import controlled_test_system_actor
from olin.investigator.authority import establish_runtime_database_custody
from olin.investigator.evidence import (
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    EvidenceAuthorityResolution,
    EvidenceBoundaryError,
    EvidenceClass,
    EvidenceLifecycle,
    EvidenceUsability,
    IndependenceStatus,
    LineageRelation,
    UnusableReason,
    VerificationStatus,
)
from olin.investigator.evidence_boundary import (
    CaseSubjectAuthority,
    InvestigatorEvidenceBoundary,
)
from olin.investigator.spine import InMemoryCaseSpine, SpineConflict

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


class UUIDs:
    def __init__(self, start: int):
        self._values = count(start)

    def __call__(self):
        return UUID(int=next(self._values))


class Subjects(CaseSubjectAuthority):
    def __init__(self, values):
        self.values = values

    def resolve_subject(self, *, tenant_id, case_id):
        return self.values[(tenant_id, case_id)]


class CanonicalAuthority:
    def __init__(self):
        self.values = {}

    def resolve(
        self, *, tenant_id, case_id, evidence_namespace, evidence_id, purpose, as_of
    ):
        del tenant_id, case_id, purpose, as_of
        return self.values[(evidence_namespace, evidence_id)]

    def revalidate(self, reference, *, as_of):
        del as_of
        return self.values[(reference.evidence_namespace, reference.evidence_id)]


class RuntimeDatabase:
    class Cursor:
        @staticmethod
        def fetchone():
            return True, True, False, False, True, True, True, True

    @staticmethod
    def execute(_query):
        return RuntimeDatabase.Cursor()


def runtime_custody():
    return establish_runtime_database_custody(RuntimeDatabase())


def resolution(tenant, bound_case_id, **changes):
    values = {
        "tenant_id": tenant,
        "case_id": bound_case_id,
        "subject_id": "canonical-business-1",
        "subject_digest": "1" * 64,
        "evidence_namespace": "evidence_passport",
        "evidence_id": "bank-event-1",
        "evidence_version": "1",
        "artifact_digest": "2" * 64,
        "evidence_class": EvidenceClass.VERIFIED_FACT,
        "lifecycle": EvidenceLifecycle.ACCEPTED,
        "verification_status": VerificationStatus.VERIFIED_FOR_PROPOSITION,
        "proposition_type": "bank_reported_transaction",
        "proposition_schema_version": 1,
        "proposition_value": "transaction-ref-opaque",
        "proposition_unit": "event",
        "verification_method": "signed_provider_record_match",
        "period_start": NOW - timedelta(days=1),
        "period_end": NOW - timedelta(days=1),
        "observed_at": NOW - timedelta(days=1),
        "evidence_expires_at": NOW + timedelta(days=30),
        "source_id": "partner_bank_api",
        "issuer_id": "bank-issuer-1",
        "acquisition_method": "signed_provider_webhook",
        "source_class": "regulated_financial_institution",
        "source_attestation_id": "attestation-1",
        "source_attestation_version": "1",
        "source_registry_digest": "3" * 64,
        "source_valid_until": NOW + timedelta(days=90),
        "production_qualified_source": True,
        "source_allows_proposition": True,
        "consent_namespace": "intake_consent",
        "consent_id": "consent-1",
        "consent_version": "receipt-sha256-1",
        "consent_purpose": "investigator_analysis",
        "consent_data_class": "bank_transaction_metadata",
        "consent_use_scope": "case_evidence_analysis",
        "consent_status": "ACTIVE",
        "consent_expires_at": NOW + timedelta(days=30),
        "retention_until": NOW + timedelta(days=60),
        "integrity_reference": "passport-integrity:event-1",
        "integrity_valid": True,
        "usability": EvidenceUsability.USABLE,
        "unusable_reason": None,
        "resolver_version": EVIDENCE_RESOLVER_CONTRACT_VERSION,
        "resolved_at": NOW,
        "semantic_independence_schema_version": 1,
        "semantic_lineage_id": "lineage-bank-event-1",
        "lineage_relation": LineageRelation.ORIGINAL,
        "derived_from_evidence_namespace": None,
        "derived_from_evidence_id": None,
        "derived_from_evidence_version": None,
        "economic_event_id": None,
        "upstream_issuer_id": "bank-issuer-1",
        "independence_status": IndependenceStatus.INDEPENDENCE_UNKNOWN,
        "independence_attestation_id": None,
        "independence_attestation_version": None,
    }
    values.update(changes)
    return EvidenceAuthorityResolution._from_authoritative_adapter(**values)


class InvestigatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tenant = UUID(int=1)
        self.other_tenant = UUID(int=2)
        self.case_id = UUID(int=10)
        self.spine = InMemoryCaseSpine(clock=lambda: NOW, uuid_factory=UUIDs(100))
        self.actor = controlled_test_system_actor(
            tenant_id=self.tenant,
            case_id=self.case_id,
            correlation_id="phase2-tests",
            created_at=NOW,
        )
        self.spine.create_case(
            tenant_id=self.tenant,
            case_id=self.case_id,
            cohort_reference=None,
            legacy_case_reference=None,
            actor=self.actor,
            idempotency_key="create-case-phase2",
            occurred_at=NOW,
        )
        self.initial_snapshot = self.spine.create_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=1,
            actor=self.actor,
            idempotency_key="initial-snapshot-phase2",
        )
        self.authority = CanonicalAuthority()
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant, self.case_id
        )
        self.subjects = Subjects(
            {(self.tenant, self.case_id): ("canonical-business-1", "1" * 64)}
        )
        self.boundary = InvestigatorEvidenceBoundary(
            spine=self.spine,
            evidence_authority=self.authority,
            subject_authority=self.subjects,
            runtime_custody=runtime_custody(),
            uuid_factory=UUIDs(500),
        )

    def accept(self, **changes):
        values = {
            "tenant_id": self.tenant,
            "case_id": self.case_id,
            "current_snapshot_id": self.initial_snapshot.snapshot_id,
            "expected_case_version": 1,
            "evidence_namespace": "evidence_passport",
            "evidence_id": "bank-event-1",
            "purpose": "investigator_analysis",
            "actor": self.actor,
            "idempotency_key": "accept-evidence-1",
            "occurred_at": NOW,
        }
        values.update(changes)
        return self.boundary.accept_evidence(**values)

    def test_caller_trust_labels_confer_no_authority(self):
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant,
            self.case_id,
            evidence_class=EvidenceClass.EXTERNAL_EVIDENCE,
            verification_status=VerificationStatus.UNVERIFIED,
            proposition_type=None,
            proposition_schema_version=None,
            proposition_value=None,
            proposition_unit=None,
            verification_method=None,
        )
        accepted = self.accept(
            submitted_claims={
                "verified": True,
                "trusted": True,
                "issuer_validated": True,
                "source_verified": True,
                "official": True,
                "validated": True,
            }
        )
        self.assertEqual(
            accepted.reference.verification_status, VerificationStatus.UNVERIFIED
        )

    def test_unknown_or_placeholder_source_cannot_become_trusted(self):
        for index, source in enumerate(("unknown", "example_bank")):
            with self.subTest(source=source):
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    resolution(
                        self.tenant,
                        self.case_id,
                        source_id=source,
                        production_qualified_source=False,
                    )
                )
                with self.assertRaisesRegex(
                    EvidenceBoundaryError, "SOURCE_NOT_TRUSTED"
                ):
                    self.accept(idempotency_key=f"untrusted-source-{index}")

    def test_tenant_case_and_subject_mismatch_are_denied(self):
        mutations = (
            {"tenant_id": self.other_tenant},
            {"case_id": UUID(int=11)},
            {"subject_digest": "9" * 64},
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    resolution(self.tenant, self.case_id, **mutation)
                )
                with self.assertRaises(EvidenceBoundaryError):
                    self.accept(idempotency_key=f"binding-mismatch-{index}")

    def test_consent_is_purpose_specific_and_time_local(self):
        changes = (
            {"consent_purpose": "credit_bureau"},
            {
                "consent_status": "WITHDRAWN",
                "usability": EvidenceUsability.UNUSABLE,
                "unusable_reason": UnusableReason.CONSENT_WITHDRAWN,
            },
            {"consent_expires_at": NOW},
            {"retention_until": NOW},
        )
        for index, mutation in enumerate(changes):
            with self.subTest(mutation=mutation):
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    resolution(self.tenant, self.case_id, **mutation)
                )
                with self.assertRaises(EvidenceBoundaryError):
                    self.accept(idempotency_key=f"consent-denied-{index}")

    def test_authentic_artifact_verifies_only_its_named_proposition(self):
        accepted = self.accept()
        self.assertEqual(
            accepted.reference.proposition_type, "bank_reported_transaction"
        )
        self.assertNotEqual(
            accepted.reference.proposition_type, "complete_business_revenue"
        )
        self.assertNotEqual(accepted.reference.proposition_type, "beneficial_ownership")

    def test_merchant_artifact_cannot_self_promote(self):
        with self.assertRaisesRegex(EvidenceBoundaryError, "only VERIFIED_FACT"):
            resolution(
                self.tenant,
                self.case_id,
                evidence_class=EvidenceClass.MERCHANT_SUPPLIED_ARTIFACT,
            )

    def test_external_and_merchant_artifacts_remain_unverified(self):
        for evidence_class in (
            EvidenceClass.EXTERNAL_EVIDENCE,
            EvidenceClass.MERCHANT_SUPPLIED_ARTIFACT,
        ):
            item = resolution(
                self.tenant,
                self.case_id,
                evidence_class=evidence_class,
                verification_status=VerificationStatus.UNVERIFIED,
                proposition_type=None,
                proposition_schema_version=None,
                proposition_value=None,
                proposition_unit=None,
                verification_method=None,
            )
            self.assertEqual(item.verification_status, VerificationStatus.UNVERIFIED)

    def test_experimental_observation_is_reserved_without_an_acquisition_engine(self):
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant,
            self.case_id,
            evidence_class=EvidenceClass.EXPERIMENTAL_OBSERVATION,
            verification_status=VerificationStatus.UNVERIFIED,
            proposition_type=None,
            proposition_schema_version=None,
            proposition_value=None,
            proposition_unit=None,
            verification_method=None,
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "not enabled"):
            self.accept()

    def test_lifecycle_states_are_historical_but_unusable(self):
        reasons = {
            EvidenceLifecycle.QUARANTINED: UnusableReason.EVIDENCE_QUARANTINED,
            EvidenceLifecycle.DISPUTED: UnusableReason.EVIDENCE_DISPUTED,
            EvidenceLifecycle.SUPERSEDED: UnusableReason.EVIDENCE_SUPERSEDED,
            EvidenceLifecycle.REVOKED: UnusableReason.EVIDENCE_REVOKED,
            EvidenceLifecycle.EXPIRED: UnusableReason.EVIDENCE_EXPIRED,
        }
        for lifecycle, reason in reasons.items():
            item = resolution(
                self.tenant,
                self.case_id,
                lifecycle=lifecycle,
                usability=EvidenceUsability.UNUSABLE,
                unusable_reason=reason,
            )
            self.assertEqual(
                item.current_usability(as_of=NOW), (EvidenceUsability.UNUSABLE, reason)
            )

    def test_acceptance_stales_old_snapshot_and_v2_is_deterministic(self):
        old_bytes = bytes(self.initial_snapshot.canonical_snapshot_bytes)
        self.accept()
        self.assertFalse(
            self.spine.is_snapshot_current(
                tenant_id=self.tenant, snapshot_id=self.initial_snapshot.snapshot_id
            )
        )
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-v2-1",
            as_of=NOW,
        )
        replay = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-v2-1",
            as_of=NOW,
        )
        self.assertIs(snapshot, replay)
        self.assertEqual(snapshot.snapshot_schema_version, 2)
        self.assertEqual(
            len(
                snapshot.canonical_snapshot_payload["evidence"][
                    "accepted_evidence_refs"
                ]
            ),
            1,
        )
        self.assertEqual(self.initial_snapshot.canonical_snapshot_bytes, old_bytes)
        self.assertTrue(
            self.boundary.is_snapshot_current_for_reasoning(
                tenant_id=self.tenant, snapshot_id=snapshot.snapshot_id, as_of=NOW
            )
        )

    def test_withdrawal_or_attestation_change_blocks_reasoning_and_keeps_history(self):
        accepted = self.accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-v2-live",
            as_of=NOW,
        )
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        for mutation in (
            {
                "consent_status": "WITHDRAWN",
                "usability": EvidenceUsability.UNUSABLE,
                "unusable_reason": UnusableReason.CONSENT_WITHDRAWN,
            },
            {
                "source_attestation_id": "attestation-2",
                "source_attestation_version": "2",
            },
        ):
            with self.subTest(mutation=mutation):
                values = {
                    field: getattr(original, field)
                    for field in original.__dataclass_fields__
                }
                values.update(mutation)
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    EvidenceAuthorityResolution._from_authoritative_adapter(**values)
                )
                self.assertFalse(
                    self.boundary.is_snapshot_current_for_reasoning(
                        tenant_id=self.tenant,
                        snapshot_id=snapshot.snapshot_id,
                        as_of=NOW,
                    )
                )
                self.assertEqual(
                    self.boundary.references(
                        tenant_id=self.tenant, case_id=self.case_id
                    ),
                    (accepted.reference,),
                )

    def test_every_authority_semantic_change_stales_snapshot(self):
        self.accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-v2-semantic-matrix",
            as_of=NOW,
        )
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        mutations = (
            {"proposition_type": "bank_reported_balance"},
            {"proposition_value": "corrected-value"},
            {"proposition_unit": "record"},
            {"verification_method": "corrected-method"},
            {"period_start": NOW - timedelta(days=2)},
            {"issuer_id": "corrected-issuer"},
            {"acquisition_method": "corrected-acquisition"},
            {"source_class": "corrected-source-class"},
            {"consent_purpose": "different-purpose"},
            {"consent_data_class": "different-data-class"},
            {"consent_use_scope": "different-use-scope"},
            {"lifecycle": EvidenceLifecycle.DISPUTED},
            {"evidence_expires_at": NOW + timedelta(days=29)},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                values = {
                    field: getattr(original, field)
                    for field in original.__dataclass_fields__
                }
                values.update(mutation)
                if mutation.get("lifecycle") is EvidenceLifecycle.DISPUTED:
                    values.update(
                        usability=EvidenceUsability.UNUSABLE,
                        unusable_reason=UnusableReason.EVIDENCE_DISPUTED,
                    )
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    EvidenceAuthorityResolution._from_authoritative_adapter(**values)
                )
                self.assertFalse(
                    self.boundary.is_snapshot_current_for_reasoning(
                        tenant_id=self.tenant,
                        snapshot_id=snapshot.snapshot_id,
                        as_of=NOW,
                    )
                )
        self.authority.values[("evidence_passport", "bank-event-1")] = original

    def test_case_subject_rebinding_stales_snapshot(self):
        self.accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-subject-rebinding",
            as_of=NOW,
        )
        self.subjects.values[(self.tenant, self.case_id)] = (
            "corrected-business",
            "9" * 64,
        )
        self.assertFalse(
            self.boundary.is_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )
        )

    def test_consent_change_event_is_idempotent_and_new_snapshot_is_unusable(self):
        accepted = self.accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-withdrawal",
            as_of=NOW,
        )
        current = self.authority.values[("evidence_passport", "bank-event-1")]
        values = {
            field: getattr(current, field) for field in current.__dataclass_fields__
        }
        values.update(
            consent_status="WITHDRAWN",
            usability=EvidenceUsability.UNUSABLE,
            unusable_reason=UnusableReason.CONSENT_WITHDRAWN,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            EvidenceAuthorityResolution._from_authoritative_adapter(**values)
        )
        arguments = {
            "tenant_id": self.tenant,
            "case_id": self.case_id,
            "current_snapshot_id": snapshot.snapshot_id,
            "consent_namespace": accepted.reference.consent_namespace,
            "consent_id": accepted.reference.consent_id,
            "status": "WITHDRAWN",
            "expected_case_version": 2,
            "reason_reference": "canonical-withdrawal-receipt-1",
            "actor": self.actor,
            "idempotency_key": "consent-withdrawal-event",
            "occurred_at": NOW,
        }
        event = self.boundary.record_consent_state_changed(**arguments)
        self.assertIs(event, self.boundary.record_consent_state_changed(**arguments))
        replacement = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=3,
            actor=self.actor,
            idempotency_key="snapshot-after-withdrawal",
            as_of=NOW,
        )
        evidence = replacement.canonical_snapshot_payload["evidence"]
        self.assertEqual(evidence["accepted_evidence_refs"], ())
        self.assertEqual(len(evidence["unusable_evidence_refs"]), 1)
        self.assertEqual(
            self.boundary.references(tenant_id=self.tenant, case_id=self.case_id),
            (accepted.reference,),
        )

    def test_state_change_commands_reject_current_snapshot_from_another_case(self):
        accepted = self.accept()
        other_case = UUID(int=11)
        other_actor = controlled_test_system_actor(
            tenant_id=self.tenant,
            case_id=other_case,
            correlation_id="phase2-cross-case-snapshot",
            created_at=NOW,
        )
        self.spine.create_case(
            tenant_id=self.tenant,
            case_id=other_case,
            cohort_reference=None,
            legacy_case_reference=None,
            actor=other_actor,
            idempotency_key="create-other-case",
            occurred_at=NOW,
        )
        other_snapshot = self.spine.create_snapshot(
            tenant_id=self.tenant,
            case_id=other_case,
            expected_case_version=1,
            actor=other_actor,
            idempotency_key="other-case-snapshot",
        )

        current = self.authority.values[("evidence_passport", "bank-event-1")]
        values = {
            field: getattr(current, field) for field in current.__dataclass_fields__
        }
        values.update(
            lifecycle=EvidenceLifecycle.REVOKED,
            usability=EvidenceUsability.UNUSABLE,
            unusable_reason=UnusableReason.EVIDENCE_REVOKED,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            EvidenceAuthorityResolution._from_authoritative_adapter(**values)
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "snapshot does not belong"):
            self.boundary.record_evidence_became_unusable(
                tenant_id=self.tenant,
                case_id=self.case_id,
                current_snapshot_id=other_snapshot.snapshot_id,
                reference_id=accepted.reference.reference_id,
                expected_case_version=2,
                reason_reference="canonical-revocation",
                actor=self.actor,
                idempotency_key="cross-case-evidence-state",
                occurred_at=NOW,
            )

        values.update(
            lifecycle=EvidenceLifecycle.ACCEPTED,
            consent_status="WITHDRAWN",
            unusable_reason=UnusableReason.CONSENT_WITHDRAWN,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            EvidenceAuthorityResolution._from_authoritative_adapter(**values)
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "snapshot does not belong"):
            self.boundary.record_consent_state_changed(
                tenant_id=self.tenant,
                case_id=self.case_id,
                current_snapshot_id=other_snapshot.snapshot_id,
                consent_namespace=accepted.reference.consent_namespace,
                consent_id=accepted.reference.consent_id,
                status="WITHDRAWN",
                expected_case_version=2,
                reason_reference="canonical-withdrawal",
                actor=self.actor,
                idempotency_key="cross-case-consent-state",
                occurred_at=NOW,
            )

    def test_duplicate_replay_is_idempotent_and_conflicts_fail(self):
        first = self.accept()
        replay = self.accept()
        self.assertIs(first, replay)
        with self.assertRaises(SpineConflict):
            self.accept(evidence_id="different", idempotency_key="accept-evidence-1")

    def test_same_artifact_under_new_identity_cannot_add_weight(self):
        self.accept()
        self.authority.values[("evidence_passport", "bank-event-2")] = resolution(
            self.tenant, self.case_id, evidence_id="bank-event-2"
        )
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-duplicate",
            as_of=NOW,
        )
        with self.assertRaisesRegex(SpineConflict, "artifact content"):
            self.accept(
                current_snapshot_id=current.snapshot_id,
                expected_case_version=2,
                evidence_id="bank-event-2",
                idempotency_key="duplicate-content",
            )

    def test_correction_appends_without_rewriting_history(self):
        first = self.accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-correction",
            as_of=NOW,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant,
            self.case_id,
            evidence_version="2",
            artifact_digest="4" * 64,
            lineage_relation=LineageRelation.CORRECTION,
            derived_from_evidence_namespace="evidence_passport",
            derived_from_evidence_id="bank-event-1",
            derived_from_evidence_version="1",
        )
        second = self.accept(
            current_snapshot_id=current.snapshot_id,
            expected_case_version=2,
            idempotency_key="accept-correction",
            supersedes_reference_id=first.reference.reference_id,
        )
        self.assertNotEqual(first.reference.reference_id, second.reference.reference_id)
        self.assertEqual(
            second.reference.supersedes_reference_id, first.reference.reference_id
        )
        replacement = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=3,
            actor=self.actor,
            idempotency_key="snapshot-after-correction",
            as_of=NOW,
        )
        evidence = replacement.canonical_snapshot_payload["evidence"]
        self.assertEqual(len(evidence["accepted_evidence_refs"]), 1)
        self.assertEqual(len(evidence["unusable_evidence_refs"]), 1)
        self.assertEqual(
            evidence["accepted_evidence_refs"][0]["acceptance"][
                "supersedes_reference_id"
            ],
            str(first.reference.reference_id),
        )
        self.assertEqual(
            evidence["unusable_evidence_refs"][0]["unusable_reason"],
            "EVIDENCE_SUPERSEDED",
        )
        self.assertEqual(
            len(self.boundary.references(tenant_id=self.tenant, case_id=self.case_id)),
            2,
        )
        self.assertTrue(
            self.boundary.is_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                snapshot_id=replacement.snapshot_id,
                as_of=NOW,
            )
        )

    def test_raw_v1_or_stale_snapshot_cannot_reason(self):
        self.assertFalse(
            self.boundary.is_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                snapshot_id=self.initial_snapshot.snapshot_id,
                as_of=NOW,
            )
        )
        self.accept()
        with self.assertRaisesRegex(EvidenceBoundaryError, "current CaseSnapshot"):
            self.accept(idempotency_key="accept-from-stale")

    def test_snapshots_exclude_arbitrary_blobs_and_business_interpretation(self):
        self.accept(submitted_claims={"revenue": 999999, "verified": True})
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-no-blobs",
            as_of=NOW,
        )
        payload = snapshot.canonical_snapshot_bytes.decode("utf-8")
        self.assertNotIn("999999", payload)
        self.assertNotIn("complete_business_revenue", payload)

    def test_verified_fact_requires_period_and_bounded_proposition(self):
        with self.assertRaisesRegex(EvidenceBoundaryError, "coverage period"):
            resolution(self.tenant, self.case_id, period_start=None, period_end=None)
        with self.assertRaisesRegex(EvidenceBoundaryError, "proposition_value"):
            resolution(self.tenant, self.case_id, proposition_value="x" * 513)

    def test_shifted_acceptance_clock_cannot_admit_future_evidence(self):
        future = NOW + timedelta(days=1)
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant,
            self.case_id,
            observed_at=future,
            period_start=future,
            period_end=future,
            evidence_expires_at=future + timedelta(days=30),
            resolved_at=future,
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "server clock"):
            self.accept(occurred_at=future)

    def test_historical_as_of_cannot_make_expired_snapshot_current(self):
        self.accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-clock-advance",
            as_of=NOW,
        )
        self.spine._clock = lambda: NOW + timedelta(days=100)
        with self.assertRaisesRegex(EvidenceBoundaryError, "server clock"):
            self.boundary.create_snapshot_v2(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=2,
                actor=self.actor,
                idempotency_key="historical-as-of-replay",
                as_of=NOW,
            )
        self.assertFalse(
            self.boundary.is_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )
        )

    def test_authority_rotation_has_audited_superseding_recovery_path(self):
        first = self.accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="snapshot-before-authority-rotation",
            as_of=NOW,
        )
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        values = {
            field: getattr(original, field) for field in original.__dataclass_fields__
        }
        values.update(
            evidence_version="2",
            source_attestation_id="attestation-2",
            source_attestation_version="2",
            lineage_relation=LineageRelation.CORRECTION,
            derived_from_evidence_namespace="evidence_passport",
            derived_from_evidence_id="bank-event-1",
            derived_from_evidence_version="1",
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            EvidenceAuthorityResolution._from_authoritative_adapter(**values)
        )
        self.boundary.record_evidence_became_unusable(
            tenant_id=self.tenant,
            case_id=self.case_id,
            current_snapshot_id=current.snapshot_id,
            reference_id=first.reference.reference_id,
            expected_case_version=2,
            reason_reference="source-attestation-rotation-2",
            actor=self.actor,
            idempotency_key="record-authority-rotation",
            occurred_at=NOW,
        )
        stale = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=3,
            actor=self.actor,
            idempotency_key="snapshot-after-authority-rotation",
            as_of=NOW,
        )
        second = self.accept(
            current_snapshot_id=stale.snapshot_id,
            expected_case_version=3,
            idempotency_key="accept-authority-rotation",
            supersedes_reference_id=first.reference.reference_id,
        )
        self.assertEqual(
            second.reference.artifact_digest, first.reference.artifact_digest
        )
        replacement = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=4,
            actor=self.actor,
            idempotency_key="snapshot-after-authority-reacceptance",
            as_of=NOW,
        )
        evidence = replacement.canonical_snapshot_payload["evidence"]
        self.assertEqual(len(evidence["accepted_evidence_refs"]), 1)
        self.assertEqual(len(evidence["unusable_evidence_refs"]), 1)


if __name__ == "__main__":
    unittest.main()
