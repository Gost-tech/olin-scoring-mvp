"""Read-only canonical Evidence Passport/consent adapter for Investigator.

This module intentionally lives outside ``olin.investigator``.  It is the
separately authorized bridge that may read canonical systems; the restricted
Investigator runtime receives only the resolved, immutable contract object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

from .investigator.canonical import canonical_digest, normalize_timestamp
from .investigator.evidence import (
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    INVESTIGATOR_ANALYTICAL_USE_SCOPE,
    EvidenceAuthorityResolution,
    EvidenceBoundaryError,
    EvidenceClass,
    EvidenceLifecycle,
    EvidenceReference,
    EvidenceUsability,
    UnusableReason,
    VerificationStatus,
)
from .source_trust import assess_source_attestation


@dataclass(frozen=True, slots=True)
class CanonicalArtifactRecord:
    tenant_id: UUID
    case_id: UUID
    subject_id: str
    subject_digest: str
    subject_controller_id: str
    namespace: str
    evidence_id: str
    version: str
    artifact_digest: str
    data_class: str
    origin_class: EvidenceClass
    lifecycle: EvidenceLifecycle
    observed_at: datetime
    expires_at: datetime | None
    source_id: str
    issuer_id: str
    acquisition_method: str
    consent_namespace: str
    consent_id: str
    integrity_reference: str
    integrity_valid: bool


@dataclass(frozen=True, slots=True)
class CanonicalConsentAuthorization:
    namespace: str
    consent_id: str
    version: str
    tenant_id: UUID
    case_id: UUID
    subject_id: str
    subject_digest: str
    purpose: str
    data_class: str
    use_scope: str
    status: str
    expires_at: datetime
    retention_until: datetime


@dataclass(frozen=True, slots=True)
class CanonicalPropositionVerification:
    proposition_type: str
    schema_version: int
    value: str
    unit: str
    verification_method: str
    period_start: datetime | None
    period_end: datetime | None


@dataclass(frozen=True, slots=True)
class ExistingPassportCaseBinding:
    """Server-established mapping from an Investigator case to a legacy case."""

    tenant_id: UUID
    case_id: UUID
    application_id: str
    owner_actor: str


class ReadOnlyQueryConnection(Protocol):
    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> Any: ...


class CanonicalEvidenceReadPort(Protocol):
    """Bounded reads implemented by canonical Passport/consent storage owners."""

    def artifact(self, namespace: str, evidence_id: str) -> CanonicalArtifactRecord: ...

    def consent(
        self, namespace: str, consent_id: str
    ) -> CanonicalConsentAuthorization: ...

    def proposition(
        self, namespace: str, evidence_id: str
    ) -> CanonicalPropositionVerification | None: ...


class ExistingEvidencePassportReadPort:
    """Read existing Passport/consent rows without promoting legacy verification.

    Existing ``evidence_record.status='verified'`` is document-level legacy state,
    not a proposition-specific Phase 2 verification. Consequently this adapter
    always returns ``None`` from :meth:`proposition`. Existing consent rows also
    lack machine-readable analytical scope, expiry, and retention authority, so
    they remain historical but analytically unusable until the canonical consent
    owner supplies a richer port. The connection is caller-owned and used only
    for parameterized SELECTs.
    """

    def __init__(
        self,
        connection: ReadOnlyQueryConnection,
        *,
        binding: ExistingPassportCaseBinding,
    ) -> None:
        self._connection = connection
        self._binding = binding

    @staticmethod
    def _timestamp(value: object, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceBoundaryError(
                f"canonical {field} timestamp is invalid"
            ) from exc
        if parsed.tzinfo is None:
            raise EvidenceBoundaryError(
                f"canonical {field} timestamp must include a timezone"
            )
        return parsed.astimezone(timezone.utc)

    def _case_owner(self) -> str:
        row = self._connection.execute(
            "SELECT owner_actor FROM scoring_log WHERE application_id=?",
            (self._binding.application_id,),
        ).fetchone()
        if row is None or str(row[0] or "") != self._binding.owner_actor:
            raise LookupError("canonical case binding not found")
        return str(row[0])

    def artifact(self, namespace: str, evidence_id: str) -> CanonicalArtifactRecord:
        if namespace != "evidence_passport":
            raise LookupError("canonical evidence namespace is unsupported")
        owner_actor = self._case_owner()
        row = self._connection.execute(
            "SELECT * FROM evidence_record WHERE evidence_id=? "
            "AND application_id=? AND owner_actor=?",
            (evidence_id, self._binding.application_id, owner_actor),
        ).fetchone()
        if row is None:
            raise LookupError("canonical Evidence Passport record not found")
        record_digest = canonical_digest(
            {
                field: str(row[field] or "")
                for field in (
                    "evidence_id",
                    "application_id",
                    "owner_actor",
                    "evidence_type",
                    "source_id",
                    "origin_id",
                    "subject_key",
                    "subject_hash",
                    "verification_method",
                    "source_reference",
                    "attestation_id",
                    "consent_id",
                    "observed_at",
                    "expires_at",
                    "metadata_sha256",
                    "created_at",
                )
            }
        )
        status = str(row["status"] or "").lower()
        lifecycle = (
            EvidenceLifecycle.ACCEPTED
            if status == "verified"
            else EvidenceLifecycle.REVOKED
        )
        return CanonicalArtifactRecord(
            tenant_id=self._binding.tenant_id,
            case_id=self._binding.case_id,
            subject_id=str(row["subject_key"]),
            subject_digest=str(row["subject_hash"]),
            subject_controller_id=owner_actor,
            namespace=namespace,
            evidence_id=str(row["evidence_id"]),
            version=record_digest,
            artifact_digest=record_digest,
            data_class=str(row["evidence_type"]),
            origin_class=EvidenceClass.EXTERNAL_EVIDENCE,
            lifecycle=lifecycle,
            observed_at=self._timestamp(row["observed_at"], "observed_at"),
            expires_at=self._timestamp(row["expires_at"], "expires_at"),
            source_id=str(row["source_id"]),
            issuer_id="legacy_issuer_unresolved",
            acquisition_method="legacy_passport_registration",
            consent_namespace="consent_record",
            consent_id=str(row["consent_id"]),
            integrity_reference=str(row["source_reference"]),
            integrity_valid=False,
        )

    def consent(self, namespace: str, consent_id: str) -> CanonicalConsentAuthorization:
        if namespace != "consent_record":
            raise LookupError("canonical consent namespace is unsupported")
        self._case_owner()
        row = self._connection.execute(
            "SELECT * FROM consent_record WHERE consent_id=? AND application_id=?",
            (consent_id, self._binding.application_id),
        ).fetchone()
        if row is None:
            raise LookupError("canonical consent record not found")
        captured_at = self._timestamp(row["captured_at"], "captured_at")
        status = str(row["status"] or "").upper()
        if status not in {"ACTIVE", "WITHDRAWN", "SUPERSEDED"}:
            status = "EXPIRED"
        # Legacy consent does not encode Phase 2 data/use scope or machine-readable
        # expiry. Marking it expired preserves auditability without inventing use.
        return CanonicalConsentAuthorization(
            namespace=namespace,
            consent_id=str(row["consent_id"]),
            version=f"{row['policy_version']}:{row['text_sha256']}",
            tenant_id=self._binding.tenant_id,
            case_id=self._binding.case_id,
            subject_id="legacy_subject_unresolved",
            subject_digest="0" * 64,
            purpose=str(row["purpose"]),
            data_class="legacy_unspecified",
            use_scope="legacy_unspecified",
            status="EXPIRED" if status == "ACTIVE" else status,
            expires_at=captured_at,
            retention_until=captured_at,
        )

    def proposition(
        self, namespace: str, evidence_id: str
    ) -> CanonicalPropositionVerification | None:
        # Confirm the record exists/belongs to the bound case, then refuse to map
        # legacy document-level verification into proposition truth.
        self.artifact(namespace, evidence_id)
        return None


class EvidencePassportReadAdapter:
    """Resolve canonical records without mutation, acquisition, or provider calls."""

    def __init__(self, port: CanonicalEvidenceReadPort) -> None:
        self._port = port

    def resolve(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        evidence_namespace: str,
        evidence_id: str,
        purpose: str,
        as_of: datetime,
    ) -> EvidenceAuthorityResolution:
        normalize_timestamp(as_of)
        artifact = self._port.artifact(evidence_namespace, evidence_id)
        consent = self._port.consent(artifact.consent_namespace, artifact.consent_id)
        proposition = self._port.proposition(evidence_namespace, evidence_id)
        proposition_type = (
            proposition.proposition_type
            if proposition is not None
            else "artifact_submission_recorded"
        )
        trust = assess_source_attestation(
            artifact.source_id,
            issuer_id=artifact.issuer_id,
            acquisition_method=artifact.acquisition_method,
            proposition_type=proposition_type,
            tenant_id=str(tenant_id),
            subject_controller_id=artifact.subject_controller_id,
            as_of=as_of.date(),
            production=True,
        )
        binding_matches = (
            artifact.tenant_id == tenant_id
            and artifact.case_id == case_id
            and consent.tenant_id == tenant_id
            and consent.case_id == case_id
            and artifact.subject_id == consent.subject_id
            and artifact.subject_digest == consent.subject_digest
        )
        reason: UnusableReason | None = None
        freshness_deadline = artifact.observed_at + timedelta(
            days=trust.freshness_max_age_days
        )
        effective_expiry = min(
            value
            for value in (artifact.expires_at, freshness_deadline)
            if value is not None
        )
        if artifact.tenant_id != tenant_id or consent.tenant_id != tenant_id:
            reason = UnusableReason.TENANT_MISMATCH
        elif artifact.case_id != case_id or consent.case_id != case_id:
            reason = UnusableReason.CASE_MISMATCH
        elif not binding_matches:
            reason = UnusableReason.SUBJECT_MISMATCH
        elif (
            consent.purpose != purpose
            or consent.data_class != artifact.data_class
            or consent.use_scope != INVESTIGATOR_ANALYTICAL_USE_SCOPE
        ):
            reason = UnusableReason.CONSENT_OUT_OF_SCOPE
        elif consent.status == "WITHDRAWN":
            reason = UnusableReason.CONSENT_WITHDRAWN
        elif consent.status == "EXPIRED":
            reason = UnusableReason.CONSENT_EXPIRED
        elif consent.status == "SUPERSEDED":
            reason = UnusableReason.CONSENT_OUT_OF_SCOPE
        elif consent.expires_at <= as_of or consent.retention_until <= as_of:
            reason = UnusableReason.CONSENT_EXPIRED
        elif not artifact.integrity_valid:
            reason = UnusableReason.INTEGRITY_FAILURE
        elif artifact.observed_at > as_of + timedelta(minutes=5) or (
            proposition is not None
            and proposition.period_end is not None
            and proposition.period_end > as_of + timedelta(minutes=5)
        ):
            reason = UnusableReason.EVIDENCE_NOT_YET_OBSERVED
        elif not trust.trusted:
            reason = UnusableReason.SOURCE_NOT_TRUSTED
        elif effective_expiry <= as_of:
            reason = UnusableReason.EVIDENCE_EXPIRED
        lifecycle_reason = {
            EvidenceLifecycle.QUARANTINED: UnusableReason.EVIDENCE_QUARANTINED,
            EvidenceLifecycle.DISPUTED: UnusableReason.EVIDENCE_DISPUTED,
            EvidenceLifecycle.SUPERSEDED: UnusableReason.EVIDENCE_SUPERSEDED,
            EvidenceLifecycle.REVOKED: UnusableReason.EVIDENCE_REVOKED,
            EvidenceLifecycle.EXPIRED: UnusableReason.EVIDENCE_EXPIRED,
        }.get(artifact.lifecycle)
        reason = reason or lifecycle_reason
        verified = (
            proposition is not None and trust.trusted and artifact.integrity_valid
        )
        evidence_class = (
            EvidenceClass.VERIFIED_FACT if verified else artifact.origin_class
        )
        verification_status = (
            VerificationStatus.VERIFIED_FOR_PROPOSITION
            if verified
            else VerificationStatus.UNVERIFIED
        )
        valid_until = datetime.combine(
            datetime.fromisoformat(trust.valid_until).date()
            if trust.valid_until
            else as_of.date(),
            time.max,
            tzinfo=timezone.utc,
        )
        return EvidenceAuthorityResolution._from_authoritative_adapter(
            tenant_id=artifact.tenant_id,
            case_id=artifact.case_id,
            subject_id=artifact.subject_id,
            subject_digest=artifact.subject_digest,
            evidence_namespace=artifact.namespace,
            evidence_id=artifact.evidence_id,
            evidence_version=artifact.version,
            artifact_digest=artifact.artifact_digest,
            evidence_class=evidence_class,
            lifecycle=artifact.lifecycle,
            verification_status=verification_status,
            proposition_type=proposition.proposition_type if verified else None,
            proposition_schema_version=proposition.schema_version if verified else None,
            proposition_value=proposition.value if verified else None,
            proposition_unit=proposition.unit if verified else None,
            verification_method=proposition.verification_method if verified else None,
            period_start=proposition.period_start if proposition else None,
            period_end=proposition.period_end if proposition else None,
            observed_at=artifact.observed_at,
            evidence_expires_at=effective_expiry,
            source_id=artifact.source_id,
            issuer_id=artifact.issuer_id,
            acquisition_method=artifact.acquisition_method,
            source_class=trust.source_class or "unresolved",
            source_attestation_id=trust.attestation_id or "unresolved",
            source_attestation_version=trust.attestation_version or "unresolved",
            source_registry_digest=trust.registry_digest,
            source_valid_until=valid_until,
            production_qualified_source=trust.trusted,
            source_allows_proposition=trust.trusted,
            consent_namespace=consent.namespace,
            consent_id=consent.consent_id,
            consent_version=consent.version,
            consent_purpose=consent.purpose,
            consent_data_class=consent.data_class,
            consent_use_scope=consent.use_scope,
            consent_status=consent.status,
            consent_expires_at=consent.expires_at,
            retention_until=consent.retention_until,
            integrity_reference=artifact.integrity_reference,
            integrity_valid=artifact.integrity_valid,
            usability=EvidenceUsability.UNUSABLE
            if reason
            else EvidenceUsability.USABLE,
            unusable_reason=reason,
            resolver_version=EVIDENCE_RESOLVER_CONTRACT_VERSION,
            resolved_at=as_of,
        )

    def revalidate(
        self, reference: EvidenceReference, *, as_of: datetime
    ) -> EvidenceAuthorityResolution:
        return self.resolve(
            tenant_id=reference.tenant_id,
            case_id=reference.case_id,
            evidence_namespace=reference.evidence_namespace,
            evidence_id=reference.evidence_id,
            purpose=reference.consent_purpose,
            as_of=as_of,
        )
