"""Read-only canonical Evidence Passport/consent adapter for Investigator.

This module intentionally lives outside ``olin.investigator``.  It is the
separately authorized bridge that may read canonical systems; the restricted
Investigator runtime receives only the resolved, immutable contract object.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
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
    IndependenceStatus,
    LineageRelation,
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
    semantic_independence_schema_version: int | None
    semantic_lineage_id: str
    lineage_relation: LineageRelation
    derived_from_evidence_namespace: str | None
    derived_from_evidence_id: str | None
    derived_from_evidence_version: str | None
    economic_event_id: str | None
    upstream_issuer_id: str
    independence_status: IndependenceStatus
    independence_attestation_id: str | None
    independence_attestation_version: str | None


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
            semantic_independence_schema_version=None,
            semantic_lineage_id=f"legacy:{row['evidence_id']}",
            lineage_relation=LineageRelation.UNKNOWN,
            derived_from_evidence_namespace=None,
            derived_from_evidence_id=None,
            derived_from_evidence_version=None,
            economic_event_id=None,
            upstream_issuer_id="legacy_issuer_unresolved",
            independence_status=IndependenceStatus.INDEPENDENCE_UNKNOWN,
            independence_attestation_id=None,
            independence_attestation_version=None,
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
            semantic_independence_schema_version=artifact.semantic_independence_schema_version,
            semantic_lineage_id=artifact.semantic_lineage_id,
            lineage_relation=artifact.lineage_relation,
            derived_from_evidence_namespace=artifact.derived_from_evidence_namespace,
            derived_from_evidence_id=artifact.derived_from_evidence_id,
            derived_from_evidence_version=artifact.derived_from_evidence_version,
            economic_event_id=artifact.economic_event_id,
            upstream_issuer_id=artifact.upstream_issuer_id,
            independence_status=artifact.independence_status,
            independence_attestation_id=artifact.independence_attestation_id,
            independence_attestation_version=artifact.independence_attestation_version,
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


class PostgresCanonicalEvidenceReadPort:
    """PostgreSQL-only authority port over one owner-maintained projection.

    The projection owns canonical joins across artifact, consent, subject,
    proposition, source-attestation, and semantic-lineage state. This adapter
    receives references only and never reads an artifact body or mutates authority.
    """

    PROJECTION_VERSION = "canonical-evidence-projection-1"
    _FIELDS = (
        "projection_version",
        "authority_digest",
        "tenant_id",
        "case_id",
        "subject_id",
        "subject_digest",
        "evidence_namespace",
        "evidence_id",
        "evidence_version",
        "artifact_digest",
        "evidence_class",
        "lifecycle",
        "verification_status",
        "proposition_type",
        "proposition_schema_version",
        "proposition_value",
        "proposition_unit",
        "verification_method",
        "period_start",
        "period_end",
        "observed_at",
        "evidence_expires_at",
        "source_id",
        "issuer_id",
        "acquisition_method",
        "source_class",
        "source_attestation_id",
        "source_attestation_version",
        "source_registry_digest",
        "source_valid_until",
        "production_qualified_source",
        "source_allows_proposition",
        "consent_namespace",
        "consent_id",
        "consent_version",
        "consent_purpose",
        "consent_data_class",
        "consent_use_scope",
        "consent_status",
        "consent_expires_at",
        "retention_until",
        "integrity_reference",
        "integrity_valid",
        "semantic_independence_schema_version",
        "semantic_lineage_id",
        "lineage_relation",
        "derived_from_evidence_namespace",
        "derived_from_evidence_id",
        "derived_from_evidence_version",
        "economic_event_id",
        "upstream_issuer_id",
        "independence_status",
        "independence_attestation_id",
        "independence_attestation_version",
        "usability",
        "unusable_reason",
    )

    def __init__(self, connection: ReadOnlyQueryConnection, *, tenant_id: UUID) -> None:
        module = type(connection).__module__
        if not (module == "psycopg" or module.startswith(("psycopg.", "psycopg2"))):
            raise EvidenceBoundaryError(
                "canonical evidence authority requires PostgreSQL; SQLite fallback is forbidden"
            )
        self._connection = connection
        self._tenant_id = tenant_id
        self._is_test_fake = module.startswith("psycopg.testing")
        if self._is_test_fake:
            self._assert_reader_custody()
        else:
            with self._reader_transaction():
                self._assert_reader_custody()

    @contextmanager
    def _reader_transaction(self):
        status = getattr(
            getattr(self._connection, "info", None), "transaction_status", None
        )
        if status is not None and getattr(status, "name", "") != "IDLE":
            raise EvidenceBoundaryError(
                "canonical evidence reader connection must be idle"
            )
        with self._connection.transaction():
            self._connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
            )
            self._connection.execute(
                "SET LOCAL statement_timeout='5000ms'; "
                "SET LOCAL lock_timeout='1000ms'; "
                "SET LOCAL idle_in_transaction_session_timeout='5000ms'"
            )
            yield

    def _assert_reader_custody(self) -> None:
        try:
            row = self._connection.execute(
                "SELECT session_user = %s, current_user = session_user, "
                "pg_has_role(session_user, "
                "'olin_investigator_evidence_reader', 'member'), "
                "pg_has_role(session_user, 'olin_investigator_runtime', 'member'), "
                "pg_has_role(session_user, "
                "'olin_investigator_evidence_authority', 'member'), "
                "pg_has_role(session_user, 'olin_investigator_owner', 'member'), "
                "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
                "OR rolreplication OR rolbypassrls) FROM pg_roles "
                "WHERE rolname=session_user),false), "
                "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
                "OR rolreplication OR rolbypassrls) FROM pg_roles "
                "WHERE rolname='olin_investigator_evidence_reader'),false), "
                "NOT EXISTS (SELECT 1 FROM ("
                "SELECT (aclexplode(relacl)).grantee FROM pg_class UNION ALL "
                "SELECT (aclexplode(proacl)).grantee FROM pg_proc UNION ALL "
                "SELECT (aclexplode(nspacl)).grantee FROM pg_namespace) direct_acl "
                "JOIN pg_roles grantee ON grantee.oid=direct_acl.grantee "
                "WHERE grantee.rolname=session_user), "
                "current_setting('transaction_read_only') = 'on', "
                "current_setting('transaction_isolation') = 'read committed', "
                "NOT EXISTS (WITH RECURSIVE memberships(roleid) AS ("
                "SELECT membership.roleid FROM pg_auth_members membership "
                "JOIN pg_roles login ON login.oid=membership.member "
                "WHERE login.rolname=session_user UNION "
                "SELECT membership.roleid FROM pg_auth_members membership "
                "JOIN memberships prior ON membership.member=prior.roleid) "
                "SELECT 1 FROM memberships JOIN pg_roles granted "
                "ON granted.oid=memberships.roleid WHERE granted.rolname <> "
                "'olin_investigator_evidence_reader')",
                ("olin_canonical_t_" + self._tenant_id.hex,),
            ).fetchone()
        except Exception as error:
            raise EvidenceBoundaryError(
                "canonical evidence reader credential custody is unavailable"
            ) from error
        if row is None or tuple(row) != (
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
        ):
            raise EvidenceBoundaryError(
                "canonical evidence reader credential custody is ambiguous"
            )

    @staticmethod
    def _utc(value: object, field: str, *, optional: bool = False) -> datetime | None:
        if value is None and optional:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
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

    def _row(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        evidence_namespace: str,
        evidence_id: str,
        purpose: str,
        as_of: datetime,
    ) -> dict[str, object]:
        if tenant_id != self._tenant_id:
            raise EvidenceBoundaryError(
                "canonical evidence reader is not bound to the requested tenant"
            )
        if not self._is_test_fake:
            with self._reader_transaction():
                return self._row_in_transaction(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    evidence_namespace=evidence_namespace,
                    evidence_id=evidence_id,
                    purpose=purpose,
                    as_of=as_of,
                )
        return self._row_in_transaction(
            tenant_id=tenant_id,
            case_id=case_id,
            evidence_namespace=evidence_namespace,
            evidence_id=evidence_id,
            purpose=purpose,
            as_of=as_of,
        )

    def _row_in_transaction(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        evidence_namespace: str,
        evidence_id: str,
        purpose: str,
        as_of: datetime,
    ) -> dict[str, object]:
        self._assert_reader_custody()
        self._connection.execute(
            "SELECT set_config('olin.tenant_id', %s, true)", (str(tenant_id),)
        ).fetchone()
        columns = ", ".join(self._FIELDS)
        cursor = self._connection.execute(
            f"SELECT {columns} FROM "
            "evidence_authority.investigator_evidence_v1 "
            "WHERE tenant_id=%s AND case_id=%s AND evidence_namespace=%s "
            "AND evidence_id=%s AND consent_purpose=%s",
            (
                tenant_id,
                case_id,
                evidence_namespace,
                evidence_id,
                purpose,
            ),
        )
        if hasattr(cursor, "fetchmany"):
            rows = cursor.fetchmany(2)
        else:  # narrow protocol fallback used only by deterministic unit fakes
            first = cursor.fetchone()
            rows = [] if first is None else [first]
        if not rows:
            raise LookupError("canonical PostgreSQL evidence was not found")
        if len(rows) != 1:
            raise EvidenceBoundaryError(
                "canonical PostgreSQL evidence authority is ambiguous"
            )
        row = rows[0]
        if isinstance(row, Mapping):
            values = {field: row[field] for field in self._FIELDS if field in row}
        else:
            values = dict(zip(self._FIELDS, row, strict=True))
        if set(values) != set(self._FIELDS):
            raise EvidenceBoundaryError("canonical PostgreSQL projection is incomplete")
        if values["projection_version"] != self.PROJECTION_VERSION:
            raise EvidenceBoundaryError(
                "canonical PostgreSQL projection version is unsupported"
            )
        return values

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
        values = self._row(
            tenant_id=tenant_id,
            case_id=case_id,
            evidence_namespace=evidence_namespace,
            evidence_id=evidence_id,
            purpose=purpose,
            as_of=as_of,
        )
        for field in (
            "observed_at",
            "source_valid_until",
            "consent_expires_at",
            "retention_until",
        ):
            values[field] = self._utc(values[field], field)
        for field in ("period_start", "period_end", "evidence_expires_at"):
            values[field] = self._utc(values[field], field, optional=True)
        values.pop("projection_version")
        expected_authority_digest = values.pop("authority_digest")
        values.update(
            resolver_version=EVIDENCE_RESOLVER_CONTRACT_VERSION,
            resolved_at=as_of,
        )
        resolution = EvidenceAuthorityResolution._from_authoritative_adapter(**values)
        if resolution.authority_digest() != expected_authority_digest:
            raise EvidenceBoundaryError(
                "canonical PostgreSQL authority digest does not match its projection"
            )
        return resolution

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
