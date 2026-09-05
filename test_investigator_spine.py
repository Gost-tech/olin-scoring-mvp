from __future__ import annotations

import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import UUID

from olin.investigator.actor import ActorContextError, controlled_test_system_actor
from olin.investigator.canonical import CanonicalizationError, canonical_json_bytes
from olin.investigator.events import EventType, EventValidationError, InvestigationEvent
from olin.investigator.spine import (
    InMemoryCaseSpine,
    InvestigationCase,
    SpineConflict,
    SpineNotFound,
    rebuild_case,
)

BASE_TIME = datetime(2026, 9, 4, 12, 30, 45, 123456, tzinfo=timezone.utc)


class DeterministicClock:
    def __init__(self, start: datetime = BASE_TIME):
        self._start = start
        self._ticks = count()

    def __call__(self) -> datetime:
        return self._start + timedelta(microseconds=next(self._ticks))


class DeterministicUUIDs:
    def __init__(self):
        self._values = count(100)

    def __call__(self) -> UUID:
        return UUID(int=next(self._values))


class InvestigatorSpineTests(unittest.TestCase):
    def setUp(self):
        self.tenant = UUID(int=1)
        self.other_tenant = UUID(int=2)
        self.case_id = UUID(int=10)
        self.clock = DeterministicClock()
        self.uuids = DeterministicUUIDs()
        self.spine = InMemoryCaseSpine(clock=self.clock, uuid_factory=self.uuids)
        self.actor = self._actor(self.tenant, "case-run", self.case_id)
        self.case = self.spine.create_case(
            tenant_id=self.tenant,
            case_id=self.case_id,
            cohort_reference="second-look-2026-09",
            legacy_case_reference=None,
            actor=self.actor,
            idempotency_key="case-create-001",
            occurred_at=BASE_TIME,
        )

    @staticmethod
    def _actor(tenant: UUID, correlation: str, case_id: UUID | None = None):
        return controlled_test_system_actor(
            tenant_id=tenant,
            case_id=case_id,
            correlation_id=correlation,
            created_at=BASE_TIME,
        )

    def _append_empty(self, *, key: str = "event-append-001"):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        return self.spine.append_event(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=head.sequence,
            event_type=EventType.INVESTIGATION_EVENT_RECORDED.value,
            schema_version=1,
            payload={},
            actor=self.actor,
            idempotency_key=key,
            occurred_at=BASE_TIME,
            parent_event_id=head.event_id,
        )

    def _snapshot(self, *, key: str = "snapshot-create-001"):
        case = self.spine.get_case(tenant_id=self.tenant, case_id=self.case_id)
        return self.spine.create_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=case.case_version,
            actor=self.actor,
            idempotency_key=key,
        )

    def test_actor_is_required_and_tenant_and_case_scope_are_enforced(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        common = {
            "tenant_id": self.tenant,
            "case_id": self.case_id,
            "expected_case_version": 1,
            "event_type": EventType.INVESTIGATION_EVENT_RECORDED.value,
            "schema_version": 1,
            "payload": {},
            "idempotency_key": "actor-check-001",
            "occurred_at": BASE_TIME,
            "parent_event_id": head.event_id,
        }
        with self.assertRaises(ActorContextError):
            self.spine.append_event(actor=None, **common)
        with self.assertRaises(ActorContextError):
            self.spine.append_event(
                actor=self._actor(self.other_tenant, "wrong-tenant", self.case_id),
                **common,
            )
        with self.assertRaises(ActorContextError):
            self.spine.append_event(
                actor=self._actor(self.tenant, "wrong-case", UUID(int=999)), **common
            )

    def test_payload_actor_aliases_cannot_override_actor_context(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        for index, field in enumerate(
            ("actor", "user", "admin", "reviewer", "workload", "principal")
        ):
            with self.subTest(field=field), self.assertRaises(EventValidationError):
                self.spine.append_event(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    expected_case_version=1,
                    event_type=EventType.INVESTIGATION_EVENT_RECORDED.value,
                    schema_version=1,
                    payload={field: "forged"},
                    actor=self.actor,
                    idempotency_key=f"forged-actor-{index}",
                    occurred_at=BASE_TIME,
                    parent_event_id=head.event_id,
                )

    def test_actor_audit_reference_is_preserved_in_event_and_snapshot(self):
        event = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[0]
        self.assertEqual(event.actor.actor_reference, "controlled-test-system")
        self.assertEqual(event.actor.authentication_reference, "local-test-fixture")
        self.assertEqual(event.actor.authorization_source, "controlled-test-factory")
        snapshot = self._snapshot()
        audit = snapshot.canonical_snapshot_payload["audit"]["case_created_actor"]
        self.assertEqual(audit["authentication_reference"], "local-test-fixture")
        self.assertEqual(audit["correlation_id"], "case-run")

    def test_unknown_event_type_field_and_schema_version_fail_closed(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        attempts = (
            ("FUTURE_EVENT", 1, {}),
            (EventType.INVESTIGATION_EVENT_RECORDED.value, 2, {}),
            (EventType.INVESTIGATION_EVENT_RECORDED.value, 1, {"extra": None}),
        )
        for index, (event_type, version, payload) in enumerate(attempts):
            with self.subTest(index=index), self.assertRaises(EventValidationError):
                self.spine.append_event(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    expected_case_version=1,
                    event_type=event_type,
                    schema_version=version,
                    payload=payload,
                    actor=self.actor,
                    idempotency_key=f"invalid-event-{index}",
                    occurred_at=BASE_TIME,
                    parent_event_id=head.event_id,
                )

    def test_reserved_event_types_require_dedicated_commands(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        for index, event_type in enumerate(
            (EventType.CASE_CREATED.value, EventType.CASE_SNAPSHOT_INVALIDATED.value)
        ):
            with (
                self.subTest(event_type=event_type),
                self.assertRaises(EventValidationError),
            ):
                self.spine.append_event(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    expected_case_version=1,
                    event_type=event_type,
                    schema_version=1,
                    payload={},
                    actor=self.actor,
                    idempotency_key=f"reserved-event-{index}",
                    occurred_at=BASE_TIME,
                    parent_event_id=head.event_id,
                )

    def test_idempotent_event_replay_and_conflicting_reuse(self):
        first = self._append_empty()
        replay = self.spine.append_event(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=1,
            event_type=EventType.INVESTIGATION_EVENT_RECORDED.value,
            schema_version=1,
            payload={},
            actor=self.actor,
            idempotency_key="event-append-001",
            occurred_at=BASE_TIME,
            parent_event_id=self.spine.get_events(
                tenant_id=self.tenant, case_id=self.case_id
            )[0].event_id,
        )
        self.assertIs(first, replay)
        self.assertEqual(
            len(self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)), 2
        )
        with self.assertRaises(SpineConflict):
            self.spine.append_event(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=2,
                event_type=EventType.INVESTIGATION_EVENT_RECORDED.value,
                schema_version=1,
                payload={},
                actor=self.actor,
                idempotency_key="event-append-001",
                occurred_at=BASE_TIME + timedelta(seconds=1),
                parent_event_id=first.event_id,
            )

    def test_version_parent_and_causation_conflicts_fail(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]
        common = {
            "tenant_id": self.tenant,
            "case_id": self.case_id,
            "event_type": EventType.INVESTIGATION_EVENT_RECORDED.value,
            "schema_version": 1,
            "payload": {},
            "actor": self.actor,
            "occurred_at": BASE_TIME,
        }
        with self.assertRaises(SpineConflict):
            self.spine.append_event(
                expected_case_version=0,
                idempotency_key="stale-version-001",
                parent_event_id=head.event_id,
                **common,
            )
        with self.assertRaises(SpineConflict):
            self.spine.append_event(
                expected_case_version=1,
                idempotency_key="parent-order-001",
                parent_event_id=UUID(int=404),
                **common,
            )
        with self.assertRaises(SpineConflict):
            self.spine.append_event(
                expected_case_version=1,
                idempotency_key="invalid-cause-001",
                parent_event_id=head.event_id,
                causation_event_id=UUID(int=405),
                **common,
            )

    def test_rebuild_rejects_out_of_order_stream_and_version_mismatch(self):
        second = self._append_empty()
        events = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)
        with self.assertRaises(EventValidationError):
            rebuild_case(
                self.spine.get_case(tenant_id=self.tenant, case_id=self.case_id),
                reversed(events),
            )
        wrong_version = InvestigationCase(
            case_id=self.case_id,
            tenant_id=self.tenant,
            cohort_reference=self.case.cohort_reference,
            legacy_case_reference=None,
            case_version=99,
            created_at=self.case.created_at,
            updated_at=second.recorded_at,
            created_by=self.case.created_by,
        )
        with self.assertRaises(EventValidationError):
            rebuild_case(wrong_version, events)

    def test_snapshot_bytes_digest_and_schema_are_deterministic(self):
        first = self._snapshot()
        replay = self._snapshot()
        self.assertIs(first, replay)
        self.assertEqual(
            first.canonical_snapshot_bytes,
            canonical_json_bytes(dict(first.canonical_snapshot_payload)),
        )
        self.assertEqual(len(first.canonical_digest), 64)
        self.assertEqual(
            set(first.canonical_snapshot_payload),
            {
                "applicable_versions",
                "audit",
                "case",
                "event_stream",
                "lifecycle",
                "snapshot_schema_version",
            },
        )
        self.assertIsNone(
            first.canonical_snapshot_payload["case"]["legacy_case_reference"]
        )
        self.assertEqual(
            len(first.canonical_snapshot_payload["event_stream"]["stream_digest"]),
            64,
        )

        clone = InMemoryCaseSpine(
            clock=DeterministicClock(), uuid_factory=DeterministicUUIDs()
        )
        clone_actor = self._actor(self.tenant, "case-run", self.case_id)
        clone.create_case(
            tenant_id=self.tenant,
            case_id=self.case_id,
            cohort_reference="second-look-2026-09",
            legacy_case_reference=None,
            actor=clone_actor,
            idempotency_key="case-create-001",
            occurred_at=BASE_TIME,
        )
        clone_snapshot = clone.create_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            expected_case_version=1,
            actor=clone_actor,
            idempotency_key="different-request-key",
        )
        self.assertEqual(
            first.canonical_snapshot_bytes, clone_snapshot.canonical_snapshot_bytes
        )
        self.assertEqual(first.canonical_digest, clone_snapshot.canonical_digest)

    def test_snapshot_payload_and_records_are_immutable(self):
        snapshot = self._snapshot()
        with self.assertRaises(TypeError):
            snapshot.canonical_snapshot_payload["case"]["case_version"] = 7
        with self.assertRaises((AttributeError, TypeError)):
            snapshot.canonical_digest = "0" * 64

    def test_event_advance_creates_new_snapshot_and_preserves_stale_old_snapshot(self):
        old = self._snapshot()
        self.assertTrue(
            self.spine.is_snapshot_current(
                tenant_id=self.tenant, snapshot_id=old.snapshot_id
            )
        )
        self._append_empty()
        self.assertFalse(
            self.spine.is_snapshot_current(
                tenant_id=self.tenant, snapshot_id=old.snapshot_id
            )
        )
        new = self._snapshot(key="snapshot-create-002")
        self.assertNotEqual(old.canonical_digest, new.canonical_digest)
        self.assertEqual(
            len(self.spine.snapshots(tenant_id=self.tenant, case_id=self.case_id)), 2
        )
        self.assertEqual(
            self.spine.snapshots(tenant_id=self.tenant, case_id=self.case_id)[0], old
        )

    def test_integrity_invalidation_is_append_only_and_audited(self):
        snapshot = self._snapshot()
        original_bytes = snapshot.canonical_snapshot_bytes
        invalidation = self.spine.invalidate_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            expected_case_version=1,
            reason_code="DIGEST_MISMATCH",
            reason_reference="integrity-review-42",
            actor=self.actor,
            idempotency_key="snapshot-invalidate-001",
            occurred_at=BASE_TIME,
        )
        self.assertFalse(
            self.spine.is_snapshot_current(
                tenant_id=self.tenant, snapshot_id=snapshot.snapshot_id
            )
        )
        self.assertEqual(snapshot.canonical_snapshot_bytes, original_bytes)
        self.assertEqual(
            invalidation.invalidated_by.authentication_reference, "local-test-fixture"
        )
        events = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)
        self.assertEqual(
            events[-1].event_type, EventType.CASE_SNAPSHOT_INVALIDATED.value
        )
        replay = self.spine.invalidate_snapshot(
            tenant_id=self.tenant,
            case_id=self.case_id,
            snapshot_id=snapshot.snapshot_id,
            expected_case_version=1,
            reason_code="DIGEST_MISMATCH",
            reason_reference="integrity-review-42",
            actor=self.actor,
            idempotency_key="snapshot-invalidate-001",
            occurred_at=BASE_TIME,
        )
        self.assertIs(replay, invalidation)
        with self.assertRaises(SpineConflict):
            self.spine.invalidate_snapshot(
                tenant_id=self.tenant,
                case_id=self.case_id,
                snapshot_id=snapshot.snapshot_id,
                expected_case_version=1,
                reason_code="PROVENANCE_FAILURE",
                reason_reference="integrity-review-42",
                actor=self.actor,
                idempotency_key="snapshot-invalidate-001",
                occurred_at=BASE_TIME,
            )

    def test_cross_tenant_snapshot_read_and_create_are_denied(self):
        snapshot = self._snapshot()
        with self.assertRaises(SpineNotFound):
            self.spine.is_snapshot_current(
                tenant_id=self.other_tenant, snapshot_id=snapshot.snapshot_id
            )
        with self.assertRaises(ActorContextError):
            self.spine.create_snapshot(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=1,
                actor=self._actor(self.other_tenant, "forged", self.case_id),
                idempotency_key="forged-snapshot-001",
            )

    def test_snapshot_head_mismatch_is_rejected(self):
        with self.assertRaises(SpineConflict):
            self.spine.create_snapshot(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=2,
                actor=self.actor,
                idempotency_key="head-mismatch-001",
            )

    def test_two_snapshot_writers_converge(self):
        def create(key: str):
            return self.spine.create_snapshot(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=1,
                actor=self.actor,
                idempotency_key=key,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            snapshots = list(executor.map(create, ("writer-one-001", "writer-two-001")))
        self.assertEqual(snapshots[0].snapshot_id, snapshots[1].snapshot_id)
        self.assertEqual(
            len(self.spine.snapshots(tenant_id=self.tenant, case_id=self.case_id)), 1
        )
        replay_key = "snapshot-actor-binding-001"
        self._snapshot(key=replay_key)
        different_actor = self._actor(self.tenant, "different-reviewer", self.case_id)
        with self.assertRaises(SpineConflict):
            self.spine.create_snapshot(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=1,
                actor=different_actor,
                idempotency_key=replay_key,
            )

    def test_two_event_writers_have_no_lost_update(self):
        head = self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)[-1]

        def append(key: str):
            return self.spine.append_event(
                tenant_id=self.tenant,
                case_id=self.case_id,
                expected_case_version=1,
                event_type=EventType.INVESTIGATION_EVENT_RECORDED.value,
                schema_version=1,
                payload={},
                actor=self.actor,
                idempotency_key=key,
                occurred_at=BASE_TIME,
                parent_event_id=head.event_id,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    lambda key: self._capture(append, key),
                    ("writer-a-001", "writer-b-001"),
                )
            )
        self.assertEqual(
            sum(isinstance(item, InvestigationEvent) for item in outcomes), 1
        )
        self.assertEqual(sum(isinstance(item, SpineConflict) for item in outcomes), 1)
        self.assertEqual(
            len(self.spine.get_events(tenant_id=self.tenant, case_id=self.case_id)), 2
        )

    @staticmethod
    def _capture(operation, key):
        try:
            return operation(key)
        except SpineConflict as exc:
            return exc

    def test_canonicalizer_rejects_floats_and_preserves_explicit_null(self):
        self.assertEqual(canonical_json_bytes({"a": None, "b": 1}), b'{"a":null,"b":1}')
        with self.assertRaises(CanonicalizationError):
            canonical_json_bytes({"amount": 0.1})

    def test_case_domain_has_no_credit_or_money_fields(self):
        forbidden = {
            "approved_amount",
            "score",
            "tier",
            "price",
            "interest_rate",
            "authoritative_terms",
            "disbursement_status",
        }
        self.assertFalse(forbidden & set(InvestigationCase.__dataclass_fields__))

    def test_snapshot_is_independent_of_mutated_input_copy(self):
        snapshot = self._snapshot()
        copied = copy.deepcopy(dict(snapshot.canonical_snapshot_payload["case"]))
        copied["cohort_reference"] = "tampered"
        self.assertEqual(
            snapshot.canonical_snapshot_payload["case"]["cohort_reference"],
            "second-look-2026-09",
        )


if __name__ == "__main__":
    unittest.main()
