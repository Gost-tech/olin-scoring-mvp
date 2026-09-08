"""Deterministic Case/Event/Snapshot spine with an in-memory reference repository."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from types import MappingProxyType
from uuid import UUID, uuid4

from .actor import ActorContext, ActorContextError, ActorType
from .canonical import CANONICALIZATION_VERSION, canonical_digest, canonical_json_bytes
from .events import (
    EVENT_REGISTRY_VERSION,
    EVENT_REGISTRY_VERSION_V2,
    EventType,
    EventValidationError,
    InvestigationEvent,
)

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION_V2 = 2


class SpineConflict(RuntimeError):
    """Raised for optimistic concurrency or idempotency conflicts."""


class SpineNotFound(LookupError):
    """Raised when a tenant-bound case or snapshot is absent."""


@dataclass(frozen=True, slots=True)
class InvestigationCase:
    case_id: UUID
    tenant_id: UUID
    cohort_reference: str | None
    legacy_case_reference: str | None
    case_version: int
    created_at: datetime
    updated_at: datetime
    created_by: str


@dataclass(frozen=True, slots=True)
class CaseProjection:
    case: InvestigationCase
    event_head_sequence: int
    event_head_id: UUID
    event_head_digest: str
    case_created_actor: ActorContext
    latest_event_actor: ActorContext
    lifecycle_state: str


@dataclass(frozen=True, slots=True)
class CaseSnapshot:
    snapshot_id: UUID
    tenant_id: UUID
    case_id: UUID
    case_version: int
    event_head_sequence: int
    snapshot_schema_version: int
    canonical_snapshot_payload: MappingProxyType
    canonical_snapshot_bytes: bytes
    canonical_digest: str
    created_at: datetime
    created_by: ActorContext


@dataclass(frozen=True, slots=True)
class SnapshotInvalidation:
    tenant_id: UUID
    case_id: UUID
    snapshot_id: UUID
    invalidation_event_id: UUID
    reason_code: str
    reason_reference: str
    invalidated_at: datetime
    invalidated_by: ActorContext


def _require_actor(actor: object) -> ActorContext:
    if not isinstance(actor, ActorContext):
        raise ActorContextError("authoritative ActorContext is required")
    return actor


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _validate_reference(label: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value.strip().encode()) <= 240:
        raise ValueError(f"{label} must be null or contain 1..240 UTF-8 bytes")
    return value.strip()


def rebuild_case(
    case_record: InvestigationCase,
    ordered_events: Iterable[InvestigationEvent],
) -> CaseProjection:
    """Rebuild and validate the case projection without hidden mutable state or a clock."""
    events = tuple(ordered_events)
    if not events:
        raise EventValidationError("case event stream is empty")
    known_ids: set[UUID] = set()
    previous: InvestigationEvent | None = None
    for expected_sequence, event in enumerate(events, start=1):
        event.verify_digest()
        if (
            event.tenant_id != case_record.tenant_id
            or event.case_id != case_record.case_id
        ):
            raise EventValidationError("event tenant/case does not match case record")
        if event.sequence != expected_sequence:
            raise EventValidationError("event stream sequence is not contiguous")
        if expected_sequence == 1:
            if (
                event.event_type != EventType.CASE_CREATED.value
                or event.parent_event_id is not None
            ):
                raise EventValidationError(
                    "event stream must begin with parentless CASE_CREATED"
                )
        elif previous is None or event.parent_event_id != previous.event_id:
            raise EventValidationError(
                "event parent must be the immediately preceding event"
            )
        if expected_sequence > 1 and event.event_type == EventType.CASE_CREATED.value:
            raise EventValidationError("CASE_CREATED may appear only at sequence one")
        if (
            event.causation_event_id is not None
            and event.causation_event_id not in known_ids
        ):
            raise EventValidationError(
                "event causation must reference an earlier event"
            )
        known_ids.add(event.event_id)
        previous = event
    if case_record.case_version != len(events):
        raise EventValidationError("case version does not match event stream head")
    assert previous is not None
    return CaseProjection(
        case=case_record,
        event_head_sequence=previous.sequence,
        event_head_id=previous.event_id,
        event_head_digest=previous.event_digest,
        case_created_actor=events[0].actor,
        latest_event_actor=previous.actor,
        lifecycle_state="OPEN",
    )


def rebuild_snapshot_input(
    case_record: InvestigationCase,
    ordered_events: Iterable[InvestigationEvent],
) -> dict[str, object]:
    """Return the exact snapshot_v1 logical value for deterministic serialization."""
    events = tuple(ordered_events)
    projection = rebuild_case(case_record, events)
    case = projection.case
    return {
        "applicable_versions": {
            "canonicalization": CANONICALIZATION_VERSION,
            "event_registry": EVENT_REGISTRY_VERSION,
        },
        "audit": {
            "case_created_actor": projection.case_created_actor.audit_record(),
            "latest_event_actor": projection.latest_event_actor.audit_record(),
        },
        "case": {
            "case_id": str(case.case_id),
            "case_version": case.case_version,
            "cohort_reference": case.cohort_reference,
            "created_at": case.created_at,
            "created_by": case.created_by,
            "legacy_case_reference": case.legacy_case_reference,
            "tenant_id": str(case.tenant_id),
            "updated_at": case.updated_at,
        },
        "event_stream": {
            "head_event_digest": projection.event_head_digest,
            "head_event_id": str(projection.event_head_id),
            "head_sequence": projection.event_head_sequence,
            "stream_digest": canonical_digest([event.event_digest for event in events]),
        },
        "lifecycle": {"state": projection.lifecycle_state},
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
    }


def rebuild_snapshot_input_v2(
    case_record: InvestigationCase,
    ordered_events: Iterable[InvestigationEvent],
    *,
    evidence: dict[str, object],
) -> dict[str, object]:
    """Extend the exact v1 value with a closed reference-only evidence section."""
    payload = rebuild_snapshot_input(case_record, ordered_events)
    expected = {
        "accepted_evidence_refs",
        "unusable_evidence_refs",
        "consent_refs",
        "source_attestation_refs",
        "evidence_state_version",
        "evidence_state_digest",
    }
    if set(evidence) != expected:
        raise SpineConflict(
            "snapshot_v2 evidence fields do not match the closed schema"
        )
    if (
        not isinstance(evidence["evidence_state_version"], int)
        or evidence["evidence_state_version"] < 0
    ):
        raise SpineConflict("snapshot_v2 evidence_state_version must be non-negative")
    payload["snapshot_schema_version"] = SNAPSHOT_SCHEMA_VERSION_V2
    payload["applicable_versions"]["event_registry"] = EVENT_REGISTRY_VERSION_V2
    payload["applicable_versions"]["evidence_reference"] = (
        "investigator-evidence-reference-1"
    )
    payload["applicable_versions"]["evidence_resolver"] = (
        "investigator-evidence-resolver-1.0"
    )
    payload["evidence"] = evidence
    return payload


class InMemoryCaseSpine:
    """Thread-safe executable specification for repository and concurrency semantics."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._uuid_factory = uuid_factory
        self._lock = RLock()
        self._cases: dict[tuple[UUID, UUID], InvestigationCase] = {}
        self._events: dict[tuple[UUID, UUID], list[InvestigationEvent]] = {}
        self._event_requests: dict[
            tuple[UUID, str], tuple[tuple[object, ...], InvestigationEvent]
        ] = {}
        self._snapshots: dict[tuple[UUID, UUID], list[CaseSnapshot]] = {}
        self._snapshot_requests: dict[
            tuple[UUID, str], tuple[UUID, int, int, ActorContext, CaseSnapshot]
        ] = {}
        self._invalidations: dict[tuple[UUID, UUID], list[SnapshotInvalidation]] = {}

    def create_case(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        cohort_reference: str | None,
        legacy_case_reference: str | None,
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> InvestigationCase:
        actor = _require_actor(actor)
        actor.require_scope(tenant_id, case_id)
        if actor.actor_type not in {ActorType.BANK_SERVICE, ActorType.SYSTEM}:
            raise ActorContextError(
                "case creation requires a bank_service or system actor"
            )
        cohort_reference = _validate_reference("cohort_reference", cohort_reference)
        legacy_case_reference = _validate_reference(
            "legacy_case_reference", legacy_case_reference
        )
        with self._lock:
            key = (tenant_id, case_id)
            request = (
                case_id,
                EventType.CASE_CREATED.value,
                1,
                (),
                cohort_reference,
                legacy_case_reference,
                actor,
                None,
                None,
                occurred_at,
            )
            replay = self._event_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                if replay[0] != request:
                    raise SpineConflict(
                        "idempotency key conflicts with an existing request"
                    )
                return self._cases[key]
            if key in self._cases:
                raise SpineConflict("case already exists")
            recorded_at = self._clock()
            event = InvestigationEvent.create(
                event_id=self._uuid_factory(),
                tenant_id=tenant_id,
                case_id=case_id,
                sequence=1,
                event_type=EventType.CASE_CREATED.value,
                schema_version=1,
                payload={},
                actor=actor,
                parent_event_id=None,
                causation_event_id=None,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                recorded_at=recorded_at,
            )
            case = InvestigationCase(
                case_id=case_id,
                tenant_id=tenant_id,
                cohort_reference=cohort_reference,
                legacy_case_reference=legacy_case_reference,
                case_version=1,
                created_at=recorded_at,
                updated_at=recorded_at,
                created_by=actor.actor_reference,
            )
            self._cases[key] = case
            self._events[key] = [event]
            self._event_requests[(tenant_id, idempotency_key)] = (request, event)
            return case

    def _append_event(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        event_type: str,
        schema_version: int,
        payload: dict[str, object],
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
        parent_event_id: UUID,
        causation_event_id: UUID | None = None,
        allow_reserved_type: bool = False,
    ) -> InvestigationEvent:
        actor = _require_actor(actor)
        actor.require_scope(tenant_id, case_id)
        if actor.actor_type not in {ActorType.HUMAN, ActorType.SYSTEM}:
            raise ActorContextError("event append requires a human or system actor")
        if (
            event_type != EventType.INVESTIGATION_EVENT_RECORDED.value
            and not allow_reserved_type
        ):
            raise EventValidationError(
                "reserved event type requires its dedicated trusted command"
            )
        request = (
            case_id,
            event_type,
            schema_version,
            tuple(sorted(payload.items())),
            actor,
            parent_event_id,
            causation_event_id,
            occurred_at,
        )
        with self._lock:
            replay = self._event_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                if replay[0] != request:
                    raise SpineConflict(
                        "idempotency key conflicts with an existing request"
                    )
                return replay[1]
            key = (tenant_id, case_id)
            case = self._cases.get(key)
            if case is None:
                raise SpineNotFound("investigation case not found")
            if case.case_version != expected_case_version:
                raise SpineConflict("stale expected case version")
            stream = self._events[key]
            head = stream[-1]
            if parent_event_id != head.event_id:
                raise SpineConflict("parent event is not the current event head")
            if causation_event_id is not None and causation_event_id not in {
                item.event_id for item in stream
            }:
                raise SpineConflict("causation event is not in the prior case stream")
            recorded_at = self._clock()
            event = InvestigationEvent.create(
                event_id=self._uuid_factory(),
                tenant_id=tenant_id,
                case_id=case_id,
                sequence=case.case_version + 1,
                event_type=event_type,
                schema_version=schema_version,
                payload=payload,
                actor=actor,
                parent_event_id=parent_event_id,
                causation_event_id=causation_event_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                recorded_at=recorded_at,
            )
            stream.append(event)
            self._cases[key] = InvestigationCase(
                case_id=case.case_id,
                tenant_id=case.tenant_id,
                cohort_reference=case.cohort_reference,
                legacy_case_reference=case.legacy_case_reference,
                case_version=event.sequence,
                created_at=case.created_at,
                updated_at=recorded_at,
                created_by=case.created_by,
            )
            self._event_requests[(tenant_id, idempotency_key)] = (request, event)
            return event

    def append_event(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        event_type: str,
        schema_version: int,
        payload: dict[str, object],
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
        parent_event_id: UUID,
        causation_event_id: UUID | None = None,
    ) -> InvestigationEvent:
        """Append the Phase 0 compatibility event; reserved types use trusted commands."""
        return self._append_event(
            tenant_id=tenant_id,
            case_id=case_id,
            expected_case_version=expected_case_version,
            event_type=event_type,
            schema_version=schema_version,
            payload=payload,
            actor=actor,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            parent_event_id=parent_event_id,
            causation_event_id=causation_event_id,
        )

    def get_case(self, *, tenant_id: UUID, case_id: UUID) -> InvestigationCase:
        with self._lock:
            try:
                return self._cases[(tenant_id, case_id)]
            except KeyError as exc:
                raise SpineNotFound("investigation case not found") from exc

    def get_events(
        self, *, tenant_id: UUID, case_id: UUID
    ) -> tuple[InvestigationEvent, ...]:
        with self._lock:
            try:
                return tuple(self._events[(tenant_id, case_id)])
            except KeyError as exc:
                raise SpineNotFound("investigation case not found") from exc

    def rebuild_case(self, *, tenant_id: UUID, case_id: UUID) -> CaseProjection:
        return rebuild_case(
            self.get_case(tenant_id=tenant_id, case_id=case_id),
            self.get_events(tenant_id=tenant_id, case_id=case_id),
        )

    def rebuild_snapshot_input(
        self, *, tenant_id: UUID, case_id: UUID
    ) -> dict[str, object]:
        return rebuild_snapshot_input(
            self.get_case(tenant_id=tenant_id, case_id=case_id),
            self.get_events(tenant_id=tenant_id, case_id=case_id),
        )

    def create_snapshot(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        actor: ActorContext,
        idempotency_key: str,
    ) -> CaseSnapshot:
        actor = _require_actor(actor)
        actor.require_scope(tenant_id, case_id)
        if actor.actor_type not in {ActorType.HUMAN, ActorType.SYSTEM}:
            raise ActorContextError(
                "snapshot creation requires a human or system actor"
            )
        if (
            not isinstance(idempotency_key, str)
            or not 8 <= len(idempotency_key.strip().encode()) <= 240
        ):
            raise SpineConflict(
                "snapshot idempotency key must contain 8..240 UTF-8 bytes"
            )
        with self._lock:
            replay = self._snapshot_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                (
                    replay_case_id,
                    replay_version,
                    replay_schema,
                    replay_actor,
                    snapshot,
                ) = replay
                if (
                    replay_case_id != case_id
                    or replay_version != expected_case_version
                    or replay_schema != SNAPSHOT_SCHEMA_VERSION
                    or replay_actor != actor
                ):
                    raise SpineConflict(
                        "snapshot idempotency key conflicts with an existing request"
                    )
                return snapshot
            case = self.get_case(tenant_id=tenant_id, case_id=case_id)
            events = self.get_events(tenant_id=tenant_id, case_id=case_id)
            if case.case_version != expected_case_version:
                raise SpineConflict("stale expected case version")
            if events[-1].sequence != expected_case_version:
                raise SpineConflict(
                    "snapshot event head does not match expected case version"
                )
            payload = rebuild_snapshot_input(case, events)
            content = canonical_json_bytes(payload)
            digest = canonical_digest(payload)
            snapshots = self._snapshots.setdefault((tenant_id, case_id), [])
            existing = next(
                (
                    item
                    for item in snapshots
                    if item.event_head_sequence == expected_case_version
                    and item.snapshot_schema_version == SNAPSHOT_SCHEMA_VERSION
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.canonical_snapshot_bytes != content
                    or existing.canonical_digest != digest
                ):
                    raise SpineConflict(
                        "snapshot content conflicts at the same event head"
                    )
                snapshot = existing
            else:
                snapshot = CaseSnapshot(
                    snapshot_id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    case_id=case_id,
                    case_version=case.case_version,
                    event_head_sequence=events[-1].sequence,
                    snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                    canonical_snapshot_payload=_freeze(payload),
                    canonical_snapshot_bytes=content,
                    canonical_digest=digest,
                    created_at=self._clock(),
                    created_by=actor,
                )
                snapshots.append(snapshot)
            self._snapshot_requests[(tenant_id, idempotency_key)] = (
                case_id,
                expected_case_version,
                SNAPSHOT_SCHEMA_VERSION,
                actor,
                snapshot,
            )
            return snapshot

    def _create_snapshot_v2(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        actor: ActorContext,
        idempotency_key: str,
        evidence: dict[str, object],
    ) -> CaseSnapshot:
        """Trusted Phase 2 command used only by the evidence boundary."""
        actor = _require_actor(actor)
        actor.require_scope(tenant_id, case_id)
        if actor.actor_type not in {ActorType.HUMAN, ActorType.SYSTEM}:
            raise ActorContextError(
                "snapshot creation requires a human or system actor"
            )
        if (
            not isinstance(idempotency_key, str)
            or not 8 <= len(idempotency_key.strip().encode()) <= 240
        ):
            raise SpineConflict(
                "snapshot idempotency key must contain 8..240 UTF-8 bytes"
            )
        with self._lock:
            replay = self._snapshot_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                (
                    replay_case_id,
                    replay_version,
                    replay_schema,
                    replay_actor,
                    snapshot,
                ) = replay
                if (
                    replay_case_id != case_id
                    or replay_version != expected_case_version
                    or replay_schema != SNAPSHOT_SCHEMA_VERSION_V2
                    or replay_actor != actor
                ):
                    raise SpineConflict(
                        "snapshot idempotency key conflicts with an existing request"
                    )
                return snapshot
            case = self.get_case(tenant_id=tenant_id, case_id=case_id)
            events = self.get_events(tenant_id=tenant_id, case_id=case_id)
            if (
                case.case_version != expected_case_version
                or events[-1].sequence != expected_case_version
            ):
                raise SpineConflict(
                    "snapshot event head does not match expected case version"
                )
            payload = rebuild_snapshot_input_v2(case, events, evidence=evidence)
            content = canonical_json_bytes(payload)
            digest = canonical_digest(payload)
            snapshots = self._snapshots.setdefault((tenant_id, case_id), [])
            existing = next(
                (
                    item
                    for item in snapshots
                    if item.event_head_sequence == expected_case_version
                    and item.snapshot_schema_version == SNAPSHOT_SCHEMA_VERSION_V2
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.canonical_snapshot_bytes != content
                    or existing.canonical_digest != digest
                ):
                    raise SpineConflict(
                        "snapshot content conflicts at the same event head"
                    )
                snapshot = existing
            else:
                snapshot = CaseSnapshot(
                    snapshot_id=self._uuid_factory(),
                    tenant_id=tenant_id,
                    case_id=case_id,
                    case_version=case.case_version,
                    event_head_sequence=events[-1].sequence,
                    snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION_V2,
                    canonical_snapshot_payload=_freeze(payload),
                    canonical_snapshot_bytes=content,
                    canonical_digest=digest,
                    created_at=self._clock(),
                    created_by=actor,
                )
                snapshots.append(snapshot)
            self._snapshot_requests[(tenant_id, idempotency_key)] = (
                case_id,
                expected_case_version,
                SNAPSHOT_SCHEMA_VERSION_V2,
                actor,
                snapshot,
            )
            return snapshot

    def _record_phase2_event(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        event_type: EventType,
        payload: dict[str, object],
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> InvestigationEvent:
        """Append a closed Phase 2 event through a dedicated trusted boundary."""
        parent = self.get_events(tenant_id=tenant_id, case_id=case_id)[-1].event_id
        return self._append_event(
            tenant_id=tenant_id,
            case_id=case_id,
            expected_case_version=expected_case_version,
            event_type=event_type.value,
            schema_version=1,
            payload=payload,
            actor=actor,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            parent_event_id=parent,
            allow_reserved_type=True,
        )

    def is_snapshot_current(self, *, tenant_id: UUID, snapshot_id: UUID) -> bool:
        with self._lock:
            snapshot = self._find_snapshot(tenant_id, snapshot_id)
            case = self._cases[(tenant_id, snapshot.case_id)]
            invalidated = any(
                item.snapshot_id == snapshot_id
                for item in self._invalidations.get((tenant_id, snapshot.case_id), [])
            )
            return case.case_version == snapshot.event_head_sequence and not invalidated

    def invalidate_snapshot(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        expected_case_version: int,
        reason_code: str,
        reason_reference: str,
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> SnapshotInvalidation:
        actor = _require_actor(actor)
        actor.require_scope(tenant_id, case_id)
        if actor.actor_type not in {ActorType.HUMAN, ActorType.SYSTEM}:
            raise ActorContextError(
                "snapshot invalidation requires a human or system actor"
            )
        normalized_reason_reference = reason_reference.strip()
        requested_payload = {
            "snapshot_id": str(snapshot_id),
            "reason_code": reason_code,
            "reason_reference": normalized_reason_reference,
        }
        with self._lock:
            snapshot = self._find_snapshot(tenant_id, snapshot_id)
            if snapshot.case_id != case_id:
                raise SpineNotFound("snapshot does not belong to case")
            for item in self._invalidations.get((tenant_id, case_id), []):
                if item.snapshot_id == snapshot_id:
                    replay = self._event_requests.get((tenant_id, idempotency_key))
                    if (
                        replay is not None
                        and replay[1].event_id == item.invalidation_event_id
                        and replay[1].case_id == case_id
                        and replay[1].sequence == expected_case_version + 1
                        and replay[1].payload == requested_payload
                        and replay[1].actor == actor
                        and replay[1].occurred_at == occurred_at
                    ):
                        return item
                    raise SpineConflict("snapshot is already invalidated")
            parent = self._events[(tenant_id, case_id)][-1].event_id
            event = self._append_event(
                tenant_id=tenant_id,
                case_id=case_id,
                expected_case_version=expected_case_version,
                event_type=EventType.CASE_SNAPSHOT_INVALIDATED.value,
                schema_version=1,
                payload=requested_payload,
                actor=actor,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                parent_event_id=parent,
                allow_reserved_type=True,
            )
            invalidation = SnapshotInvalidation(
                tenant_id=tenant_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                invalidation_event_id=event.event_id,
                reason_code=reason_code,
                reason_reference=normalized_reason_reference,
                invalidated_at=event.recorded_at,
                invalidated_by=actor,
            )
            self._invalidations.setdefault((tenant_id, case_id), []).append(
                invalidation
            )
            return invalidation

    def snapshots(self, *, tenant_id: UUID, case_id: UUID) -> tuple[CaseSnapshot, ...]:
        self.get_case(tenant_id=tenant_id, case_id=case_id)
        with self._lock:
            return tuple(self._snapshots.get((tenant_id, case_id), []))

    def invalidations(
        self, *, tenant_id: UUID, case_id: UUID
    ) -> tuple[SnapshotInvalidation, ...]:
        self.get_case(tenant_id=tenant_id, case_id=case_id)
        with self._lock:
            return tuple(self._invalidations.get((tenant_id, case_id), []))

    def _find_snapshot(self, tenant_id: UUID, snapshot_id: UUID) -> CaseSnapshot:
        for (candidate_tenant, _case_id), snapshots in self._snapshots.items():
            if candidate_tenant == tenant_id:
                for snapshot in snapshots:
                    if snapshot.snapshot_id == snapshot_id:
                        return snapshot
        raise SpineNotFound("snapshot not found")
