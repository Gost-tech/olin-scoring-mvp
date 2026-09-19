"""Loopback-only development operator for fixed synthetic Investigator evidence.

This process is deliberately separate from the analyst runtime.  It owns the
development evidence-authority credential and accepts only closed fixtures; it
is not a generic upload or verification API.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID, uuid4

from .investigator.canonical import normalize_timestamp
from .investigator.claims import MERCHANT_ASSERTION_PROFILE
from .investigator.evidence import (
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    EvidenceAuthorityResolution,
    EvidenceReference,
    EvidenceUsability,
)

MAX_BODY_BYTES = 16_384
CANONICAL_REFERENCE_FIELDS = (
    "tenant_id",
    "case_id",
    "subject_id",
    "subject_digest",
    "evidence_namespace",
    "evidence_id",
    "evidence_version",
    "artifact_digest",
    "authority_digest",
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
    "integrity_valid",
    "integrity_reference",
    "resolver_version",
)


def _semantics(
    lineage: str,
    issuer: str,
    *,
    economic_event_id: str | None,
) -> dict[str, object]:
    return {
        "semantic_schema_version": 1,
        "semantic_lineage_id": lineage,
        "lineage_relation": "ORIGINAL",
        "derived_from_evidence_namespace": None,
        "derived_from_evidence_id": None,
        "derived_from_evidence_version": None,
        "economic_event_id": economic_event_id,
        "upstream_issuer_id": issuer,
        "independence_status": "INDEPENDENCE_UNKNOWN",
        "independence_attestation_id": None,
        "independence_attestation_version": None,
    }


def _resolution(
    *,
    tenant_id: UUID,
    case_id: UUID,
    reference_id: UUID,
    subject_id: str,
    subject_digest: str,
    evidence_id: str,
    evidence_class: str,
    verification_status: str,
    proposition_type: str,
    proposition_value: str,
    proposition_unit: str,
    verification_method: str,
    period_start: datetime,
    period_end: datetime,
    source_id: str,
    issuer_id: str,
    source_class: str,
    acquisition_method: str,
    semantics: dict[str, object],
    now: datetime,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    artifact_digest = sha256(
        f"{tenant_id}:{case_id}:{evidence_id}:{proposition_type}:{proposition_value}".encode()
    ).hexdigest()
    resolved = EvidenceAuthorityResolution._from_authoritative_adapter(
        tenant_id=tenant_id,
        case_id=case_id,
        subject_id=subject_id,
        subject_digest=subject_digest,
        evidence_namespace="evidence_passport",
        evidence_id=evidence_id,
        evidence_version="1",
        artifact_digest=artifact_digest,
        evidence_class=evidence_class,
        lifecycle="ACCEPTED",
        verification_status=verification_status,
        proposition_type=proposition_type,
        proposition_schema_version=1,
        proposition_value=proposition_value,
        proposition_unit=proposition_unit,
        verification_method=verification_method,
        period_start=period_start,
        period_end=period_end,
        observed_at=period_end,
        evidence_expires_at=now + timedelta(days=30),
        source_id=source_id,
        issuer_id=issuer_id,
        acquisition_method=acquisition_method,
        source_class=source_class,
        source_attestation_id=f"attestation-{evidence_id}",
        source_attestation_version="1",
        source_registry_digest=sha256(b"phase5a-synthetic-source-registry").hexdigest(),
        source_valid_until=now + timedelta(days=90),
        production_qualified_source=True,
        source_allows_proposition=True,
        consent_namespace="synthetic_case_consent",
        consent_id=f"consent-{case_id}",
        consent_version="1",
        consent_purpose="investigator_analysis",
        consent_data_class="synthetic_economic_evidence",
        consent_use_scope="case_evidence_analysis",
        consent_status="ACTIVE",
        consent_expires_at=now + timedelta(days=30),
        retention_until=now + timedelta(days=60),
        integrity_reference=f"integrity-{evidence_id}",
        integrity_valid=True,
        usability=EvidenceUsability.USABLE,
        unusable_reason=None,
        resolver_version=EVIDENCE_RESOLVER_CONTRACT_VERSION,
        resolved_at=now,
        semantic_independence_schema_version=1,
        semantic_lineage_id=semantics["semantic_lineage_id"],
        lineage_relation=semantics["lineage_relation"],
        derived_from_evidence_namespace=None,
        derived_from_evidence_id=None,
        derived_from_evidence_version=None,
        economic_event_id=semantics["economic_event_id"],
        upstream_issuer_id=semantics["upstream_issuer_id"],
        independence_status=semantics["independence_status"],
        independence_attestation_id=None,
        independence_attestation_version=None,
    )
    reference = EvidenceReference.from_resolution(
        reference_id=reference_id,
        resolution=resolved,
        supersedes_reference_id=None,
        accepted_at=now,
    )
    flat = {
        "tenant_id": str(tenant_id),
        "case_id": str(case_id),
        "subject_id": resolved.subject_id,
        "subject_digest": resolved.subject_digest,
        "evidence_namespace": resolved.evidence_namespace,
        "evidence_id": resolved.evidence_id,
        "evidence_version": resolved.evidence_version,
        "artifact_digest": resolved.artifact_digest,
        "authority_digest": resolved.authority_digest(),
        "evidence_class": resolved.evidence_class.value,
        "lifecycle": resolved.lifecycle.value,
        "verification_status": resolved.verification_status.value,
        "proposition_type": resolved.proposition_type,
        "proposition_schema_version": resolved.proposition_schema_version,
        "proposition_value": resolved.proposition_value,
        "proposition_unit": resolved.proposition_unit,
        "verification_method": resolved.verification_method,
        "period_start": normalize_timestamp(resolved.period_start),
        "period_end": normalize_timestamp(resolved.period_end),
        "observed_at": normalize_timestamp(resolved.observed_at),
        "evidence_expires_at": normalize_timestamp(resolved.evidence_expires_at),
        "source_id": resolved.source_id,
        "issuer_id": resolved.issuer_id,
        "acquisition_method": resolved.acquisition_method,
        "source_class": resolved.source_class,
        "source_attestation_id": resolved.source_attestation_id,
        "source_attestation_version": resolved.source_attestation_version,
        "source_registry_digest": resolved.source_registry_digest,
        "source_valid_until": normalize_timestamp(resolved.source_valid_until),
        "production_qualified_source": resolved.production_qualified_source,
        "source_allows_proposition": resolved.source_allows_proposition,
        "consent_namespace": resolved.consent_namespace,
        "consent_id": resolved.consent_id,
        "consent_version": resolved.consent_version,
        "consent_purpose": resolved.consent_purpose,
        "consent_data_class": resolved.consent_data_class,
        "consent_use_scope": resolved.consent_use_scope,
        "consent_status": resolved.consent_status,
        "consent_expires_at": normalize_timestamp(resolved.consent_expires_at),
        "retention_until": normalize_timestamp(resolved.retention_until),
        "integrity_valid": resolved.integrity_valid,
        "integrity_reference": resolved.integrity_reference,
        "resolver_version": resolved.resolver_version,
        "reference_id": str(reference.reference_id),
        "accepted_at": normalize_timestamp(reference.accepted_at),
        "supersedes_reference_id": None,
    }
    canonical_reference = {field: flat[field] for field in CANONICAL_REFERENCE_FIELDS}
    projection = {
        "projection_version": "canonical-evidence-projection-1",
        "authority_digest": flat["authority_digest"],
        "canonical_reference": canonical_reference,
        **canonical_reference,
        "reference_id": flat["reference_id"],
        "accepted_at": flat["accepted_at"],
        "supersedes_reference_id": None,
        "semantic_independence_schema_version": 1,
        "semantic_lineage_id": semantics["semantic_lineage_id"],
        "lineage_relation": semantics["lineage_relation"],
        "derived_from_evidence_namespace": None,
        "derived_from_evidence_id": None,
        "derived_from_evidence_version": None,
        "economic_event_id": semantics["economic_event_id"],
        "upstream_issuer_id": semantics["upstream_issuer_id"],
        "independence_status": semantics["independence_status"],
        "independence_attestation_id": None,
        "independence_attestation_version": None,
        "usability": "USABLE",
        "unusable_reason": None,
    }
    if reference.authority_digest != flat["authority_digest"]:
        raise RuntimeError("synthetic authority record is inconsistent")
    return flat, semantics, projection


class SyntheticEvidenceOperator:
    def __init__(self, runtime_connect, authority_connect) -> None:
        self._runtime_connect = runtime_connect
        self._authority_connect = authority_connect

    @staticmethod
    def _runtime_context(
        connection: Any, tenant_id: UUID, *, read_only: bool = False
    ) -> None:
        if read_only:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
            )
        else:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE"
            )
        connection.execute("SET LOCAL ROLE olin_investigator_runtime")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)", (str(tenant_id),)
        )

    @staticmethod
    def _authority_context(connection: Any, tenant_id: UUID) -> None:
        connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
        connection.execute("SET LOCAL ROLE olin_investigator_evidence_authority")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)", (str(tenant_id),)
        )

    def _current(self, tenant_id: UUID, case_id: UUID) -> tuple[UUID, int, dict]:
        with closing(self._runtime_connect()) as connection, connection.transaction():
            self._runtime_context(connection, tenant_id, read_only=True)
            row = connection.execute(
                "SELECT snapshot.snapshot_id,stored_case.case_version,"
                "snapshot.canonical_snapshot_payload FROM investigator.case_snapshot snapshot "
                "JOIN investigator.investigation_case stored_case USING (tenant_id,case_id) "
                "WHERE snapshot.tenant_id=%s AND snapshot.case_id=%s "
                "AND snapshot.snapshot_schema_version=2 "
                "AND investigator.is_snapshot_current(%s,snapshot.snapshot_id) "
                "ORDER BY snapshot.created_at DESC LIMIT 1",
                (tenant_id, case_id, tenant_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("current synthetic case snapshot was not found")
        return UUID(str(row[0])), int(row[1]), row[2]

    def _latest_state(
        self, tenant_id: UUID, case_id: UUID
    ) -> tuple[UUID, int, dict, bool]:
        with closing(self._runtime_connect()) as connection, connection.transaction():
            self._runtime_context(connection, tenant_id, read_only=True)
            row = connection.execute(
                "SELECT snapshot.snapshot_id,stored_case.case_version,"
                "snapshot.canonical_snapshot_payload,"
                "investigator.is_snapshot_current(%s,snapshot.snapshot_id) "
                "FROM investigator.case_snapshot snapshot "
                "JOIN investigator.investigation_case stored_case USING (tenant_id,case_id) "
                "WHERE snapshot.tenant_id=%s AND snapshot.case_id=%s "
                "AND snapshot.snapshot_schema_version=2 "
                "ORDER BY snapshot.event_head_sequence DESC LIMIT 1",
                (tenant_id, tenant_id, case_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("synthetic case snapshot was not found")
        return UUID(str(row[0])), int(row[1]), row[2], bool(row[3])

    def _accepted_reference(
        self, tenant_id: UUID, case_id: UUID, evidence_id: str
    ) -> UUID | None:
        with closing(self._runtime_connect()) as connection, connection.transaction():
            self._runtime_context(connection, tenant_id, read_only=True)
            row = connection.execute(
                "SELECT reference_id FROM investigator.investigation_evidence_reference "
                "WHERE tenant_id=%s AND case_id=%s "
                "AND evidence_namespace='evidence_passport' AND evidence_id=%s "
                "AND lifecycle='ACCEPTED' ORDER BY accepted_at DESC LIMIT 1",
                (tenant_id, case_id, evidence_id),
            ).fetchone()
        return None if row is None else UUID(str(row[0]))

    def _create_current_snapshot(
        self, tenant_id: UUID, case_id: UUID, case_version: int, idempotency_key: str
    ) -> UUID:
        with closing(self._runtime_connect()) as runtime, runtime.transaction():
            self._runtime_context(runtime, tenant_id)
            return UUID(
                str(
                    runtime.execute(
                        "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                        (tenant_id, case_id, case_version, idempotency_key),
                    ).fetchone()[0]
                )
            )

    def useful_coverage(
        self, *, tenant_id: UUID, case_id: UUID, action_id: UUID, expected_revision: int
    ) -> dict:
        fixture_evidence_id = f"fixture-account-coverage-{action_id}"
        snapshot_id, case_version, payload, structurally_current = self._latest_state(
            tenant_id, case_id
        )
        existing_reference = self._accepted_reference(
            tenant_id, case_id, fixture_evidence_id
        )
        if existing_reference is not None:
            if not structurally_current:
                self._create_current_snapshot(
                    tenant_id,
                    case_id,
                    case_version,
                    f"phase5a-after-{action_id}",
                )
            current_snapshot, _, current_payload = self._current(tenant_id, case_id)
            return {
                "authority_revision": current_payload["canonical_authority"][
                    "authority_revision"
                ],
                "evidence_reference": str(existing_reference),
                "new_snapshot_id": str(current_snapshot),
                "outcome": "EVIDENCE_ACCEPTED",
                "synthetic": True,
                "replayed": True,
            }
        if not structurally_current:
            raise RuntimeError("synthetic case has no current pre-handoff snapshot")
        accepted = payload["evidence"]["accepted_evidence_refs"]
        bank = next(
            item
            for item in accepted
            if item["proposition_verification"]["proposition_type"]
            == "bank_visible_inflows"
        )
        now = datetime.now(timezone.utc)
        issuer = "fixture-bank-issuer"
        semantic = _semantics(
            f"phase5a-coverage-{action_id}",
            issuer,
            economic_event_id=f"coverage-{action_id}",
        )
        flat, semantics, projection = _resolution(
            tenant_id=tenant_id,
            case_id=case_id,
            reference_id=uuid4(),
            subject_id=bank["subject"]["subject_id"],
            subject_digest=bank["subject"]["subject_digest"],
            evidence_id=fixture_evidence_id,
            evidence_class="VERIFIED_FACT",
            verification_status="VERIFIED_FOR_PROPOSITION",
            proposition_type="bank_account_coverage",
            proposition_value="COMPLETE",
            proposition_unit="STATUS",
            verification_method="signed_provider_record_match",
            period_start=datetime.fromisoformat(
                bank["artifact"]["period_start"].replace("Z", "+00:00")
            ),
            period_end=datetime.fromisoformat(
                bank["artifact"]["period_end"].replace("Z", "+00:00")
            ),
            source_id="fixture_bank_registry",
            issuer_id=issuer,
            source_class="regulated_financial_institution",
            acquisition_method="synthetic_fixture",
            semantics=semantic,
            now=now,
        )
        with closing(self._authority_connect()) as authority, authority.transaction():
            self._authority_context(authority, tenant_id)
            revision = authority.execute(
                "SELECT authority_revision,authority_state_digest FROM evidence_authority."
                "commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(projection), expected_revision, "EVIDENCE_PROJECTED"),
            ).fetchone()
            authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(flat),
                    json.dumps(semantics),
                    snapshot_id,
                    case_version,
                    uuid4(),
                    f"phase5a-useful-{action_id}",
                ),
            ).fetchone()
        new_snapshot = self._create_current_snapshot(
            tenant_id, case_id, case_version + 1, f"phase5a-after-{action_id}"
        )
        return {
            "authority_revision": revision[0],
            "evidence_reference": flat["reference_id"],
            "new_snapshot_id": str(new_snapshot),
            "outcome": "EVIDENCE_ACCEPTED",
            "synthetic": True,
        }

    def setup_target_case(self, *, tenant_id: UUID, case_id: UUID) -> dict:
        """Idempotently create the reviewed 118k observation / 260k claim fixture."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=31)
        period_end = now - timedelta(days=1)
        with closing(self._runtime_connect()) as runtime, runtime.transaction():
            self._runtime_context(runtime, tenant_id)
            existing = runtime.execute(
                "SELECT case_version FROM investigator.investigation_case "
                "WHERE tenant_id=%s AND case_id=%s",
                (tenant_id, case_id),
            ).fetchone()
            if existing is None:
                empty_digest = sha256(b"{}").hexdigest()
                runtime.execute(
                    "SELECT investigator.create_case("
                    "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                    (
                        case_id,
                        tenant_id,
                        f"SYNTHETIC-PHASE5A-{case_id.hex}",
                        "phase5a-synthetic-demo",
                        uuid4(),
                        now,
                        "{}",
                        1,
                        f"phase5a-create-{case_id}",
                        empty_digest,
                        "{}",
                    ),
                )
                initial_snapshot = runtime.execute(
                    "SELECT snapshot_id FROM investigator.create_snapshot(%s,%s,%s,%s)",
                    (tenant_id, case_id, 1, f"phase5a-initial-{case_id}"),
                ).fetchone()[0]
            else:
                try:
                    snapshot_id, _, _ = self._current(tenant_id, case_id)
                    return {
                        "case_id": str(case_id),
                        "snapshot_id": str(snapshot_id),
                        "synthetic": True,
                    }
                except RuntimeError:
                    raise RuntimeError(
                        "existing synthetic case has no current snapshot"
                    ) from None

        subject_id = "synthetic-business-phase5a"
        subject_digest = sha256(subject_id.encode()).hexdigest()
        bank_semantics = _semantics(
            f"bank-lineage-{case_id}",
            "fixture-bank-issuer",
            economic_event_id=f"bank-period-{case_id}",
        )
        bank_flat, bank_semantics, bank_projection = _resolution(
            tenant_id=tenant_id,
            case_id=case_id,
            reference_id=uuid4(),
            subject_id=subject_id,
            subject_digest=subject_digest,
            evidence_id=f"bank-visible-{case_id}",
            evidence_class="VERIFIED_FACT",
            verification_status="VERIFIED_FOR_PROPOSITION",
            proposition_type="bank_visible_inflows",
            proposition_value="118000",
            proposition_unit="MXN",
            verification_method="signed_provider_record_match",
            period_start=period_start,
            period_end=period_end,
            source_id="fixture_bank_registry",
            issuer_id="fixture-bank-issuer",
            source_class="regulated_financial_institution",
            acquisition_method="synthetic_fixture",
            semantics=bank_semantics,
            now=now,
        )
        with closing(self._authority_connect()) as authority, authority.transaction():
            self._authority_context(authority, tenant_id)
            authority.execute(
                "SELECT authority_revision FROM evidence_authority."
                "commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(bank_projection), 0, "EVIDENCE_PROJECTED"),
            )
            authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(bank_flat),
                    json.dumps(bank_semantics),
                    initial_snapshot,
                    1,
                    uuid4(),
                    f"phase5a-bank-{case_id}",
                ),
            )
        with closing(self._runtime_connect()) as runtime, runtime.transaction():
            self._runtime_context(runtime, tenant_id)
            bank_snapshot = runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (tenant_id, case_id, 2, f"phase5a-bank-snapshot-{case_id}"),
            ).fetchone()[0]

        merchant_semantics = _semantics(
            f"merchant-lineage-{case_id}",
            "fixture-merchant",
            economic_event_id=f"merchant-period-{case_id}",
        )
        merchant_flat, merchant_semantics, merchant_projection = _resolution(
            tenant_id=tenant_id,
            case_id=case_id,
            reference_id=uuid4(),
            subject_id=subject_id,
            subject_digest=subject_digest,
            evidence_id=f"merchant-revenue-{case_id}",
            evidence_class="MERCHANT_SUPPLIED_ARTIFACT",
            verification_status="UNVERIFIED",
            proposition_type="monthly_revenue",
            proposition_value="260000",
            proposition_unit="MXN",
            verification_method=MERCHANT_ASSERTION_PROFILE,
            period_start=period_start,
            period_end=period_end,
            source_id="fixture_merchant_registry",
            issuer_id="fixture-merchant",
            source_class="merchant_self_reported",
            acquisition_method="synthetic_merchant_clarification",
            semantics=merchant_semantics,
            now=now,
        )
        with closing(self._authority_connect()) as authority, authority.transaction():
            self._authority_context(authority, tenant_id)
            authority.execute(
                "SELECT authority_revision FROM evidence_authority."
                "commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(merchant_projection), 1, "EVIDENCE_PROJECTED"),
            )
            authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(merchant_flat),
                    json.dumps(merchant_semantics),
                    bank_snapshot,
                    2,
                    uuid4(),
                    f"phase5a-merchant-{case_id}",
                ),
            )
        with closing(self._runtime_connect()) as runtime, runtime.transaction():
            self._runtime_context(runtime, tenant_id)
            snapshot = runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (tenant_id, case_id, 3, f"phase5a-target-snapshot-{case_id}"),
            ).fetchone()[0]
        return {
            "case_id": str(case_id),
            "snapshot_id": str(snapshot),
            "synthetic": True,
        }

    def handle(self, request: dict) -> dict:
        fixture = str(request["fixture"])
        if fixture == "useful_coverage":
            return self.useful_coverage(
                tenant_id=UUID(str(request["tenant_id"])),
                case_id=UUID(str(request["case_id"])),
                action_id=UUID(str(request["action_id"])),
                expected_revision=int(request["expected_authority_revision"]),
            )
        if fixture == "duplicate_response":
            return {
                "outcome": "COMPLETED_UNRESOLVED",
                "reason_code": "QUESTION_STILL_UNRESOLVED",
                "reason_detail": "Synthetic response duplicated the existing semantic source and was not accepted as additional support.",
                "synthetic": True,
            }
        if fixture == "unavailable":
            return {
                "outcome": "STOPPED",
                "reason_code": "EVIDENCE_UNAVAILABLE",
                "reason_detail": "Synthetic source reported that the requested record was unavailable.",
                "synthetic": True,
            }
        raise ValueError("unsupported synthetic fixture")


