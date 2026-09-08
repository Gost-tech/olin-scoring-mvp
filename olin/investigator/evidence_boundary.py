"""Bounded commands joining canonical evidence authority to the case spine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from .actor import ActorContext
from .canonical import canonical_digest, normalize_timestamp
from .events import EventType
from .evidence import (
    CALLER_TRUST_LABELS,
    MAX_EVIDENCE_CLOCK_SKEW,
    EvidenceAuthority,
    EvidenceAuthorityResolution,
    EvidenceBoundaryError,
    EvidenceReference,
    EvidenceUsability,
    UnusableReason,
)
from .spine import CaseSnapshot, InMemoryCaseSpine, SpineConflict


class CaseSubjectAuthority:
    """Read-only authoritative case-subject binding port."""

    def resolve_subject(self, *, tenant_id: UUID, case_id: UUID) -> tuple[str, str]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EvidenceAcceptance:
    reference: EvidenceReference
    event_id: UUID
    evidence_state_version: int


class InvestigatorEvidenceBoundary:
    """Reference-only Phase 2 executable specification.

    Canonical trust, consent, issuer, and evidence lifecycle remain owned by the
    injected read-only authorities.  This object records only immutable
    references and case events.
    """

    def __init__(
        self,
        *,
        spine: InMemoryCaseSpine,
        evidence_authority: EvidenceAuthority,
        subject_authority: CaseSubjectAuthority,
        uuid_factory=uuid4,
    ) -> None:
        self._spine = spine
        self._evidence_authority = evidence_authority
        self._subject_authority = subject_authority
        self._uuid_factory = uuid_factory
        self._lock = RLock()
        self._references: dict[tuple[UUID, UUID], list[EvidenceReference]] = {}
        self._acceptance_requests: dict[
            tuple[UUID, str], tuple[tuple[object, ...], EvidenceAcceptance]
        ] = {}
        self._state_requests: dict[
            tuple[UUID, str], tuple[tuple[object, ...], object]
        ] = {}
        self._state_versions: dict[tuple[UUID, UUID], int] = {}
        self._unusable_references: dict[tuple[UUID, UUID, UUID], str] = {}
        self._inactive_consents: dict[tuple[UUID, UUID, str, str], str] = {}

    def accept_evidence(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        current_snapshot_id: UUID,
        expected_case_version: int,
        evidence_namespace: str,
        evidence_id: str,
        purpose: str,
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
        submitted_claims: Mapping[str, object] | None = None,
        supersedes_reference_id: UUID | None = None,
    ) -> EvidenceAcceptance:
        """Resolve canonical state and append one reference; caller labels are inert."""
        actor.require_scope(tenant_id, case_id)
        request = (
            case_id,
            current_snapshot_id,
            expected_case_version,
            evidence_namespace,
            evidence_id,
            purpose,
            actor,
            occurred_at,
            supersedes_reference_id,
        )
        with self._lock:
            replay = self._acceptance_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                if replay[0] != request:
                    raise SpineConflict(
                        "evidence idempotency key conflicts with an existing request"
                    )
                return replay[1]
        self._require_server_bounded_command_time(occurred_at)
        self._require_current_snapshot_for_case(
            tenant_id=tenant_id,
            case_id=case_id,
            snapshot_id=current_snapshot_id,
        )
        # These labels are intentionally neither persisted nor sent to authorities.
        # Deliberately inspect only names, never values, and confer no authority.
        _ = frozenset(submitted_claims or {}) & CALLER_TRUST_LABELS
        with self._lock:
            replay = self._acceptance_requests.get((tenant_id, idempotency_key))
            if replay is not None:
                if replay[0] != request:
                    raise SpineConflict(
                        "evidence idempotency key conflicts with an existing request"
                    )
                return replay[1]
            resolution = self._evidence_authority.resolve(
                tenant_id=tenant_id,
                case_id=case_id,
                evidence_namespace=evidence_namespace,
                evidence_id=evidence_id,
                purpose=purpose,
                as_of=occurred_at,
            )
            self._validate_resolution(
                resolution,
                tenant_id=tenant_id,
                case_id=case_id,
                purpose=purpose,
                as_of=occurred_at,
            )
            key = (tenant_id, case_id)
            references = self._references.setdefault(key, [])
            duplicate = next(
                (
                    item
                    for item in references
                    if item.evidence_namespace == resolution.evidence_namespace
                    and item.evidence_id == resolution.evidence_id
                    and item.evidence_version == resolution.evidence_version
                ),
                None,
            )
            if duplicate is not None:
                raise SpineConflict(
                    "canonical evidence version is already referenced under another request"
                )
            same_artifact = next(
                (
                    item
                    for item in references
                    if item.artifact_digest == resolution.artifact_digest
                ),
                None,
            )
            if (
                same_artifact is not None
                and same_artifact.reference_id != supersedes_reference_id
            ):
                raise SpineConflict("artifact content is already referenced")
            if supersedes_reference_id is not None:
                prior = next(
                    (
                        item
                        for item in references
                        if item.reference_id == supersedes_reference_id
                    ),
                    None,
                )
                if prior is None:
                    raise EvidenceBoundaryError(
                        "superseded evidence reference was not found"
                    )
                if any(
                    item.supersedes_reference_id == supersedes_reference_id
                    for item in references
                ):
                    raise EvidenceBoundaryError(
                        "evidence reference already has a canonical successor"
                    )
                if (
                    prior.evidence_namespace != resolution.evidence_namespace
                    or prior.evidence_id != resolution.evidence_id
                    or prior.evidence_version == resolution.evidence_version
                ):
                    raise EvidenceBoundaryError(
                        "correction must be a new version of the same canonical evidence"
                    )
            reference = EvidenceReference.from_resolution(
                reference_id=self._uuid_factory(),
                resolution=resolution,
                supersedes_reference_id=supersedes_reference_id,
                accepted_at=occurred_at,
            )
            state_version = self._state_versions.get(key, 0) + 1
            event = self._spine._record_phase2_event(
                tenant_id=tenant_id,
                case_id=case_id,
                expected_case_version=expected_case_version,
                event_type=EventType.EVIDENCE_ACCEPTED,
                payload={
                    "reference_id": str(reference.reference_id),
                    "evidence_state_version": state_version,
                },
                actor=actor,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
            )
            references.append(reference)
            if supersedes_reference_id is not None:
                self._unusable_references[
                    (tenant_id, case_id, supersedes_reference_id)
                ] = "EVIDENCE_SUPERSEDED"
            self._state_versions[key] = state_version
            acceptance = EvidenceAcceptance(reference, event.event_id, state_version)
            self._acceptance_requests[(tenant_id, idempotency_key)] = (
                request,
                acceptance,
            )
            return acceptance

    def record_evidence_became_unusable(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        current_snapshot_id: UUID,
        reference_id: UUID,
        expected_case_version: int,
        reason_reference: str,
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
    ):
        request = (
            case_id,
            current_snapshot_id,
            reference_id,
            expected_case_version,
            reason_reference,
            actor,
            occurred_at,
            EventType.EVIDENCE_BECAME_UNUSABLE,
        )
        replay = self._state_requests.get((tenant_id, idempotency_key))
        if replay is not None:
            if replay[0] != request:
                raise SpineConflict("state idempotency key conflicts with history")
            return replay[1]
        self._require_server_bounded_command_time(occurred_at)
        self._require_current_snapshot_for_case(
            tenant_id=tenant_id,
            case_id=case_id,
            snapshot_id=current_snapshot_id,
        )
        reference = self._find_reference(tenant_id, case_id, reference_id)
        resolution = self._evidence_authority.revalidate(reference, as_of=occurred_at)
        usability, reason = resolution.current_usability(as_of=occurred_at)
        if usability is EvidenceUsability.USABLE:
            if resolution.authority_digest() == reference.authority_digest:
                raise EvidenceBoundaryError(
                    "canonical authority still reports evidence usable"
                )
            reason = UnusableReason.AUTHORITY_REFERENCE_CHANGED
        if reason is None:
            raise EvidenceBoundaryError("canonical unusability reason is missing")
        key = (tenant_id, case_id)
        state_version = self._state_versions.get(key, 0) + 1
        event = self._spine._record_phase2_event(
            tenant_id=tenant_id,
            case_id=case_id,
            expected_case_version=expected_case_version,
            event_type=EventType.EVIDENCE_BECAME_UNUSABLE,
            payload={
                "reference_id": str(reference_id),
                "evidence_state_version": state_version,
                "reason_code": reason.value,
                "reason_reference": reason_reference.strip(),
            },
            actor=actor,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        self._state_versions[key] = state_version
        self._unusable_references[(tenant_id, case_id, reference_id)] = reason.value
        self._state_requests[(tenant_id, idempotency_key)] = (request, event)
        return event

    def record_consent_state_changed(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        current_snapshot_id: UUID,
        consent_namespace: str,
        consent_id: str,
        status: str,
        expected_case_version: int,
        reason_reference: str,
        actor: ActorContext,
        idempotency_key: str,
        occurred_at: datetime,
    ):
        if status not in {"WITHDRAWN", "EXPIRED", "SUPERSEDED"}:
            raise EvidenceBoundaryError("consent status is unknown")
        request = (
            case_id,
            current_snapshot_id,
            consent_namespace,
            consent_id,
            status,
            expected_case_version,
            reason_reference,
            actor,
            occurred_at,
            EventType.CONSENT_STATE_CHANGED,
        )
        replay = self._state_requests.get((tenant_id, idempotency_key))
        if replay is not None:
            if replay[0] != request:
                raise SpineConflict("state idempotency key conflicts with history")
            return replay[1]
        self._require_server_bounded_command_time(occurred_at)
        self._require_current_snapshot_for_case(
            tenant_id=tenant_id,
            case_id=case_id,
            snapshot_id=current_snapshot_id,
        )
        affected = [
            item
            for item in self.references(tenant_id=tenant_id, case_id=case_id)
            if item.consent_namespace == consent_namespace
            and item.consent_id == consent_id
        ]
        if not affected:
            raise EvidenceBoundaryError("consent does not authorize any case evidence")
        canonical_statuses = {
            self._evidence_authority.revalidate(
                reference, as_of=occurred_at
            ).consent_status
            for reference in affected
        }
        if canonical_statuses != {status}:
            raise EvidenceBoundaryError(
                "consent state change does not match canonical authority"
            )
        key = (tenant_id, case_id)
        state_version = self._state_versions.get(key, 0) + 1
        event = self._spine._record_phase2_event(
            tenant_id=tenant_id,
            case_id=case_id,
            expected_case_version=expected_case_version,
            event_type=EventType.CONSENT_STATE_CHANGED,
            payload={
                "consent_namespace": consent_namespace,
                "consent_id": consent_id,
                "evidence_state_version": state_version,
                "status": status,
                "reason_reference": reason_reference.strip(),
            },
            actor=actor,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        self._state_versions[key] = state_version
        consent_reason = {
            "WITHDRAWN": "CONSENT_WITHDRAWN",
            "EXPIRED": "CONSENT_EXPIRED",
            "SUPERSEDED": "CONSENT_OUT_OF_SCOPE",
        }[status]
        self._inactive_consents[(tenant_id, case_id, consent_namespace, consent_id)] = (
            consent_reason
        )
        self._state_requests[(tenant_id, idempotency_key)] = (request, event)
        return event

    def create_snapshot_v2(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        expected_case_version: int,
        actor: ActorContext,
        idempotency_key: str,
        as_of: datetime,
    ) -> CaseSnapshot:
        self._require_server_bounded_command_time(as_of)
        evidence = self._snapshot_evidence(tenant_id, case_id, as_of=as_of)
        return self._spine._create_snapshot_v2(
            tenant_id=tenant_id,
            case_id=case_id,
            expected_case_version=expected_case_version,
            actor=actor,
            idempotency_key=idempotency_key,
            evidence=evidence,
        )

    def is_snapshot_current_for_reasoning(
        self, *, tenant_id: UUID, snapshot_id: UUID, as_of: datetime
    ) -> bool:
        try:
            self._require_server_bounded_command_time(as_of)
            if not self._spine.is_snapshot_current(
                tenant_id=tenant_id, snapshot_id=snapshot_id
            ):
                return False
            snapshot = self._spine._find_snapshot(tenant_id, snapshot_id)
        except (EvidenceBoundaryError, LookupError, StopIteration):
            return False
        if snapshot.snapshot_schema_version != 2:
            return False
        try:
            current = self._snapshot_evidence(tenant_id, snapshot.case_id, as_of=as_of)
        except (EvidenceBoundaryError, KeyError, LookupError):
            return False
        stored = snapshot.canonical_snapshot_payload["evidence"]
        return canonical_digest(current) == canonical_digest(stored)

    def references(
        self, *, tenant_id: UUID, case_id: UUID
    ) -> tuple[EvidenceReference, ...]:
        self._spine.get_case(tenant_id=tenant_id, case_id=case_id)
        with self._lock:
            return tuple(self._references.get((tenant_id, case_id), ()))

    def _require_current_snapshot_for_case(
        self, *, tenant_id: UUID, case_id: UUID, snapshot_id: UUID
    ) -> CaseSnapshot:
        if not self._spine.is_snapshot_current(
            tenant_id=tenant_id, snapshot_id=snapshot_id
        ):
            raise EvidenceBoundaryError("a current CaseSnapshot is required")
        snapshot = self._spine._find_snapshot(tenant_id, snapshot_id)
        if snapshot.case_id != case_id:
            raise EvidenceBoundaryError("snapshot does not belong to the case")
        return snapshot

    def _require_server_bounded_command_time(self, occurred_at: datetime) -> None:
        normalize_timestamp(occurred_at)
        server_time = self._spine._clock()
        normalize_timestamp(server_time)
        if abs(occurred_at - server_time) > MAX_EVIDENCE_CLOCK_SKEW:
            raise EvidenceBoundaryError(
                "command time is outside server clock tolerance"
            )

    def _validate_resolution(
        self,
        resolution: EvidenceAuthorityResolution,
        *,
        tenant_id: UUID,
        case_id: UUID,
        purpose: str,
        as_of: datetime,
    ) -> None:
        subject_id, subject_digest = self._subject_authority.resolve_subject(
            tenant_id=tenant_id, case_id=case_id
        )
        if resolution.tenant_id != tenant_id:
            raise EvidenceBoundaryError("canonical evidence tenant mismatch")
        if resolution.case_id != case_id:
            raise EvidenceBoundaryError("canonical evidence case mismatch")
        if (
            resolution.subject_id != subject_id
            or resolution.subject_digest != subject_digest
        ):
            raise EvidenceBoundaryError("canonical evidence subject mismatch")
        if resolution.consent_purpose != purpose:
            raise EvidenceBoundaryError("canonical consent purpose mismatch")
        usability, reason = resolution.current_usability(as_of=as_of)
        if usability is not EvidenceUsability.USABLE:
            suffix = reason.value if reason is not None else "UNKNOWN"
            raise EvidenceBoundaryError(f"canonical evidence is unusable: {suffix}")

    def _snapshot_evidence(
        self, tenant_id: UUID, case_id: UUID, *, as_of: datetime
    ) -> dict[str, object]:
        references = self.references(tenant_id=tenant_id, case_id=case_id)
        try:
            current_subject_id, current_subject_digest = (
                self._subject_authority.resolve_subject(
                    tenant_id=tenant_id, case_id=case_id
                )
            )
        except (KeyError, LookupError) as exc:
            raise EvidenceBoundaryError(
                "authoritative case subject is unavailable"
            ) from exc
        accepted: list[dict[str, object]] = []
        unusable: list[dict[str, object]] = []
        consent_refs: set[tuple[str, str, str]] = set()
        source_refs: set[tuple[str, str, str, str]] = set()
        for reference in references:
            resolution = self._evidence_authority.revalidate(reference, as_of=as_of)
            binding_matches = (
                resolution.tenant_id == reference.tenant_id
                and resolution.case_id == reference.case_id
                and reference.subject_id == current_subject_id
                and reference.subject_digest == current_subject_digest
                and resolution.subject_id == reference.subject_id
                and resolution.subject_digest == reference.subject_digest
                and resolution.authority_digest() == reference.authority_digest
            )
            usability, reason = resolution.current_usability(as_of=as_of)
            item = reference.canonical_record()
            historical_reason = self._unusable_references.get(
                (tenant_id, case_id, reference.reference_id)
            )
            consent_inactive_reason = self._inactive_consents.get(
                (
                    tenant_id,
                    case_id,
                    reference.consent_namespace,
                    reference.consent_id,
                )
            )
            if (
                binding_matches
                and usability is EvidenceUsability.USABLE
                and historical_reason is None
                and consent_inactive_reason is None
            ):
                accepted.append(item)
            else:
                item = dict(item)
                item["unusable_reason"] = (
                    historical_reason
                    or consent_inactive_reason
                    or (reason.value if reason is not None else None)
                    or "AUTHORITY_REFERENCE_CHANGED"
                )
                unusable.append(item)
            consent_refs.add(
                (
                    reference.consent_namespace,
                    reference.consent_id,
                    reference.consent_version,
                )
            )
            source_refs.add(
                (
                    reference.source_id,
                    reference.source_attestation_id,
                    reference.source_attestation_version,
                    reference.source_registry_digest,
                )
            )
        accepted.sort(key=lambda item: str(item["reference_id"]))
        unusable.sort(key=lambda item: str(item["reference_id"]))
        state_version = self._state_versions.get((tenant_id, case_id), 0)
        state_records = [reference.canonical_record() for reference in references]
        state_records.sort(key=lambda item: str(item["reference_id"]))
        state_projection = {
            "accepted_reference_ids": [item["reference_id"] for item in accepted],
            "unusable_references": [
                {
                    "reference_id": item["reference_id"],
                    "reason": item["unusable_reason"],
                }
                for item in unusable
            ],
            "evidence_state_version": state_version,
            "references": state_records,
        }
        return {
            "accepted_evidence_refs": accepted,
            "unusable_evidence_refs": unusable,
            "consent_refs": [
                {"namespace": namespace, "consent_id": consent_id, "version": version}
                for namespace, consent_id, version in sorted(consent_refs)
            ],
            "source_attestation_refs": [
                {
                    "source_id": source_id,
                    "attestation_id": attestation_id,
                    "attestation_version": version,
                    "registry_digest": digest,
                }
                for source_id, attestation_id, version, digest in sorted(source_refs)
            ],
            "evidence_state_version": state_version,
            "evidence_state_digest": canonical_digest(state_projection),
        }

    def _find_reference(
        self, tenant_id: UUID, case_id: UUID, reference_id: UUID
    ) -> EvidenceReference:
        for reference in self.references(tenant_id=tenant_id, case_id=case_id):
            if reference.reference_id == reference_id:
                return reference
        raise EvidenceBoundaryError("evidence reference was not found")
