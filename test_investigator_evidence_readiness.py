from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import UUID

from olin.investigator.actor import controlled_test_system_actor
from olin.investigator.authority import (
    AuthorityDenied,
    assert_evidence_authority_database_custody,
    assert_runtime_database_custody,
    establish_runtime_database_custody,
)
from olin.investigator.canonical import canonical_digest
from olin.investigator.evidence import (
    EvidenceBoundaryError,
    EvidenceLifecycle,
    IndependenceStatus,
    LineageRelation,
)
from olin.investigator.evidence_boundary import (
    InvestigatorEvidenceBoundary,
    PostgresReasoningSnapshotGate,
    ReasoningReadySnapshot,
)
from olin.investigator.spine import InMemoryCaseSpine
from olin.investigator_evidence_adapter import PostgresCanonicalEvidenceReadPort
from test_investigator_evidence import (
    CanonicalAuthority,
    Subjects,
    resolution,
    runtime_custody,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


def changed_resolution(value, **changes):
    values = {field: getattr(value, field) for field in value.__dataclass_fields__}
    values.update(changes)
    return type(value)._from_authoritative_adapter(**values)


class UUIDs:
    def __init__(self, start: int):
        self._values = count(start)

    def __call__(self):
        return UUID(int=next(self._values))


class Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchmany(self, _size):
        if isinstance(self._row, list):
            return self._row[:2]
        return [] if self._row is None else [self._row]


class FakePostgres:
    __module__ = "psycopg.testing"

    def __init__(self, row, *, reader_custody=None):
        self.row = row
        self.calls = []
        self.reader_custody = reader_custody or (
            True,
            True,
            True,
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            True,
            True,
        )

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        if "olin_investigator_evidence_reader" in query:
            return Cursor(self.reader_custody)
        return Cursor(self.row)


class RuntimeSnapshotPostgres:
    __module__ = "psycopg.testing"

    def __init__(self, snapshot_row):
        self.snapshot_row = snapshot_row
        self.calls = []
        self.final_time = snapshot_row[6]

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        if "current_user = 'olin_investigator_runtime'" in query:
            return Cursor((True, True, False, False, True, True, True, True))
        if "canonical.authority_revision" in query and "case_snapshot" not in query:
            return Cursor(
                (
                    7001,
                    "42",
                    True,
                    True,
                    self.final_time,
                    self.snapshot_row[7],
                    self.snapshot_row[8],
                )
            )
        if "transaction_isolation') = 'read committed'" in query and (
            "case_snapshot" not in query
        ):
            return Cursor((True, True))
        if "pg_advisory_xact_lock_shared" in query:
            return Cursor((None,))
        if "pg_current_xact_id()::text" in query and "case_snapshot" not in query:
            return Cursor((7001, "42"))
        return Cursor(self.snapshot_row)


class EvidenceReasoningReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tenant = UUID(int=1)
        self.case_id = UUID(int=10)
        self.spine = InMemoryCaseSpine(clock=lambda: NOW, uuid_factory=UUIDs(2000))
        self.actor = controlled_test_system_actor(
            tenant_id=self.tenant,
            case_id=self.case_id,
            correlation_id="phase25-readiness",
            created_at=NOW,
        )
        self.spine.create_case(
            tenant_id=self.tenant,
            case_id=self.case_id,
            cohort_reference=None,
            legacy_case_reference=None,
            actor=self.actor,
            idempotency_key="case-phase25",
            occurred_at=NOW,
        )
        self.initial = self.spine.create_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=1,
            actor=self.actor,
            idempotency_key="snapshot-v1-phase25",
        )
        self.authority = CanonicalAuthority()
        self.authority.values[("evidence_passport", "bank-event-1")] = resolution(
            self.tenant, self.case_id
        )
        self.boundary = InvestigatorEvidenceBoundary(
            spine=self.spine,
            evidence_authority=self.authority,
            subject_authority=Subjects(
                {(self.tenant, self.case_id): ("canonical-business-1", "1" * 64)}
            ),
            runtime_custody=runtime_custody(),
            uuid_factory=UUIDs(3000),
        )

    def _accept(self, **changes):
        values = {
            "tenant_id": self.tenant,
            "case_id": self.case_id,
            "current_snapshot_id": self.initial.snapshot_id,
            "expected_case_version": 1,
            "evidence_namespace": "evidence_passport",
            "evidence_id": "bank-event-1",
            "purpose": "investigator_analysis",
            "actor": self.actor,
            "idempotency_key": "accept-phase25",
            "occurred_at": NOW,
        }
        values.update(changes)
        return self.boundary.accept_evidence(**values)

    def test_caller_independence_labels_confer_no_authority(self):
        accepted = self._accept(
            submitted_claims={
                "independent": True,
                "independence_status": "INDEPENDENT_VERIFIED",
                "semantic_lineage_id": "caller-lineage",
            }
        )
        self.assertEqual(
            accepted.reference.independence_status,
            IndependenceStatus.INDEPENDENCE_UNKNOWN,
        )
        self.assertEqual(accepted.reference.semantic_lineage_id, "lineage-bank-event-1")

    def test_copy_and_correction_cannot_self_promote_to_independent(self):
        first = self._accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="current-phase25",
            as_of=NOW,
        )
        self.authority.values[("evidence_passport", "copy-1")] = resolution(
            self.tenant,
            self.case_id,
            evidence_id="copy-1",
            evidence_version="1",
            artifact_digest="4" * 64,
            semantic_lineage_id=first.reference.semantic_lineage_id,
            lineage_relation=LineageRelation.DERIVED_COPY,
            derived_from_evidence_namespace="evidence_passport",
            derived_from_evidence_id="bank-event-1",
            derived_from_evidence_version="1",
        )
        copy = self._accept(
            current_snapshot_id=current.snapshot_id,
            expected_case_version=2,
            evidence_id="copy-1",
            idempotency_key="copy-phase25",
        )
        self.assertEqual(copy.reference.lineage_relation, LineageRelation.DERIVED_COPY)
        self.assertEqual(
            copy.reference.independence_status,
            IndependenceStatus.INDEPENDENCE_UNKNOWN,
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "proven original"):
            changed_resolution(
                self.authority.values[("evidence_passport", "copy-1")],
                independence_status=IndependenceStatus.INDEPENDENT_VERIFIED,
                independence_attestation_id="independence-1",
                independence_attestation_version="1",
            )

    def test_verified_independence_requires_server_attestation(self):
        value = self.authority.values[("evidence_passport", "bank-event-1")]
        with self.assertRaisesRegex(EvidenceBoundaryError, "versioned attestation"):
            changed_resolution(
                value,
                independence_status=IndependenceStatus.INDEPENDENT_VERIFIED,
            )

    def test_unknown_lineage_cannot_become_verified_independent(self):
        value = self.authority.values[("evidence_passport", "bank-event-1")]
        with self.assertRaisesRegex(EvidenceBoundaryError, "proven original"):
            changed_resolution(
                value,
                lineage_relation=LineageRelation.UNKNOWN,
                independence_status=IndependenceStatus.INDEPENDENT_VERIFIED,
                independence_attestation_id="independence-unknown-lineage",
                independence_attestation_version="1",
            )

    def test_derived_and_corrected_evidence_require_real_parent_relationships(self):
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            changed_resolution(
                original,
                lineage_relation=LineageRelation.DERIVED_COPY,
                derived_from_evidence_namespace="evidence_passport",
                derived_from_evidence_id="fictional-parent",
                derived_from_evidence_version="1",
            )
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "existing parent"):
            self._accept()
        self.authority.values[("evidence_passport", "bank-event-1")] = original
        self._accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="parent-current-phase25",
            as_of=NOW,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            changed_resolution(
                original,
                evidence_version="2",
                artifact_digest="5" * 64,
                lineage_relation=LineageRelation.CORRECTION,
                derived_from_evidence_namespace="evidence_passport",
                derived_from_evidence_id="bank-event-1",
                derived_from_evidence_version="1",
            )
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "superseded"):
            self._accept(
                current_snapshot_id=current.snapshot_id,
                expected_case_version=2,
                idempotency_key="correction-without-parent-phase25",
            )

    def test_verified_independence_basis_cannot_be_reused_across_aliases(self):
        first = self.authority.values[("evidence_passport", "bank-event-1")]
        first = changed_resolution(
            first,
            economic_event_id="economic-event-1",
            independence_status=IndependenceStatus.INDEPENDENT_VERIFIED,
            independence_attestation_id="independence-basis-1",
            independence_attestation_version="1",
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = first
        self._accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="independence-current-phase25",
            as_of=NOW,
        )
        alias = changed_resolution(
            first,
            evidence_id="bank-alias-event-1",
            artifact_digest="6" * 64,
            semantic_lineage_id="alias-lineage-1",
            independence_attestation_id="independence-basis-2",
        )
        self.authority.values[("evidence_passport", "bank-alias-event-1")] = alias
        with self.assertRaisesRegex(EvidenceBoundaryError, "basis cannot be reused"):
            self._accept(
                current_snapshot_id=current.snapshot_id,
                expected_case_version=2,
                evidence_id="bank-alias-event-1",
                idempotency_key="alias-event-phase25",
            )
        self.authority.values[("evidence_passport", "bank-alias-event-1")] = (
            changed_resolution(
                alias,
                economic_event_id="economic-event-2",
                upstream_issuer_id="bank-issuer-2",
                independence_attestation_id="independence-basis-1",
            )
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "basis cannot be reused"):
            self._accept(
                current_snapshot_id=current.snapshot_id,
                expected_case_version=2,
                evidence_id="bank-alias-event-1",
                idempotency_key="alias-attestation-phase25",
            )

    def test_attestation_version_and_whitespace_cannot_bypass_reuse(self):
        first = changed_resolution(
            self.authority.values[("evidence_passport", "bank-event-1")],
            independence_status=IndependenceStatus.INDEPENDENT_VERIFIED,
            independence_attestation_id="stable-independence-basis",
            independence_attestation_version="1",
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = first
        self._accept()
        current = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="stable-basis-current",
            as_of=NOW,
        )
        alias = changed_resolution(
            first,
            evidence_id="bank-event-alias",
            artifact_digest="7" * 64,
            semantic_lineage_id="alias-lineage",
            independence_attestation_version="2",
        )
        self.authority.values[("evidence_passport", "bank-event-alias")] = alias
        with self.assertRaisesRegex(EvidenceBoundaryError, "basis cannot be reused"):
            self._accept(
                current_snapshot_id=current.snapshot_id,
                expected_case_version=2,
                evidence_id="bank-event-alias",
                idempotency_key="version-bump-alias",
            )
        with self.assertRaisesRegex(EvidenceBoundaryError, "canonical identifier"):
            changed_resolution(first, semantic_lineage_id=" lineage-bank-event-1")

    def test_reasoning_gate_issues_opaque_current_snapshot(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="v2-phase25",
            as_of=NOW,
        )
        ready = self.boundary.require_snapshot_current_for_reasoning(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            as_of=NOW,
        )
        self.assertIsInstance(ready, ReasoningReadySnapshot)
        self.assertEqual(ready.snapshot_digest, snapshot.canonical_digest)
        with self.assertRaises(TypeError):
            ReasoningReadySnapshot()
        self.assertEqual(
            ready.consume(lambda capability: capability.snapshot_id),
            snapshot.snapshot_id,
        )
        with self.assertRaises(TypeError):
            ready.__reduce__()
        with self.assertRaises(EvidenceBoundaryError):
            ready.consume(lambda capability: capability)

    def test_postgres_reasoning_gate_issues_the_same_opaque_type(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="test-durable-gate",
            as_of=NOW,
        )
        payload = json.loads(snapshot.canonical_snapshot_bytes)
        payload["canonical_authority"] = {
            "projection_version": "canonical-evidence-projection-1",
            "authority_revision": 0,
            "authority_state_digest": "0" * 64,
        }
        durable_digest = canonical_digest(payload)
        connection = RuntimeSnapshotPostgres(
            (
                payload,
                durable_digest,
                True,
                True,
                True,
                True,
                NOW,
                0,
                "0" * 64,
                7001,
                "42",
            )
        )
        gate = PostgresReasoningSnapshotGate(
            runtime_connection=connection,
            evidence_authority=self.authority,
            runtime_custody=establish_runtime_database_custody(connection),
        )
        ready = gate.require_snapshot_current_for_reasoning(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            as_of=NOW,
        )
        self.assertIsInstance(ready, ReasoningReadySnapshot)
        self.assertEqual(ready.snapshot_digest, durable_digest)
        self.assertEqual(ready.authority_revision, 0)
        self.assertEqual(
            ready.consume(lambda item: item.snapshot_id), snapshot.snapshot_id
        )
        with self.assertRaises(TypeError):
            gate.consume_snapshot_current_for_reasoning(
                snapshot=snapshot, consumer=lambda item: item.snapshot_id
            )
        query, parameters = next(
            call
            for call in connection.calls
            if "FROM investigator.case_snapshot" in call[0]
        )
        self.assertIn("transaction_isolation", query)
        self.assertEqual(parameters[:2], (self.tenant, snapshot.snapshot_id))
        self.assertTrue(
            any("pg_advisory_xact_lock_shared" in call[0] for call in connection.calls)
        )

    def test_postgres_reasoning_capability_rejects_completion_after_deadline(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="test-durable-deadline",
            as_of=NOW,
        )
        payload = json.loads(snapshot.canonical_snapshot_bytes)
        payload["canonical_authority"] = {
            "projection_version": "canonical-evidence-projection-1",
            "authority_revision": 0,
            "authority_state_digest": "0" * 64,
        }
        connection = RuntimeSnapshotPostgres(
            (
                payload,
                canonical_digest(payload),
                True,
                True,
                True,
                True,
                NOW,
                0,
                "0" * 64,
                7001,
                "42",
            )
        )
        gate = PostgresReasoningSnapshotGate(
            runtime_connection=connection,
            evidence_authority=self.authority,
            runtime_custody=establish_runtime_database_custody(connection),
        )
        ready = gate.require_snapshot_current_for_reasoning(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            as_of=NOW,
        )
        connection.final_time = NOW + timedelta(seconds=6)
        with self.assertRaisesRegex(EvidenceBoundaryError, "deadline expired"):
            ready.consume(lambda item: item.snapshot_id)
        other_connection = RuntimeSnapshotPostgres(connection.snapshot_row)
        with self.assertRaisesRegex(AuthorityDenied, "requested connection"):
            PostgresReasoningSnapshotGate(
                runtime_connection=other_connection,
                evidence_authority=self.authority,
                runtime_custody=establish_runtime_database_custody(connection),
            ).require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )

    def test_postgres_reasoning_gate_rechecks_time_based_expiry(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="durable-expiry-test",
            as_of=NOW,
        )
        payload = json.loads(snapshot.canonical_snapshot_bytes)
        payload["canonical_authority"] = {
            "projection_version": "canonical-evidence-projection-1",
            "authority_revision": 0,
            "authority_state_digest": "0" * 64,
        }
        connection = RuntimeSnapshotPostgres(
            (
                payload,
                canonical_digest(payload),
                True,
                True,
                True,
                True,
                NOW + timedelta(days=30, minutes=1),
                0,
                "0" * 64,
                7001,
                "42",
            )
        )
        gate = PostgresReasoningSnapshotGate(
            runtime_connection=connection,
            evidence_authority=self.authority,
            runtime_custody=establish_runtime_database_custody(connection),
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "no longer usable"):
            gate.require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW + timedelta(days=29, hours=23, minutes=56),
            )

    def test_empty_current_snapshot_passes_without_inventing_adverse_evidence(self):
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=1,
            actor=self.actor,
            idempotency_key="empty-v2-phase25",
            as_of=NOW,
        )
        ready = self.boundary.require_snapshot_current_for_reasoning(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            as_of=NOW,
        )
        self.assertEqual(ready.evidence_references, ())

    def test_reasoning_gate_rejects_stale_historical_and_substituted_snapshots(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="v2-stale-phase25",
            as_of=NOW,
        )
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            changed_resolution(
                self.authority.values[("evidence_passport", "bank-event-1")],
                consent_status="WITHDRAWN",
            )
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "semantic authority"):
            self.boundary.require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )
        with self.assertRaises(EvidenceBoundaryError):
            self.boundary.require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=UUID(int=999),
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )
        with self.assertRaisesRegex(EvidenceBoundaryError, "structurally current"):
            self.boundary.require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=self.initial.snapshot_id,
                as_of=NOW,
            )
        with self.assertRaises(EvidenceBoundaryError):
            self.boundary.require_snapshot_current_for_reasoning(
                tenant_id=UUID(int=2),
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )

    def test_reasoning_gate_revalidates_consent_source_and_lifecycle(self):
        self._accept()
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="v2-authority-revalidation",
            as_of=NOW,
        )
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        changes = (
            {"consent_status": "WITHDRAWN"},
            {"source_attestation_version": "2"},
            {"lifecycle": EvidenceLifecycle.REVOKED},
            {"evidence_expires_at": NOW},
        )
        for change in changes:
            with self.subTest(change=change):
                self.authority.values[("evidence_passport", "bank-event-1")] = (
                    changed_resolution(original, **change)
                )
                with self.assertRaises(EvidenceBoundaryError):
                    self.boundary.require_snapshot_current_for_reasoning(
                        tenant_id=self.tenant,
                        case_id=self.case_id,
                        snapshot_id=snapshot.snapshot_id,
                        as_of=NOW,
                    )
        self.authority.values[("evidence_passport", "bank-event-1")] = original

    def test_reasoning_gate_rejects_new_snapshot_with_unusable_authority(self):
        self._accept()
        original = self.authority.values[("evidence_passport", "bank-event-1")]
        self.authority.values[("evidence_passport", "bank-event-1")] = (
            changed_resolution(original, consent_status="WITHDRAWN")
        )
        snapshot = self.boundary.create_snapshot_v2(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=2,
            actor=self.actor,
            idempotency_key="v2-unusable-current-authority",
            as_of=NOW,
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "unusable current"):
            self.boundary.require_snapshot_current_for_reasoning(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                as_of=NOW,
            )