def build_handler(operator: SyntheticEvidenceOperator, token: str):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/v1/synthetic-evidence" or not hmac.compare_digest(
                self.headers.get("Authorization", ""), f"Bearer {token}"
            ):
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY_BYTES:
                    raise ValueError
                body = json.loads(self.rfile.read(size))
                result = operator.handle(body)
                encoded = json.dumps(result, separators=(",", ":")).encode()
                self.send_response(200)
            except Exception:  # noqa: BLE001 - authority failures return no detail
                encoded = b'{"error":"synthetic operation failed safely"}'
                self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return Handler


def _connect(name: str):
    dsn = os.environ.get(name, "")
    if not dsn:
        raise RuntimeError(f"{name} is required")
    import psycopg

    return lambda: psycopg.connect(dsn)


def main() -> None:
    parser = argparse.ArgumentParser(description="OLIN synthetic evidence operator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8086)
    parser.add_argument("--setup-tenant")
    parser.add_argument("--setup-case")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("synthetic operator is loopback-only")
    token = os.environ.get("OLIN_SYNTHETIC_OPERATOR_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("synthetic operator token must contain 32 characters")
    operator = SyntheticEvidenceOperator(
        _connect("OLIN_SYNTHETIC_RUNTIME_DATABASE_URL"),
        _connect("OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL"),
    )
    if bool(args.setup_tenant) != bool(args.setup_case):
        raise RuntimeError("setup tenant and case must be supplied together")
    if args.setup_tenant:
        result = operator.setup_target_case(
            tenant_id=UUID(args.setup_tenant), case_id=UUID(args.setup_case)
        )
        print(json.dumps(result, sort_keys=True))
    server = ThreadingHTTPServer((args.host, args.port), build_handler(operator, token))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
