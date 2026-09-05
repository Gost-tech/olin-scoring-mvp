"""Closed, versioned Investigator event registry and immutable envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from .actor import ActorContext
from .canonical import canonical_digest, normalize_timestamp

EVENT_REGISTRY_VERSION = "investigator-events-1.0"
AUTHORITATIVE_PAYLOAD_FIELDS = frozenset(
    {"actor", "user", "admin", "reviewer", "workload", "principal"}
)


class EventValidationError(ValueError):
    """Raised when an event is unknown, unsupported, or not schema-exact."""


class EventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    INVESTIGATION_EVENT_RECORDED = "INVESTIGATION_EVENT_RECORDED"
    CASE_SNAPSHOT_INVALIDATED = "CASE_SNAPSHOT_INVALIDATED"


class SnapshotInvalidationReason(str, Enum):
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    EVENT_STREAM_CORRUPTION = "EVENT_STREAM_CORRUPTION"
    CANONICALIZATION_FAILURE = "CANONICALIZATION_FAILURE"
    PROVENANCE_FAILURE = "PROVENANCE_FAILURE"


@dataclass(frozen=True, slots=True)
class EventDefinition:
    event_type: EventType
    schema_version: int
    required_fields: frozenset[str]

    def validate(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise EventValidationError("event payload must be an object")
        fields = set(payload)
        if fields & AUTHORITATIVE_PAYLOAD_FIELDS:
            raise EventValidationError(
                "actor identity fields are forbidden in event payloads"
            )
        if fields != set(self.required_fields):
            unknown = sorted(fields - self.required_fields)
            missing = sorted(self.required_fields - fields)
            raise EventValidationError(
                f"payload fields do not match schema; unknown={unknown}, missing={missing}"
            )
        if self.event_type is EventType.CASE_SNAPSHOT_INVALIDATED:
            try:
                UUID(str(payload["snapshot_id"]))
                SnapshotInvalidationReason(payload["reason_code"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EventValidationError(
                    "snapshot invalidation payload is invalid"
                ) from exc
            reference = payload["reason_reference"]
            if (
                not isinstance(reference, str)
                or not 1 <= len(reference.strip().encode()) <= 240
            ):
                raise EventValidationError(
                    "reason_reference must contain 1..240 UTF-8 bytes"
                )


_REGISTRY = MappingProxyType(
    {
        (EventType.CASE_CREATED.value, 1): EventDefinition(
            EventType.CASE_CREATED, 1, frozenset()
        ),
        (EventType.INVESTIGATION_EVENT_RECORDED.value, 1): EventDefinition(
            EventType.INVESTIGATION_EVENT_RECORDED, 1, frozenset()
        ),
        (EventType.CASE_SNAPSHOT_INVALIDATED.value, 1): EventDefinition(
            EventType.CASE_SNAPSHOT_INVALIDATED,
            1,
            frozenset({"snapshot_id", "reason_code", "reason_reference"}),
        ),
    }
)


def validate_event_payload(
    event_type: str, schema_version: int, payload: dict[str, Any]
) -> None:
    definition = _REGISTRY.get((event_type, schema_version))
    if definition is None:
        known_type = any(key[0] == event_type for key in _REGISTRY)
        if known_type:
            raise EventValidationError("unsupported event schema version")
        raise EventValidationError("unknown event type")
    definition.validate(payload)


@dataclass(frozen=True, slots=True)
class InvestigationEvent:
    event_id: UUID
    tenant_id: UUID
    case_id: UUID
    sequence: int
    event_type: str
    schema_version: int
    payload: MappingProxyType
    actor: ActorContext
    parent_event_id: UUID | None
    causation_event_id: UUID | None
    idempotency_key: str
    occurred_at: datetime
    recorded_at: datetime
    event_digest: str

    @classmethod
    def create(
        cls,
        *,
        event_id: UUID,
        tenant_id: UUID,
        case_id: UUID,
        sequence: int,
        event_type: str,
        schema_version: int,
        payload: dict[str, Any],
        actor: ActorContext,
        parent_event_id: UUID | None,
        causation_event_id: UUID | None,
        idempotency_key: str,
        occurred_at: datetime,
        recorded_at: datetime,
    ) -> InvestigationEvent:
        if not isinstance(actor, ActorContext):
            raise EventValidationError("authoritative ActorContext is required")
        actor.require_scope(tenant_id, case_id)
        validate_event_payload(event_type, schema_version, payload)
        if sequence < 1:
            raise EventValidationError("event sequence must be positive")
        if (
            not isinstance(idempotency_key, str)
            or not 8 <= len(idempotency_key.strip().encode()) <= 240
        ):
            raise EventValidationError(
                "idempotency key must contain 8..240 UTF-8 bytes"
            )
        envelope = {
            "actor": actor.audit_record(),
            "case_id": str(case_id),
            "causation_event_id": str(causation_event_id)
            if causation_event_id
            else None,
            "event_id": str(event_id),
            "event_type": event_type,
            "idempotency_key": idempotency_key.strip(),
            "occurred_at": normalize_timestamp(occurred_at),
            "parent_event_id": str(parent_event_id) if parent_event_id else None,
            "payload": payload,
            "recorded_at": normalize_timestamp(recorded_at),
            "schema_version": schema_version,
            "sequence": sequence,
            "tenant_id": str(tenant_id),
        }
        return cls(
            event_id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            sequence=sequence,
            event_type=event_type,
            schema_version=schema_version,
            payload=MappingProxyType(dict(payload)),
            actor=actor,
            parent_event_id=parent_event_id,
            causation_event_id=causation_event_id,
            idempotency_key=idempotency_key.strip(),
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            event_digest=canonical_digest(envelope),
        )

    def verify_digest(self) -> None:
        rebuilt = InvestigationEvent.create(
            event_id=self.event_id,
            tenant_id=self.tenant_id,
            case_id=self.case_id,
            sequence=self.sequence,
            event_type=self.event_type,
            schema_version=self.schema_version,
            payload=dict(self.payload),
            actor=self.actor,
            parent_event_id=self.parent_event_id,
            causation_event_id=self.causation_event_id,
            idempotency_key=self.idempotency_key,
            occurred_at=self.occurred_at,
            recorded_at=self.recorded_at,
        )
        if rebuilt.event_digest != self.event_digest:
            raise EventValidationError("event digest mismatch")
