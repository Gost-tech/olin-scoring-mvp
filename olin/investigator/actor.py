"""Server-authoritative actor provenance for Investigator commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from .canonical import normalize_timestamp


class ActorContextError(PermissionError):
    """Raised when trusted actor provenance is absent or scope-invalid."""


class ActorType(str, Enum):
    BANK_SERVICE = "bank_service"
    HUMAN = "human"
    SYSTEM = "system"


def _bounded(label: str, value: str, *, minimum: int = 1, maximum: int = 240) -> str:
    if (
        not isinstance(value, str)
        or not minimum <= len(value.strip().encode()) <= maximum
    ):
        raise ActorContextError(
            f"{label} must contain {minimum}..{maximum} UTF-8 bytes"
        )
    return value.strip()


@dataclass(frozen=True, slots=True, init=False)
class ActorContext:
    """Resolved identity and authorization facts, separate from command payloads.

    Construction is intentionally private. A production resolver must later bind
    authenticated claims to this type. Phase 1 exposes only a conspicuous local/test
    system factory and therefore does not pretend to authenticate production users.
    """

    actor_type: ActorType
    actor_reference: str
    tenant_id: UUID
    case_id: UUID | None
    authentication_reference: str
    authorization_source: str
    correlation_id: str
    created_at: datetime

    @classmethod
    def _from_trusted_resolution(
        cls,
        *,
        actor_type: ActorType,
        actor_reference: str,
        tenant_id: UUID,
        case_id: UUID | None,
        authentication_reference: str,
        authorization_source: str,
        correlation_id: str,
        created_at: datetime,
    ) -> ActorContext:
        instance = object.__new__(cls)
        object.__setattr__(instance, "actor_type", ActorType(actor_type))
        object.__setattr__(
            instance, "actor_reference", _bounded("actor_reference", actor_reference)
        )
        if not isinstance(tenant_id, UUID):
            raise ActorContextError("tenant_id must be a UUID")
        if case_id is not None and not isinstance(case_id, UUID):
            raise ActorContextError("case_id must be a UUID or null")
        object.__setattr__(instance, "tenant_id", tenant_id)
        object.__setattr__(instance, "case_id", case_id)
        object.__setattr__(
            instance,
            "authentication_reference",
            _bounded("authentication_reference", authentication_reference),
        )
        object.__setattr__(
            instance,
            "authorization_source",
            _bounded("authorization_source", authorization_source),
        )
        object.__setattr__(
            instance, "correlation_id", _bounded("correlation_id", correlation_id)
        )
        normalize_timestamp(created_at)
        object.__setattr__(instance, "created_at", created_at)
        return instance

    def require_scope(self, tenant_id: UUID, case_id: UUID | None = None) -> None:
        if self.tenant_id != tenant_id:
            raise ActorContextError("actor tenant scope does not match command tenant")
        if self.case_id is not None and self.case_id != case_id:
            raise ActorContextError("actor case scope does not match command case")

    def audit_record(self) -> dict[str, object]:
        """Return the exact non-secret provenance persisted in event/snapshot history."""
        return {
            "actor_type": self.actor_type.value,
            "actor_reference": self.actor_reference,
            "tenant_id": str(self.tenant_id),
            "case_id": str(self.case_id) if self.case_id is not None else None,
            "authentication_reference": self.authentication_reference,
            "authorization_source": self.authorization_source,
            "correlation_id": self.correlation_id,
            "created_at": normalize_timestamp(self.created_at),
        }


def controlled_test_system_actor(
    *,
    tenant_id: UUID,
    correlation_id: str,
    created_at: datetime,
    case_id: UUID | None = None,
) -> ActorContext:
    """Create an unmistakably non-production actor for local and test execution."""
    return ActorContext._from_trusted_resolution(
        actor_type=ActorType.SYSTEM,
        actor_reference="controlled-test-system",
        tenant_id=tenant_id,
        case_id=case_id,
        authentication_reference="local-test-fixture",
        authorization_source="controlled-test-factory",
        correlation_id=correlation_id,
        created_at=created_at,
    )