class PostgresCanonicalPortTests(unittest.TestCase):
    @staticmethod
    def _projection(**changes):
        value = resolution(UUID(int=1), UUID(int=10))
        row = {
            field: getattr(value, field)
            for field in PostgresCanonicalEvidenceReadPort._FIELDS
            if hasattr(value, field)
        }
        row["projection_version"] = PostgresCanonicalEvidenceReadPort.PROJECTION_VERSION
        row["authority_digest"] = value.authority_digest()
        row.update(changes)
        return row

    def test_postgres_projection_resolves_ids_without_artifact_body(self):
        connection = FakePostgres(self._projection())
        port = PostgresCanonicalEvidenceReadPort(connection, tenant_id=UUID(int=1))
        resolved = port.resolve(
            tenant_id=UUID(int=1),
            case_id=UUID(int=10),
            evidence_namespace="evidence_passport",
            evidence_id="bank-event-1",
            purpose="investigator_analysis",
            as_of=NOW,
        )
        self.assertEqual(resolved.semantic_lineage_id, "lineage-bank-event-1")
        query, parameters = next(
            call
            for call in connection.calls
            if "FROM evidence_authority.investigator_evidence_v1" in call[0]
        )
        self.assertNotIn("body", query.lower())
        self.assertEqual(parameters[:2], (UUID(int=1), UUID(int=10)))
        with self.assertRaisesRegex(EvidenceBoundaryError, "requested tenant"):
            port.resolve(
                tenant_id=UUID(int=2),
                case_id=UUID(int=10),
                evidence_namespace="evidence_passport",
                evidence_id="bank-event-1",
                purpose="investigator_analysis",
                as_of=NOW,
            )

    def test_incomplete_projection_and_sqlite_fail_closed(self):
        incomplete = self._projection()
        incomplete.pop("consent_status")
        port = PostgresCanonicalEvidenceReadPort(
            FakePostgres(incomplete), tenant_id=UUID(int=1)
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "incomplete"):
            port.resolve(
                tenant_id=UUID(int=1),
                case_id=UUID(int=10),
                evidence_namespace="evidence_passport",
                evidence_id="bank-event-1",
                purpose="investigator_analysis",
                as_of=NOW,
            )
        sqlite = sqlite3.connect(":memory:")
        try:
            with self.assertRaisesRegex(EvidenceBoundaryError, "SQLite fallback"):
                PostgresCanonicalEvidenceReadPort(sqlite, tenant_id=UUID(int=1))
        finally:
            sqlite.close()

    def test_ambiguous_projection_and_reader_custody_fail_closed(self):
        duplicated = self._projection()
        port = PostgresCanonicalEvidenceReadPort(
            FakePostgres([duplicated, duplicated]), tenant_id=UUID(int=1)
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "ambiguous"):
            port.resolve(
                tenant_id=UUID(int=1),
                case_id=UUID(int=10),
                evidence_namespace="evidence_passport",
                evidence_id="bank-event-1",
                purpose="investigator_analysis",
                as_of=NOW,
            )
        connection = FakePostgres(
            self._projection(),
            reader_custody=(True, False, False, False, False, True, True, True),
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "custody"):
            PostgresCanonicalEvidenceReadPort(connection, tenant_id=UUID(int=1))


