"""Evidence/consent reference boundary for Investigator snapshot schema v2.

This module stores no artifact bodies and grants no trust.  A separately
authorized adapter resolves canonical Evidence Passport, consent, subject, and
source-attestation state into :class:`EvidenceAuthorityResolution`.  The
Investigator can only retain the resulting immutable references and must
re-resolve them before a snapshot is used for reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from .canonical import canonical_digest, canonical_json_bytes, normalize_timestamp

EVIDENCE_REFERENCE_SCHEMA_VERSION = 1
EVIDENCE_RESOLVER_CONTRACT_VERSION = "investigator-evidence-resolver-1.0"
MAX_AUTHORITY_RECORD_BYTES = 16_384
INVESTIGATOR_ANALYTICAL_USE_SCOPE = "case_evidence_analysis"
MAX_EVIDENCE_CLOCK_SKEW = timedelta(minutes=5)
CALLER_TRUST_LABELS = frozenset(
    {
        "verified",
        "trusted",
        "authoritative",
        "issuer_validated",
        "source_verified",
        "official",
        "validated",
    }
)


class EvidenceBoundaryError(ValueError):
    """Raised when canonical evidence cannot cross the Investigator boundary."""


class EvidenceClass(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    EXTERNAL_EVIDENCE = "EXTERNAL_EVIDENCE"
    MERCHANT_SUPPLIED_ARTIFACT = "MERCHANT_SUPPLIED_ARTIFACT"
    EXPERIMENTAL_OBSERVATION = "EXPERIMENTAL_OBSERVATION"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED_FOR_PROPOSITION = "VERIFIED_FOR_PROPOSITION"


class EvidenceUsability(str, Enum):
    USABLE = "USABLE"
    UNUSABLE = "UNUSABLE"


class EvidenceLifecycle(str, Enum):
    RECEIVED = "RECEIVED"
    QUARANTINED = "QUARANTINED"
    ACCEPTED = "ACCEPTED"
    DISPUTED = "DISPUTED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class UnusableReason(str, Enum):
    CONSENT_MISSING = "CONSENT_MISSING"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    CONSENT_EXPIRED = "CONSENT_EXPIRED"
    CONSENT_OUT_OF_SCOPE = "CONSENT_OUT_OF_SCOPE"
    EVIDENCE_QUARANTINED = "EVIDENCE_QUARANTINED"
    EVIDENCE_DISPUTED = "EVIDENCE_DISPUTED"
    EVIDENCE_SUPERSEDED = "EVIDENCE_SUPERSEDED"
    EVIDENCE_REVOKED = "EVIDENCE_REVOKED"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    EVIDENCE_NOT_YET_OBSERVED = "EVIDENCE_NOT_YET_OBSERVED"
    SOURCE_NOT_TRUSTED = "SOURCE_NOT_TRUSTED"
    SOURCE_ATTESTATION_CHANGED = "SOURCE_ATTESTATION_CHANGED"
    SOURCE_ATTESTATION_EXPIRED = "SOURCE_ATTESTATION_EXPIRED"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    CASE_MISMATCH = "CASE_MISMATCH"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    AUTHORITY_REFERENCE_CHANGED = "AUTHORITY_REFERENCE_CHANGED"


def _bounded(label: str, value: object, maximum: int = 240) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip().encode()) <= maximum:
        raise EvidenceBoundaryError(f"{label} must contain 1..{maximum} UTF-8 bytes")
    return value.strip()


def _digest(label: str, value: str) -> str:
    value = _bounded(label, value, 64).lower()
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise EvidenceBoundaryError(f"{label} must be a SHA-256 hex digest")
    return value


@dataclass(frozen=True, slots=True, init=False)
class EvidenceAuthorityResolution:
    """Server-derived canonical state; construction belongs to authority adapters.

    It deliberately has no document-level ``trusted`` or ``verified`` boolean.
    Verification is constrained to one named proposition and its exact subject,
    period, value, unit, issuer, method, and attestation.
    """

    tenant_id: UUID
    case_id: UUID
    subject_id: str
    subject_digest: str
    evidence_namespace: str
    evidence_id: str
    evidence_version: str
    artifact_digest: str
    evidence_class: EvidenceClass
    lifecycle: EvidenceLifecycle
    verification_status: VerificationStatus
    proposition_type: str | None
    proposition_schema_version: int | None
    proposition_value: str | None
    proposition_unit: str | None
    verification_method: str | None
    period_start: datetime | None
    period_end: datetime | None
    observed_at: datetime
    evidence_expires_at: datetime | None
    source_id: str
    issuer_id: str
    acquisition_method: str
    source_class: str
    source_attestation_id: str
    source_attestation_version: str
    source_registry_digest: str
    source_valid_until: datetime
    production_qualified_source: bool
    source_allows_proposition: bool
    consent_namespace: str
    consent_id: str
    consent_version: str
    consent_purpose: str
    consent_data_class: str
    consent_use_scope: str
    consent_status: str
    consent_expires_at: datetime
    retention_until: datetime
    integrity_reference: str
    integrity_valid: bool
    usability: EvidenceUsability
    unusable_reason: UnusableReason | None
    resolver_version: str
    resolved_at: datetime

    @classmethod
    def _from_authoritative_adapter(
        cls, **values: object
    ) -> EvidenceAuthorityResolution:
        """Construct after a privileged canonical adapter has resolved all fields."""
        instance = object.__new__(cls)
        enum_fields = {
            "evidence_class": EvidenceClass,
            "lifecycle": EvidenceLifecycle,
            "verification_status": VerificationStatus,
            "usability": EvidenceUsability,
            "unusable_reason": UnusableReason,
        }
        for field_name in cls.__dataclass_fields__:
            if field_name not in values:
                raise EvidenceBoundaryError(
                    f"authority resolution missing {field_name}"
                )
            value = values[field_name]
            enum_type = enum_fields.get(field_name)
            if enum_type is not None and value is not None:
                value = enum_type(value)
            object.__setattr__(instance, field_name, value)
        instance._validate()
        return instance

    def _validate(self) -> None:
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.case_id, UUID):
            raise EvidenceBoundaryError(
                "authority resolution tenant/case must be UUIDs"
            )
        for field_name in (
            "subject_id",
            "evidence_namespace",
            "evidence_id",
            "evidence_version",
            "source_id",
            "issuer_id",
            "acquisition_method",
            "source_class",
            "source_attestation_id",
            "source_attestation_version",
            "consent_namespace",
            "consent_id",
            "consent_version",
            "consent_purpose",
            "consent_data_class",
            "consent_use_scope",
            "consent_status",
            "resolver_version",
            "integrity_reference",
        ):
            _bounded(field_name, getattr(self, field_name))
        for field_name in (
            "production_qualified_source",
            "source_allows_proposition",
            "integrity_valid",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise EvidenceBoundaryError(
                    f"{field_name} must be server-derived boolean"
                )
        _digest("subject_digest", self.subject_digest)
        _digest("artifact_digest", self.artifact_digest)
        _digest("source_registry_digest", self.source_registry_digest)
        EvidenceClass(self.evidence_class)
        EvidenceLifecycle(self.lifecycle)
        VerificationStatus(self.verification_status)
        EvidenceUsability(self.usability)
        if self.unusable_reason is not None:
            UnusableReason(self.unusable_reason)
        for field_name in (
            "observed_at",
            "source_valid_until",
            "consent_expires_at",
            "retention_until",
            "resolved_at",
        ):
            normalize_timestamp(getattr(self, field_name))
        for optional_time in ("period_start", "period_end", "evidence_expires_at"):
            value = getattr(self, optional_time)
            if value is not None:
                normalize_timestamp(value)
        if self.resolver_version != EVIDENCE_RESOLVER_CONTRACT_VERSION:
            raise EvidenceBoundaryError("unsupported evidence resolver version")
        if self.consent_status not in {
            "ACTIVE",
            "WITHDRAWN",
            "EXPIRED",
            "SUPERSEDED",
        }:
            raise EvidenceBoundaryError("canonical consent status is unknown")
        authority_identity = (
            f"{self.source_id} {self.issuer_id} {self.source_class} "
            f"{self.source_attestation_id}"
        ).lower()
        if self.production_qualified_source and any(
            marker in authority_identity
            for marker in ("example", "placeholder", "synthetic", "demo")
        ):
            raise EvidenceBoundaryError(
                "example or placeholder source cannot be production qualified"
            )
        if self.proposition_type == "*":
            raise EvidenceBoundaryError(
                "wildcard proposition verification is forbidden"
            )
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_start > self.period_end
        ):
            raise EvidenceBoundaryError("evidence period is inverted")
        if self.lifecycle is EvidenceLifecycle.RECEIVED:
            raise EvidenceBoundaryError(
                "received evidence must be accepted or quarantined"
            )
        if (
            self.usability is EvidenceUsability.USABLE
            and self.unusable_reason is not None
        ):
            raise EvidenceBoundaryError(
                "usable evidence cannot carry an unusable reason"
            )
        if (
            self.usability is EvidenceUsability.UNUSABLE
            and self.unusable_reason is None
        ):
            raise EvidenceBoundaryError("unusable evidence requires a closed reason")
        if self.verification_status is VerificationStatus.VERIFIED_FOR_PROPOSITION:
            required = (
                self.proposition_type,
                self.proposition_value,
                self.proposition_unit,
                self.verification_method,
            )
            if not all(isinstance(value, str) and value.strip() for value in required):
                raise EvidenceBoundaryError(
                    "proposition verification requires type, value, and unit"
                )
            if (
                not isinstance(self.proposition_schema_version, int)
                or self.proposition_schema_version < 1
            ):
                raise EvidenceBoundaryError(
                    "verified proposition schema version is invalid"
                )
            for field_name, maximum in (
                ("proposition_type", 120),
                ("proposition_value", 512),
                ("proposition_unit", 64),
                ("verification_method", 160),
            ):
                _bounded(field_name, getattr(self, field_name), maximum)
            if self.period_start is None or self.period_end is None:
                raise EvidenceBoundaryError(
                    "verified proposition requires an explicit coverage period"
                )
            if self.evidence_class is not EvidenceClass.VERIFIED_FACT:
                raise EvidenceBoundaryError(
                    "only VERIFIED_FACT may be VERIFIED_FOR_PROPOSITION"
                )
            if self.evidence_expires_at is None:
                raise EvidenceBoundaryError(
                    "verified proposition requires an authoritative freshness limit"
                )
        elif self.evidence_class is EvidenceClass.VERIFIED_FACT:
            raise EvidenceBoundaryError(
                "VERIFIED_FACT requires VERIFIED_FOR_PROPOSITION status"
            )
        if (
            len(canonical_json_bytes(self.authority_record()))
            > MAX_AUTHORITY_RECORD_BYTES
        ):
            raise EvidenceBoundaryError("authority resolution exceeds the size limit")

    def authority_record(self) -> dict[str, object]:
        """Return every field whose semantic change must stale a reference."""
        return {
            "artifact": {
                "artifact_digest": self.artifact_digest,
                "evidence_class": self.evidence_class.value,
                "evidence_id": self.evidence_id,
                "evidence_namespace": self.evidence_namespace,
                "evidence_version": self.evidence_version,
                "expires_at": normalize_timestamp(self.evidence_expires_at)
                if self.evidence_expires_at
                else None,
                "lifecycle": self.lifecycle.value,
                "observed_at": normalize_timestamp(self.observed_at),
                "period_end": normalize_timestamp(self.period_end)
                if self.period_end
                else None,
                "period_start": normalize_timestamp(self.period_start)
                if self.period_start
                else None,
            },
            "consent": {
                "consent_data_class": self.consent_data_class,
                "consent_id": self.consent_id,
                "consent_namespace": self.consent_namespace,
                "consent_purpose": self.consent_purpose,
                "consent_use_scope": self.consent_use_scope,
                "consent_version": self.consent_version,
                "expires_at": normalize_timestamp(self.consent_expires_at),
                "retention_until": normalize_timestamp(self.retention_until),
                "status": self.consent_status,
            },
            "integrity": {
                "integrity_reference": self.integrity_reference,
                "integrity_valid": self.integrity_valid,
            },
            "proposition_verification": {
                "proposition_schema_version": self.proposition_schema_version,
                "proposition_type": self.proposition_type,
                "proposition_unit": self.proposition_unit,
                "proposition_value": self.proposition_value,
                "verification_method": self.verification_method,
                "status": self.verification_status.value,
            },
            "resolver_version": self.resolver_version,
            "source_attestation": {
                "acquisition_method": self.acquisition_method,
                "attestation_id": self.source_attestation_id,
                "attestation_version": self.source_attestation_version,
                "issuer_id": self.issuer_id,
                "production_qualified": self.production_qualified_source,
                "proposition_allowed": self.source_allows_proposition,
                "registry_digest": self.source_registry_digest,
                "source_class": self.source_class,
                "source_id": self.source_id,
                "valid_until": normalize_timestamp(self.source_valid_until),
            },
            "subject": {
                "subject_digest": self.subject_digest,
                "subject_id": self.subject_id,
            },
            "tenant_case": {
                "case_id": str(self.case_id),
                "tenant_id": str(self.tenant_id),
            },
        }

    def authority_digest(self) -> str:
        return canonical_digest(self.authority_record())

    def current_usability(
        self, *, as_of: datetime
    ) -> tuple[EvidenceUsability, UnusableReason | None]:
        """Apply time-local fail-closed checks to the authoritative resolution."""
        normalize_timestamp(as_of)
        if self.usability is EvidenceUsability.UNUSABLE:
            return self.usability, self.unusable_reason
        if not self.integrity_valid:
            return EvidenceUsability.UNUSABLE, UnusableReason.INTEGRITY_FAILURE
        if self.observed_at > as_of + MAX_EVIDENCE_CLOCK_SKEW:
            return EvidenceUsability.UNUSABLE, UnusableReason.EVIDENCE_NOT_YET_OBSERVED
        if (
            self.period_end is not None
            and self.period_end > as_of + MAX_EVIDENCE_CLOCK_SKEW
        ):
            return EvidenceUsability.UNUSABLE, UnusableReason.EVIDENCE_NOT_YET_OBSERVED
        if not self.production_qualified_source or not self.source_allows_proposition:
            return EvidenceUsability.UNUSABLE, UnusableReason.SOURCE_NOT_TRUSTED
        if self.source_valid_until <= as_of:
            return EvidenceUsability.UNUSABLE, UnusableReason.SOURCE_ATTESTATION_EXPIRED
        if self.consent_status == "WITHDRAWN":
            return EvidenceUsability.UNUSABLE, UnusableReason.CONSENT_WITHDRAWN
        if self.consent_status == "EXPIRED":
            return EvidenceUsability.UNUSABLE, UnusableReason.CONSENT_EXPIRED
        if self.consent_status == "SUPERSEDED":
            return EvidenceUsability.UNUSABLE, UnusableReason.CONSENT_OUT_OF_SCOPE
        if self.consent_use_scope != INVESTIGATOR_ANALYTICAL_USE_SCOPE:
            return EvidenceUsability.UNUSABLE, UnusableReason.CONSENT_OUT_OF_SCOPE
        if self.consent_expires_at <= as_of or self.retention_until <= as_of:
            return EvidenceUsability.UNUSABLE, UnusableReason.CONSENT_EXPIRED
        if self.evidence_expires_at is None or self.evidence_expires_at <= as_of:
            return EvidenceUsability.UNUSABLE, UnusableReason.EVIDENCE_EXPIRED
        lifecycle_reason = {
            EvidenceLifecycle.QUARANTINED: UnusableReason.EVIDENCE_QUARANTINED,
            EvidenceLifecycle.DISPUTED: UnusableReason.EVIDENCE_DISPUTED,
            EvidenceLifecycle.SUPERSEDED: UnusableReason.EVIDENCE_SUPERSEDED,
            EvidenceLifecycle.REVOKED: UnusableReason.EVIDENCE_REVOKED,
            EvidenceLifecycle.EXPIRED: UnusableReason.EVIDENCE_EXPIRED,
        }.get(self.lifecycle)
        if lifecycle_reason is not None:
            return EvidenceUsability.UNUSABLE, lifecycle_reason
        return EvidenceUsability.USABLE, None


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    reference_id: UUID
    tenant_id: UUID
    case_id: UUID
    subject_id: str
    subject_digest: str
    evidence_namespace: str
    evidence_id: str
    evidence_version: str
    artifact_digest: str
    evidence_class: EvidenceClass
    lifecycle: EvidenceLifecycle
    verification_status: VerificationStatus
    proposition_type: str | None
    proposition_schema_version: int | None
    proposition_value: str | None
    proposition_unit: str | None
    verification_method: str | None
    period_start: datetime | None
    period_end: datetime | None
    observed_at: datetime
    evidence_expires_at: datetime | None
    source_id: str
    issuer_id: str
    acquisition_method: str
    source_class: str
    source_attestation_id: str
    source_attestation_version: str
    source_registry_digest: str
    source_valid_until: datetime
    consent_namespace: str
    consent_id: str
    consent_version: str
    consent_purpose: str
    consent_data_class: str
    consent_use_scope: str
    consent_status: str
    consent_expires_at: datetime
    retention_until: datetime
    integrity_reference: str
    resolver_version: str
    authority_digest: str
    supersedes_reference_id: UUID | None
    accepted_at: datetime

    @classmethod
    def from_resolution(
        cls,
        *,
        reference_id: UUID,
        resolution: EvidenceAuthorityResolution,
        supersedes_reference_id: UUID | None,
        accepted_at: datetime,
    ) -> EvidenceReference:
        if resolution.evidence_class is EvidenceClass.EXPERIMENTAL_OBSERVATION:
            raise EvidenceBoundaryError(
                "experimental observation acquisition is not enabled in Phase 2"
            )
        usability, reason = resolution.current_usability(as_of=accepted_at)
        if usability is not EvidenceUsability.USABLE:
            suffix = reason.value if reason is not None else "UNKNOWN"
            raise EvidenceBoundaryError(
                f"evidence is not analytically usable: {suffix}"
            )
        return cls(
            reference_id=reference_id,
            tenant_id=resolution.tenant_id,
            case_id=resolution.case_id,
            subject_id=resolution.subject_id,
            subject_digest=resolution.subject_digest,
            evidence_namespace=resolution.evidence_namespace,
            evidence_id=resolution.evidence_id,
            evidence_version=resolution.evidence_version,
            artifact_digest=resolution.artifact_digest,
            evidence_class=resolution.evidence_class,
            lifecycle=resolution.lifecycle,
            verification_status=resolution.verification_status,
            proposition_type=resolution.proposition_type,
            proposition_schema_version=resolution.proposition_schema_version,
            proposition_value=resolution.proposition_value,
            proposition_unit=resolution.proposition_unit,
            verification_method=resolution.verification_method,
            period_start=resolution.period_start,
            period_end=resolution.period_end,
            observed_at=resolution.observed_at,
            evidence_expires_at=resolution.evidence_expires_at,
            source_id=resolution.source_id,
            issuer_id=resolution.issuer_id,
            acquisition_method=resolution.acquisition_method,
            source_class=resolution.source_class,
            source_attestation_id=resolution.source_attestation_id,
            source_attestation_version=resolution.source_attestation_version,
            source_registry_digest=resolution.source_registry_digest,
            source_valid_until=resolution.source_valid_until,
            consent_namespace=resolution.consent_namespace,
            consent_id=resolution.consent_id,
            consent_version=resolution.consent_version,
            consent_purpose=resolution.consent_purpose,
            consent_data_class=resolution.consent_data_class,
            consent_use_scope=resolution.consent_use_scope,
            consent_status=resolution.consent_status,
            consent_expires_at=resolution.consent_expires_at,
            retention_until=resolution.retention_until,
            integrity_reference=resolution.integrity_reference,
            resolver_version=resolution.resolver_version,
            authority_digest=resolution.authority_digest(),
            supersedes_reference_id=supersedes_reference_id,
            accepted_at=accepted_at,
        )

    def canonical_record(self) -> dict[str, object]:
        return {
            "acceptance": {
                "accepted_at": normalize_timestamp(self.accepted_at),
                "authority_digest": self.authority_digest,
                "integrity_reference": self.integrity_reference,
                "resolver_version": self.resolver_version,
                "supersedes_reference_id": str(self.supersedes_reference_id)
                if self.supersedes_reference_id
                else None,
            },
            "artifact": {
                "artifact_digest": self.artifact_digest,
                "evidence_class": self.evidence_class.value,
                "evidence_id": self.evidence_id,
                "evidence_namespace": self.evidence_namespace,
                "evidence_version": self.evidence_version,
                "expires_at": normalize_timestamp(self.evidence_expires_at)
                if self.evidence_expires_at
                else None,
                "lifecycle": self.lifecycle.value,
                "observed_at": normalize_timestamp(self.observed_at),
                "period_end": normalize_timestamp(self.period_end)
                if self.period_end
                else None,
                "period_start": normalize_timestamp(self.period_start)
                if self.period_start
                else None,
            },
            "consent": {
                "consent_data_class": self.consent_data_class,
                "consent_id": self.consent_id,
                "consent_namespace": self.consent_namespace,
                "consent_purpose": self.consent_purpose,
                "consent_use_scope": self.consent_use_scope,
                "consent_version": self.consent_version,
                "expires_at": normalize_timestamp(self.consent_expires_at),
                "retention_until": normalize_timestamp(self.retention_until),
                "status": self.consent_status,
            },
            "proposition_verification": {
                "proposition_schema_version": self.proposition_schema_version,
                "proposition_type": self.proposition_type,
                "proposition_unit": self.proposition_unit,
                "proposition_value": self.proposition_value,
                "verification_method": self.verification_method,
                "status": self.verification_status.value,
            },
            "reference_id": str(self.reference_id),
            "schema_version": EVIDENCE_REFERENCE_SCHEMA_VERSION,
            "source_attestation": {
                "acquisition_method": self.acquisition_method,
                "attestation_id": self.source_attestation_id,
                "attestation_version": self.source_attestation_version,
                "issuer_id": self.issuer_id,
                "registry_digest": self.source_registry_digest,
                "source_class": self.source_class,
                "source_id": self.source_id,
                "valid_until": normalize_timestamp(self.source_valid_until),
            },
            "subject": {
                "subject_digest": self.subject_digest,
                "subject_id": self.subject_id,
            },
        }


class EvidenceAuthority(Protocol):
    """Read-only port implemented by the canonical evidence authority."""

    def resolve(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        evidence_namespace: str,
        evidence_id: str,
        purpose: str,
        as_of: datetime,
    ) -> EvidenceAuthorityResolution: ...

    def revalidate(
        self, reference: EvidenceReference, *, as_of: datetime
    ) -> EvidenceAuthorityResolution: ...


def evidence_state_digest(references: tuple[EvidenceReference, ...]) -> str:
    records = sorted(
        (reference.canonical_record() for reference in references),
        key=lambda item: str(item["reference_id"]),
    )
    return canonical_digest(records)


def frozen_reference_record(reference: EvidenceReference) -> MappingProxyType:
    """Return a shallow immutable wrapper for presentation-only consumers."""
    return MappingProxyType(reference.canonical_record())
