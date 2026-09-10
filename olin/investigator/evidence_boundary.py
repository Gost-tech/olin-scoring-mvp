"""Bounded commands joining canonical evidence authority to the case spine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from .actor import ActorContext
from .authority import RuntimeDatabaseCustody
from .canonical import canonical_digest, normalize_timestamp
from .events import EventType
from .evidence import (
    CALLER_INDEPENDENCE_LABELS,
    CALLER_TRUST_LABELS,
    EVIDENCE_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    MAX_EVIDENCE_CLOCK_SKEW,
    SEMANTIC_INDEPENDENCE_SCHEMA_VERSION,
    EvidenceAuthority,
    EvidenceAuthorityResolution,
    EvidenceBoundaryError,
    EvidenceReference,
    EvidenceUsability,
    IndependenceStatus,
    LineageRelation,
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


@dataclass(frozen=True, slots=True, init=False)
class ReasoningReadySnapshot:
    """Opaque, immutable result issued only after live semantic revalidation."""

    tenant_id: UUID
    case_id: UUID
    snapshot_id: UUID
    snapshot_digest: str
    authority_state_digest: str
    evidence_state_digest: str
    authority_revision: int
    canonical_projection_version: str
    checked_at: datetime
    evidence_references: tuple[EvidenceReference, ...]
    _consumed: bool = field(repr=False, compare=False)
    _connection: object | None = field(repr=False, compare=False)
    _transaction_id: str | None = field(repr=False, compare=False)
    _backend_pid: int | None = field(repr=False, compare=False)

    def __new__(cls):
        raise TypeError(
            "ReasoningReadySnapshot can only be issued by the currentness gate"
        )

    @classmethod
    def _issue(
        cls,
        *,
        snapshot: CaseSnapshot,
        authority_state_digest: str,
        checked_at: datetime,
        evidence_references: tuple[EvidenceReference, ...],
        issuer: object,
    ) -> ReasoningReadySnapshot:
        return cls._issue_values(
            tenant_id=snapshot.tenant_id,
            case_id=snapshot.case_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_digest=snapshot.canonical_digest,
            authority_state_digest=authority_state_digest,
            evidence_state_digest=authority_state_digest,
            authority_revision=0,
            canonical_projection_version="in-memory-authority-1",
            checked_at=checked_at,
            evidence_references=evidence_references,
            connection=None,
            transaction_id=None,
            backend_pid=None,
            issuer=issuer,
        )

    @classmethod
    def _issue_values(
        cls,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        snapshot_digest: str,
        authority_state_digest: str,
        evidence_state_digest: str,
        authority_revision: int,
        canonical_projection_version: str,
        checked_at: datetime,
        evidence_references: tuple[EvidenceReference, ...],
        connection: object | None,
        transaction_id: str | None,
        backend_pid: int | None,
        issuer: object,
    ) -> ReasoningReadySnapshot:
        if issuer is not _REASONING_GATE_ISSUER:
            raise TypeError("reasoning-ready snapshots require the authoritative gate")
        instance = object.__new__(cls)
        object.__setattr__(instance, "tenant_id", tenant_id)
        object.__setattr__(instance, "case_id", case_id)
        object.__setattr__(instance, "snapshot_id", snapshot_id)
        object.__setattr__(instance, "snapshot_digest", snapshot_digest)
        object.__setattr__(instance, "authority_state_digest", authority_state_digest)
        object.__setattr__(instance, "evidence_state_digest", evidence_state_digest)
        object.__setattr__(instance, "authority_revision", authority_revision)
        object.__setattr__(
            instance, "canonical_projection_version", canonical_projection_version
        )
        object.__setattr__(instance, "checked_at", checked_at)
        object.__setattr__(instance, "evidence_references", evidence_references)
        object.__setattr__(instance, "_consumed", False)
        object.__setattr__(instance, "_connection", connection)
        object.__setattr__(instance, "_transaction_id", transaction_id)
        object.__setattr__(instance, "_backend_pid", backend_pid)
        return instance

    def consume(self, consumer):
        """Pass this capability to a future reasoning consumer exactly once."""
        if not callable(consumer):
            raise TypeError("reasoning consumer must be callable")
        if self._consumed:
            raise EvidenceBoundaryError(
                "reasoning-ready capability was already consumed"
            )
        if self._connection is not None:
            status = getattr(
                getattr(self._connection, "info", None), "transaction_status", None
            )
            if status is not None and getattr(status, "name", "") != "INTRANS":
                raise EvidenceBoundaryError(
                    "reasoning-ready capability escaped its issuing transaction"
                )
            try:
                transaction = self._connection.execute(
                    "SELECT pg_backend_pid(), pg_current_xact_id()::text"
                ).fetchone()
            except Exception as error:
                object.__setattr__(self, "_consumed", True)
                raise EvidenceBoundaryError(
                    "reasoning-ready transaction is no longer usable"
                ) from error
            if transaction is None or tuple(transaction) != (
                self._backend_pid,
                self._transaction_id,
            ):
                object.__setattr__(self, "_consumed", True)
                raise EvidenceBoundaryError(
                    "reasoning-ready capability transaction does not match"
                )
        object.__setattr__(self, "_consumed", True)
        result = consumer(self)
        if self._connection is not None:
            status = getattr(
                getattr(self._connection, "info", None), "transaction_status", None
            )
            if status is not None and getattr(status, "name", "") != "INTRANS":
                raise EvidenceBoundaryError(
                    "reasoning consumer ended its authoritative transaction"
                )
        return result

    def __reduce__(self):
        raise TypeError("reasoning-ready capabilities cannot be serialized")


_REASONING_GATE_ISSUER = object()


class PostgresReasoningSnapshotGate:
    """Durable implementation of the sole reasoning-currentness contract."""

    def __init__(
        self,
        *,
        runtime_connection: object,
        evidence_authority: EvidenceAuthority,
        runtime_custody: RuntimeDatabaseCustody,
    ) -> None:
        module = type(runtime_connection).__module__
        if not (module == "psycopg" or module.startswith(("psycopg.", "psycopg2"))):
            raise EvidenceBoundaryError(
                "durable reasoning currentness requires PostgreSQL"
            )
        if not isinstance(runtime_custody, RuntimeDatabaseCustody):
            raise TypeError("runtime_custody must be an established database guard")
        self._connection = runtime_connection
        self._evidence_authority = evidence_authority
        self._runtime_custody = runtime_custody

    @staticmethod
    def _timestamp(value: object, field: str) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as error:
                raise EvidenceBoundaryError(
                    f"snapshot {field} timestamp is invalid"
                ) from error
        normalize_timestamp(parsed)
        return parsed

    def require_snapshot_current_for_reasoning(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        as_of: datetime,
    ) -> ReasoningReadySnapshot:
        """Revalidate inside a current, read-only transaction-scoped case lock."""
        transaction_status = getattr(
            getattr(self._connection, "info", None), "transaction_status", None
        )
        if transaction_status is not None and (
            getattr(transaction_status, "name", "") != "INTRANS"
        ):
            raise EvidenceBoundaryError(
                "durable reasoning requires an explicitly open transaction"
            )
        # Bound lock retention and authority revalidation; transaction-scoped so
        # pooled connections cannot carry these limits into unrelated work.
        self._connection.execute(
            "SET LOCAL statement_timeout = '5000ms'; "
            "SET LOCAL lock_timeout = '1000ms'; "
            "SET LOCAL idle_in_transaction_session_timeout = '5000ms'"
        )
        self._runtime_custody.require_connection(self._connection)
        normalize_timestamp(as_of)
        mode = self._connection.execute(
            "SELECT current_setting('transaction_read_only') = 'on', "
            "current_setting('transaction_isolation') = 'read committed'"
        ).fetchone()
        if mode is None or tuple(mode) != (True, True):
            raise EvidenceBoundaryError(
                "durable reasoning requires a read-only read-committed transaction"
            )
        self._connection.execute(
            "SELECT pg_advisory_xact_lock_shared(hashtextextended("  # nosec B608
            "%s::text || ':reasoning-currentness:' || %s::text,0))",
            (tenant_id, case_id),
        ).fetchone()
        row = self._connection.execute(
            "SELECT snapshot.canonical_snapshot_payload, "
            "snapshot.canonical_digest, "
            "investigator.is_snapshot_current(%s,%s), "
            "current_setting('transaction_read_only') = 'on', "
            "current_setting('transaction_isolation') = 'read committed', "
            "abs(extract(epoch FROM (statement_timestamp() - %s))) <= 300, "
            "statement_timestamp(), canonical.authority_revision, "
            "canonical.authority_state_digest, pg_backend_pid(), "
            "pg_current_xact_id()::text "
            "FROM investigator.case_snapshot snapshot "
            "CROSS JOIN LATERAL "
            "investigator.current_canonical_authority_revision(%s,%s) canonical "
            "WHERE snapshot.tenant_id=%s AND snapshot.case_id=%s "
            "AND snapshot.snapshot_id=%s AND snapshot.snapshot_schema_version=2",
            (
                tenant_id,
                snapshot_id,
                as_of,
                tenant_id,
                case_id,
                tenant_id,
                case_id,
                snapshot_id,
            ),
        ).fetchone()
        if row is None:
            raise EvidenceBoundaryError(
                "durable snapshot tenant, case, identity, or schema is invalid"
            )
        (
            payload,
            stored_digest,
            structurally_current,
            read_only,
            stable,
            bounded,
            server_time_value,
            authority_revision,
            current_authority_digest,
            backend_pid,
            transaction_id,
        ) = row
        if not structurally_current:
            raise EvidenceBoundaryError("snapshot is not structurally current")
        if not read_only or not stable:
            raise EvidenceBoundaryError(
                "durable reasoning requires a read-only read-committed transaction"
            )
        if not bounded:
            raise EvidenceBoundaryError(
                "command time is outside server clock tolerance"
            )
        current_time = self._timestamp(server_time_value, "server")
        if not isinstance(payload, Mapping):
            raise EvidenceBoundaryError("durable snapshot payload is malformed")
        if canonical_digest(payload) != stored_digest:
            raise EvidenceBoundaryError("durable snapshot digest is invalid")
        if payload.get("snapshot_schema_version") != 2:
            raise EvidenceBoundaryError("snapshot schema is unsupported for reasoning")
        versions = payload.get("applicable_versions", {})
        if not isinstance(versions, Mapping) or (
            versions.get("evidence_reference")
            != f"investigator-evidence-reference-{EVIDENCE_REFERENCE_SCHEMA_VERSION}"
            or versions.get("evidence_resolver") != EVIDENCE_RESOLVER_CONTRACT_VERSION
            or versions.get("semantic_independence")
            != f"investigator-evidence-semantics-{SEMANTIC_INDEPENDENCE_SCHEMA_VERSION}"
        ):
            raise EvidenceBoundaryError(
                "snapshot evidence contract is unsupported for reasoning"
            )
        case_record = payload.get("case", {})
        if not isinstance(case_record, Mapping) or (
            case_record.get("tenant_id") != str(tenant_id)
            or case_record.get("case_id") != str(case_id)
        ):
            raise EvidenceBoundaryError("snapshot tenant or case payload is mismatched")
        evidence = payload.get("evidence", {})
        if not isinstance(evidence, Mapping):
            raise EvidenceBoundaryError("snapshot evidence payload is malformed")
        canonical_authority = payload.get("canonical_authority", {})
        if not isinstance(canonical_authority, Mapping) or (
            canonical_authority.get("projection_version")
            != "canonical-evidence-projection-1"
            or canonical_authority.get("authority_revision") != authority_revision
            or canonical_authority.get("authority_state_digest")
            != current_authority_digest
        ):
            raise EvidenceBoundaryError(
                "snapshot canonical authority revision is stale"
            )
        accepted = evidence.get("accepted_evidence_refs")
        unusable = evidence.get("unusable_evidence_refs")
        if not isinstance(accepted, (list, tuple)) or not isinstance(
            unusable, (list, tuple)
        ):
            raise EvidenceBoundaryError("snapshot evidence collections are malformed")
        successors = {
            item.get("acceptance", {}).get("supersedes_reference_id")
            for item in accepted
            if isinstance(item, Mapping) and isinstance(item.get("acceptance"), Mapping)
        }
        for item in unusable:
            if not isinstance(item, Mapping) or (
                item.get("unusable_reason") != "EVIDENCE_SUPERSEDED"
                or item.get("reference_id") not in successors
            ):
                raise EvidenceBoundaryError(
                    "snapshot contains unusable current evidence authority"
                )
        references: list[EvidenceReference] = []
        for item in accepted:
            if not isinstance(item, Mapping):
                raise EvidenceBoundaryError("accepted evidence reference is malformed")
            artifact = item.get("artifact", {})
            consent = item.get("consent", {})
            acceptance = item.get("acceptance", {})
            if not all(
                isinstance(value, Mapping) for value in (artifact, consent, acceptance)
            ):
                raise EvidenceBoundaryError("accepted evidence reference is malformed")
            resolution = self._evidence_authority.resolve(
                tenant_id=tenant_id,
                case_id=case_id,
                evidence_namespace=str(artifact.get("evidence_namespace", "")),
                evidence_id=str(artifact.get("evidence_id", "")),
                purpose=str(consent.get("consent_purpose", "")),
                as_of=current_time,
            )
            if resolution.current_usability(as_of=current_time) != (
                EvidenceUsability.USABLE,
                None,
            ):
                raise EvidenceBoundaryError(
                    "snapshot evidence authority is no longer usable"
                )
            reference = EvidenceReference.from_resolution(
                reference_id=UUID(str(item.get("reference_id"))),
                resolution=resolution,
                supersedes_reference_id=(
                    UUID(str(acceptance["supersedes_reference_id"]))
                    if acceptance.get("supersedes_reference_id")
                    else None
                ),
                accepted_at=self._timestamp(
                    acceptance.get("accepted_at"), "accepted_at"
                ),
            )
            if reference.canonical_record() != dict(item):
                raise EvidenceBoundaryError("snapshot semantic authority is stale")
            if (
                reference.semantic_independence_schema_version
                != SEMANTIC_INDEPENDENCE_SCHEMA_VERSION
            ):
                raise EvidenceBoundaryError(
                    "snapshot lacks current semantic independence authority"
                )
            references.append(reference)
        return ReasoningReadySnapshot._issue_values(
            tenant_id=tenant_id,
            case_id=case_id,
            snapshot_id=snapshot_id,
            snapshot_digest=str(stored_digest),
            authority_state_digest=str(current_authority_digest),
            evidence_state_digest=str(evidence.get("evidence_state_digest", "")),
            authority_revision=int(authority_revision),
            canonical_projection_version="canonical-evidence-projection-1",
            checked_at=current_time,
            evidence_references=tuple(references),
            connection=self._connection,
            transaction_id=str(transaction_id),
            backend_pid=int(backend_pid),
            issuer=_REASONING_GATE_ISSUER,
        )

    def consume_snapshot_current_for_reasoning(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        as_of: datetime,
        consumer,
    ):
        """Validate and consume readiness inside one server-controlled transaction."""
        status = getattr(
            getattr(self._connection, "info", None), "transaction_status", None
        )
        if status is not None and getattr(status, "name", "") != "IDLE":
            raise EvidenceBoundaryError(
                "reasoning transaction must start from an idle connection"
            )
        with self._connection.transaction():
            self._connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
            )
            ready = self.require_snapshot_current_for_reasoning(
                tenant_id=tenant_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                as_of=as_of,
            )
            return ready.consume(consumer)


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
        runtime_custody: RuntimeDatabaseCustody,
        uuid_factory=uuid4,
    ) -> None:
        self._spine = spine
        self._evidence_authority = evidence_authority
        self._subject_authority = subject_authority
        if not isinstance(runtime_custody, RuntimeDatabaseCustody):
            raise TypeError("runtime_custody must be an established database guard")
        self._runtime_custody = runtime_custody
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
        _ = frozenset(submitted_claims or {}) & (
            CALLER_TRUST_LABELS | CALLER_INDEPENDENCE_LABELS
        )
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
                if (
                    resolution.semantic_lineage_id != prior.semantic_lineage_id
                    or resolution.lineage_relation is not LineageRelation.CORRECTION
                    or resolution.derived_from_evidence_namespace
                    != prior.evidence_namespace
                    or resolution.derived_from_evidence_id != prior.evidence_id
                    or resolution.derived_from_evidence_version
                    != prior.evidence_version
                ):
                    raise EvidenceBoundaryError(
                        "correction must preserve canonical semantic lineage and parent"
                    )
            elif resolution.lineage_relation is LineageRelation.CORRECTION:
                raise EvidenceBoundaryError(
                    "correction requires an existing superseded evidence reference"
                )
            if resolution.lineage_relation is LineageRelation.DERIVED_COPY:
                parent = next(
                    (
                        item
                        for item in references
                        if item.evidence_namespace
                        == resolution.derived_from_evidence_namespace
                        and item.evidence_id == resolution.derived_from_evidence_id
                        and item.evidence_version
                        == resolution.derived_from_evidence_version
                    ),
                    None,
                )
                if (
                    parent is None
                    or parent.semantic_lineage_id != resolution.semantic_lineage_id
                ):
                    raise EvidenceBoundaryError(
                        "derived copy requires an existing parent in the same lineage"
                    )
            same_lineage = next(
                (
                    item
                    for item in references
                    if item.semantic_lineage_id == resolution.semantic_lineage_id
                ),
                None,
            )
            if (
                same_lineage is not None
                and resolution.independence_status
                is IndependenceStatus.INDEPENDENT_VERIFIED
            ):
                raise EvidenceBoundaryError(
                    "the same semantic lineage cannot become independent support"
                )
            if (
                resolution.independence_status
                is IndependenceStatus.INDEPENDENT_VERIFIED
            ):
                reused_basis = next(
                    (
                        item
                        for item in references
                        if item.independence_status
                        is IndependenceStatus.INDEPENDENT_VERIFIED
                        and (
                            item.independence_attestation_id
                            == resolution.independence_attestation_id
                            or (
                                resolution.economic_event_id is not None
                                and item.economic_event_id
                                == resolution.economic_event_id
                                and item.upstream_issuer_id
                                == resolution.upstream_issuer_id
                            )
                        )
                    ),
                    None,
                )
                if reused_basis is not None:
                    raise EvidenceBoundaryError(
                        "verified independence basis cannot be reused as new support"
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
        current_time = self._require_server_bounded_command_time(as_of)
        evidence = self._snapshot_evidence(tenant_id, case_id, as_of=current_time)
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
            self.require_snapshot_current_for_reasoning(
                tenant_id=tenant_id,
                case_id=self._spine._find_snapshot(tenant_id, snapshot_id).case_id,
                snapshot_id=snapshot_id,
                as_of=as_of,
            )
        except (EvidenceBoundaryError, KeyError, LookupError, StopIteration):
            return False
        return True

    def require_snapshot_current_for_reasoning(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        as_of: datetime,
    ) -> ReasoningReadySnapshot:
        """Fail closed and issue the sole future reasoning input type."""
        # Evidence commands already acquire these locks in this order. Holding
        # both through issuance makes structural state, evidence state, and the
        # returned capability one atomic in-memory observation.
        with self._lock, self._spine._lock:
            return self._require_snapshot_current_for_reasoning_locked(
                tenant_id=tenant_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                as_of=as_of,
            )

    def _require_snapshot_current_for_reasoning_locked(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        snapshot_id: UUID,
        as_of: datetime,
    ) -> ReasoningReadySnapshot:
        self._runtime_custody.require_current()
        current_time = self._require_server_bounded_command_time(as_of)
        try:
            structurally_current = self._spine.is_snapshot_current(
                tenant_id=tenant_id, snapshot_id=snapshot_id
            )
            snapshot = self._spine._find_snapshot(tenant_id, snapshot_id)
        except LookupError as error:
            raise EvidenceBoundaryError(
                "snapshot is not structurally current"
            ) from error
        if not structurally_current:
            raise EvidenceBoundaryError("snapshot is not structurally current")
        if snapshot.case_id != case_id:
            raise EvidenceBoundaryError("snapshot does not belong to the case")
        if snapshot.snapshot_schema_version != 2:
            raise EvidenceBoundaryError("snapshot schema is unsupported for reasoning")
        versions = snapshot.canonical_snapshot_payload.get("applicable_versions", {})
        if (
            versions.get("evidence_reference")
            != f"investigator-evidence-reference-{EVIDENCE_REFERENCE_SCHEMA_VERSION}"
            or versions.get("evidence_resolver") != EVIDENCE_RESOLVER_CONTRACT_VERSION
            or versions.get("semantic_independence")
            != f"investigator-evidence-semantics-{SEMANTIC_INDEPENDENCE_SCHEMA_VERSION}"
        ):
            raise EvidenceBoundaryError(
                "snapshot evidence contract is unsupported for reasoning"
            )
        current = self._snapshot_evidence(tenant_id, case_id, as_of=current_time)
        stored = snapshot.canonical_snapshot_payload["evidence"]
        if canonical_digest(current) != canonical_digest(stored):
            raise EvidenceBoundaryError("snapshot semantic authority is stale")
        accepted_ids = {
            item["reference_id"] for item in current["accepted_evidence_refs"]
        }
        all_references = self.references(tenant_id=tenant_id, case_id=case_id)
        references = tuple(
            reference
            for reference in all_references
            if str(reference.reference_id) in accepted_ids
        )
        if len(references) != len(accepted_ids) or any(
            reference.semantic_independence_schema_version
            != SEMANTIC_INDEPENDENCE_SCHEMA_VERSION
            for reference in references
        ):
            raise EvidenceBoundaryError(
                "snapshot lacks current semantic independence authority"
            )
        accepted_successors = {
            str(reference.supersedes_reference_id)
            for reference in references
            if reference.supersedes_reference_id is not None
        }
        for unusable in current["unusable_evidence_refs"]:
            if (
                unusable["unusable_reason"] != "EVIDENCE_SUPERSEDED"
                or unusable["reference_id"] not in accepted_successors
            ):
                raise EvidenceBoundaryError(
                    "snapshot contains unusable current evidence authority"
                )
        return ReasoningReadySnapshot._issue(
            snapshot=snapshot,
            authority_state_digest=str(current["evidence_state_digest"]),
            checked_at=current_time,
            evidence_references=references,
            issuer=_REASONING_GATE_ISSUER,
        )

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

    def _require_server_bounded_command_time(self, occurred_at: datetime) -> datetime:
        normalize_timestamp(occurred_at)
        server_time = self._spine._clock()
        normalize_timestamp(server_time)
        if abs(occurred_at - server_time) > MAX_EVIDENCE_CLOCK_SKEW:
            raise EvidenceBoundaryError(
                "command time is outside server clock tolerance"
            )
        return server_time

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