class CredentialCustodyTests(unittest.TestCase):
    def test_runtime_identity_must_be_exclusive(self):
        safe = FakePostgres((True, True, False, False, True, True, True, True))
        assert_runtime_database_custody(safe)
        for unsafe in (
            (False, True, False, False, True, True, True, True),
            (True, True, True, False, True, True, True, True),
            (True, True, False, True, True, True, True, True),
            (True, False, False, False, True, True, True, True),
            (True, True, False, False, False, True, True, True),
            (True, True, False, False, True, False, True, True),
            (True, True, False, False, True, True, False, True),
            (True, True, False, False, True, True, True, False),
        ):
            with self.assertRaises(AuthorityDenied):
                connection = FakePostgres(unsafe)
                assert_runtime_database_custody(connection)

    def test_evidence_authority_identity_must_be_exclusive(self):
        assert_evidence_authority_database_custody(
            FakePostgres((True, True, True, True, True, True))
        )
        for unsafe in (
            (False, True, True, True, True, True),
            (True, False, True, True, True, True),
            (True, True, False, True, True, True),
            (True, True, True, False, True, True),
            (True, True, True, True, False, True),
            (True, True, True, True, True, False),
        ):
            with self.assertRaises(AuthorityDenied):
                assert_evidence_authority_database_custody(FakePostgres(unsafe))


if __name__ == "__main__":
    unittest.main()
