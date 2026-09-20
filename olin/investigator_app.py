"""Separate Phase 5A Investigator analyst entry point.

The service exposes one tenant-bound human investigation workspace.  It does not
import the legacy scoring server and does not possess canonical evidence-authority
credentials.  Synthetic evidence is handed to a separate loopback-only operator.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
import secrets
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, UUID, uuid5

from .investigator.authority import establish_runtime_database_custody
from .investigator.evidence_boundary import PostgresReasoningSnapshotGate
from .investigator.workflow import (
    ACTION_CATALOGUE,
    ActionStatus,
    action_definition,
    require_terminal_reason,
    require_transition,
    validate_effort_cost,
    validate_rationale,
    validate_reason_detail,
)
from .investigator_evidence_adapter import PostgresCanonicalEvidenceReadPort

SESSION_VERSION = "investigator1"
SESSION_TTL_SECONDS = 15 * 60
MAX_BODY_BYTES = 32_768


class InvestigatorAppError(RuntimeError):
    """Safe application error carrying an HTTP status and public code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class AnalystIdentity:
    name: str
    tenant_id: UUID
    role: str


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class InvestigatorAuthenticator:
    """Named analyst credentials exchanged for short-lived signed sessions."""

    def __init__(self, users: Mapping[str, Mapping[str, str]], secret: str) -> None:
        if len(secret) < 32:
            raise RuntimeError("Investigator session secret must contain 32 characters")
        parsed: dict[str, tuple[str, AnalystIdentity]] = {}
        for name, record in users.items():
            token = str(record.get("token", ""))
            role = str(record.get("role", ""))
            if not token or role != "analyst":
                raise RuntimeError("Investigator users must be named analysts")
            parsed[str(name)] = (
                token,
                AnalystIdentity(str(name), UUID(str(record["tenant_id"])), role),
            )
        if not parsed:
            raise RuntimeError("At least one Investigator analyst is required")
        self._users = parsed
        self._secret = secret.encode("utf-8")

    @classmethod
    def from_environment(cls) -> InvestigatorAuthenticator:
        try:
            users = json.loads(os.environ["OLIN_INVESTIGATOR_USERS"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError("OLIN_INVESTIGATOR_USERS must be valid JSON") from exc
        if not isinstance(users, dict):
            raise TypeError("OLIN_INVESTIGATOR_USERS must be an object")
        return cls(users, os.environ.get("OLIN_INVESTIGATOR_SESSION_SECRET", ""))

    def issue(self, name: str, supplied_token: str, now: int | None = None) -> str:
        configured = self._users.get(name)
        if configured is None or not hmac.compare_digest(supplied_token, configured[0]):
            raise InvestigatorAppError(401, "UNAUTHENTICATED", "Invalid credentials")
        current = int(time.time() if now is None else now)
        identity = configured[1]
        payload = {
            "aud": "olin-investigator",
            "exp": current + SESSION_TTL_SECONDS,
            "iat": current,
            "iss": "olin-investigator",
            "jti": secrets.token_hex(12),
            "role": identity.role,
            "sub": identity.name,
            "tenant_id": str(identity.tenant_id),
        }
        encoded = _b64(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        prefix = f"{SESSION_VERSION}.{encoded}"
        signature = _b64(
            hmac.new(self._secret, prefix.encode(), hashlib.sha256).digest()
        )
        return f"{prefix}.{signature}"

    def authenticate(self, header: str, now: int | None = None) -> AnalystIdentity:
        if not header.startswith("Bearer "):
            raise InvestigatorAppError(
                401, "UNAUTHENTICATED", "Authentication required"
            )
        token = header[7:].strip()
        try:
            version, encoded, supplied_signature = token.split(".")
            prefix = f"{version}.{encoded}"
            expected = _b64(
                hmac.new(self._secret, prefix.encode(), hashlib.sha256).digest()
            )
            if version != SESSION_VERSION or not hmac.compare_digest(
                supplied_signature, expected
            ):
                raise ValueError
            payload = json.loads(_unb64(encoded))
            current = int(time.time() if now is None else now)
            if (
                payload.get("iss") != "olin-investigator"
                or payload.get("aud") != "olin-investigator"
                or payload.get("role") != "analyst"
                or not isinstance(payload.get("iat"), int)
                or not isinstance(payload.get("exp"), int)
                or payload["iat"] > current + 30
                or payload["exp"] <= current
                or payload["exp"] - payload["iat"] > SESSION_TTL_SECONDS
            ):
                raise ValueError
            configured = self._users.get(str(payload["sub"]))
            if configured is None or str(configured[1].tenant_id) != payload.get(
                "tenant_id"
            ):
                raise ValueError
            return configured[1]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise InvestigatorAppError(
                401, "UNAUTHENTICATED", "Session is invalid or expired"
            ) from None


class LoopbackSyntheticOperator:
    """Narrow client for the separately credentialed development operator."""

    def __init__(self, base_url: str, token: str) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Synthetic operator must be loopback-only")
        if not token:
            raise RuntimeError("Synthetic operator service token is required")
        self._host = parsed.hostname
        self._port = parsed.port or 80
        self._token = token

    def submit(
        self,
        *,
        tenant_id: UUID,
        case_id: UUID,
        action_id: UUID,
        fixture: str,
        expected_authority_revision: int,
    ) -> dict:
        body = json.dumps(
            {
                "action_id": str(action_id),
                "case_id": str(case_id),
                "expected_authority_revision": expected_authority_revision,
                "fixture": fixture,
                "tenant_id": str(tenant_id),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        connection = http.client.HTTPConnection(self._host, self._port, timeout=5)
        try:
            connection.request(
                "POST",
                "/v1/synthetic-evidence",
                body=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            encoded = response.read(MAX_BODY_BYTES + 1)
            if response.status != 200 or len(encoded) > MAX_BODY_BYTES:
                raise OSError("synthetic operator rejected request")
            return json.loads(encoded)
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            raise InvestigatorAppError(
                503,
                "SYNTHETIC_OPERATOR_UNAVAILABLE",
                "The synthetic evidence operator is unavailable",
            ) from exc
        finally:
            connection.close()


class InvestigatorWorkflowService:
    """Coordinates current reasoning and separately authorized action writes."""

    def __init__(
        self,
        *,
        runtime_connect: Callable[[], Any],
        canonical_connect: Callable[[], Any],
        action_connect: Callable[[], Any],
        synthetic_operator: LoopbackSyntheticOperator | None = None,
    ) -> None:
        self._runtime_connect = runtime_connect
        self._canonical_connect = canonical_connect
        self._action_connect = action_connect
        self._synthetic_operator = synthetic_operator

    @staticmethod
    def _runtime_context(connection: Any, tenant_id: UUID, *, read_only: bool) -> None:
        if read_only:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
            )
        else:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE"
            )
        connection.execute("SET LOCAL ROLE olin_investigator_runtime")
        row = connection.execute(
            "SELECT investigator.session_tenant_id()=%s", (tenant_id,)
        ).fetchone()
        if row is None or tuple(row) != (True,):
            raise InvestigatorAppError(403, "TENANT_DENIED", "Case access denied")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)", (str(tenant_id),)
        )

    @staticmethod
    def _action_context(connection: Any, tenant_id: UUID) -> None:
        connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
        connection.execute("SET LOCAL ROLE olin_investigator_action_writer")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)", (str(tenant_id),)
        )

    def _current_snapshot(
        self, connection: Any, tenant_id: UUID, case_id: UUID
    ) -> tuple[UUID, int]:
        with connection.transaction():
            self._runtime_context(connection, tenant_id, read_only=True)
            row = connection.execute(
                "SELECT snapshot.snapshot_id, stored_case.case_version "
                "FROM investigator.case_snapshot snapshot "
                "JOIN investigator.investigation_case stored_case "
                "ON stored_case.tenant_id=snapshot.tenant_id "
                "AND stored_case.case_id=snapshot.case_id "
                "WHERE snapshot.tenant_id=%s AND snapshot.case_id=%s "
                "AND snapshot.snapshot_schema_version=2 "
                "AND investigator.is_snapshot_current(%s,snapshot.snapshot_id) "
                "ORDER BY snapshot.created_at DESC, snapshot.snapshot_id DESC LIMIT 1",
                (tenant_id, case_id, tenant_id),
            ).fetchone()
        if row is None:
            raise InvestigatorAppError(
                409, "CURRENT_ANALYSIS_UNAVAILABLE", "No current authorized snapshot"
            )
        return UUID(str(row[0])), int(row[1])

    @staticmethod
    def _establish_custody(connection: Any) -> Any:
        with connection.transaction():
            connection.execute("SET LOCAL ROLE olin_investigator_runtime")
            return establish_runtime_database_custody(connection)

    def current_analysis(self, identity: AnalystIdentity, case_id: UUID) -> dict:
        with (
            closing(self._runtime_connect()) as runtime,
            closing(self._canonical_connect()) as canonical,
        ):
            custody = self._establish_custody(runtime)
            snapshot_id, case_version = self._current_snapshot(
                runtime, identity.tenant_id, case_id
            )
            reader = PostgresCanonicalEvidenceReadPort(
                canonical, tenant_id=identity.tenant_id
            )
            gate = PostgresReasoningSnapshotGate(
                runtime_connection=runtime,
                evidence_authority=reader,
                runtime_custody=custody,
            )
            try:
                result = gate.reconstruct_economics_current(
                    tenant_id=identity.tenant_id,
                    case_id=case_id,
                    snapshot_id=snapshot_id,
                    as_of=datetime.now(timezone.utc),
                )
            except Exception as exc:
                raise InvestigatorAppError(
                    409,
                    "CURRENT_ANALYSIS_UNAVAILABLE",
                    "Current evidence is stale, unusable, or unsupported",
                ) from exc
        record = result.canonical_record()
        actions = self.list_actions(identity, case_id)
        accepted_actions = [
            item
            for item in actions
            if any(
                transition["to_status"] == ActionStatus.EVIDENCE_ACCEPTED.value
                for transition in item["transitions"]
            )
        ]
        selected_snapshot_id = (
            accepted_actions[-1]["action"]["selected_snapshot_id"]
            if accepted_actions
            else None
        )
        current_snapshot_id = record["input_assessment"]["snapshot_id"]
        evidence_added: list[dict] = []
        if selected_snapshot_id is not None:
            with closing(self._runtime_connect()) as runtime, runtime.transaction():
                self._runtime_context(runtime, identity.tenant_id, read_only=True)
                rows = runtime.execute(
                    "SELECT snapshot_id,canonical_snapshot_payload "
                    "FROM investigator.case_snapshot WHERE tenant_id=%s AND case_id=%s "
                    "AND snapshot_id IN (%s,%s)",
                    (
                        identity.tenant_id,
                        case_id,
                        UUID(selected_snapshot_id),
                        UUID(current_snapshot_id),
                    ),
                ).fetchall()
            payloads = {str(row[0]): row[1] for row in rows}
            if selected_snapshot_id in payloads and current_snapshot_id in payloads:
                historical_ids = {
                    item["reference_id"]
                    for item in payloads[selected_snapshot_id]["evidence"][
                        "accepted_evidence_refs"
                    ]
                }
                evidence_added = [
                    {
                        "reference_id": item["reference_id"],
                        "evidence_id": item["artifact"]["evidence_id"],
                        "source_id": item["source_attestation"]["source_id"],
                        "proposition_type": item["proposition_verification"][
                            "proposition_type"
                        ],
                    }
                    for item in payloads[current_snapshot_id]["evidence"][
                        "accepted_evidence_refs"
                    ]
                    if item["reference_id"] not in historical_ids
                ]
        added_reference_ids = {item["reference_id"] for item in evidence_added}

        def supported_by_added(items: list[dict]) -> list[str]:
            return sorted(
                {
                    str(item.get("quantity", item.get("coverage_type", "")))
                    for item in items
                    if any(
                        provenance["reference_id"] in added_reference_ids
                        for provenance in item.get("provenance", [])
                    )
                }
                - {""}
            )

        return {
            "case_id": str(case_id),
            "case_version": case_version,
            "demonstration": "SYNTHETIC DEMONSTRATION",
            "reconstruction": record,
            "server_checked_at": record["input_assessment"]["checked_at"],
            "synthetic": True,
            "tenant_id": str(identity.tenant_id),
            "change_summary": {
                "historical_selected_snapshot_id": selected_snapshot_id,
                "current_snapshot_id": current_snapshot_id,
                "canonical_evidence_added": evidence_added,
                "current_values_supported_by_added_evidence": supported_by_added(
                    record["observed_values"] + record["claimed_values"]
                ),
                "current_coverage_supported_by_added_evidence": supported_by_added(
                    record["coverage_diagnostics"]
                ),
                "questions_still_unresolved": [
                    item["quantity"] for item in record["unresolved_quantities"]
                ],
                "historical_notice": (
                    "The reference delta compares immutable snapshot evidence lists. "
                    "Only the current analysis is authorized; the selected snapshot "
                    "is historical and is not rerun as current."
                ),
            },
        }

    def list_actions(self, identity: AnalystIdentity, case_id: UUID) -> list[dict]:
        with closing(self._action_connect()) as connection, connection.transaction():
            self._action_context(connection, identity.tenant_id)
            rows = connection.execute(
                "SELECT action,transitions FROM investigator."
                "read_investigation_actions(%s,%s)",
                (identity.tenant_id, case_id),
            ).fetchall()
        return [{"action": row[0], "transitions": row[1]} for row in rows]

    def current_report(self, identity: AnalystIdentity, case_id: UUID) -> dict:
        from .investigator_reports import capture, render

        return render(capture(self, identity, case_id))

    def select_action(
        self,
        identity: AnalystIdentity,
        case_id: UUID,
        *,
        action_type: str,
        rationale: str,
        idempotency_key: str,
    ) -> dict:
        definition = action_definition(action_type)
        rationale = validate_rationale(rationale)
        existing_actions = self.list_actions(identity, case_id)
        existing = next(
            (
                item
                for item in existing_actions
                if item["action"]["idempotency_key"] == idempotency_key
            ),
            None,
        )
        if existing is not None:
            if (
                existing["action"]["action_type"] == definition.action_type.value
                and existing["action"]["analyst_rationale"] == rationale
            ):
                return existing
            raise InvestigatorAppError(
                409, "IDEMPOTENCY_CONFLICT", "Action request conflicts with history"
            )
        current = self.current_analysis(identity, case_id)
        reconstruction = current["reconstruction"]
        binding = reconstruction["input_assessment"]
        finding_refs = [
            {
                "kind": "UNKNOWN",
                "quantity": item["quantity"],
                "rule_id": item["rule_id"],
            }
            for item in reconstruction["unresolved_quantities"]
        ] + [
            {
                "kind": "CONTRADICTION",
                "contradiction_type": item["contradiction_type"],
                "rule_id": item["rule_id"],
            }
            for item in reconstruction["contradictions_carried_forward"]
        ]
        action_id = uuid5(
            NAMESPACE_URL,
            f"olin:phase5a:{identity.tenant_id}:{case_id}:{idempotency_key}",
        )
        with closing(self._action_connect()) as connection, connection.transaction():
            self._action_context(connection, identity.tenant_id)
            stored = connection.execute(
                "SELECT investigator.select_investigation_action("
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    identity.tenant_id,
                    case_id,
                    action_id,
                    UUID(binding["snapshot_id"]),
                    binding["snapshot_digest"],
                    binding["authority_revision"],
                    binding["authority_digest"],
                    binding["evidence_state_digest"],
                    binding["assessment_digest"],
                    binding["phase3_rules_version"],
                    binding["phase3_schema_version"],
                    reconstruction["rules_version"],
                    reconstruction["schema_version"],
                    definition.action_type.value,
                    definition.question_id,
                    definition.unresolved_question,
                    definition.purpose,
                    definition.permitted_data_scope,
                    definition.requested_source,
                    json.dumps(definition.prerequisites),
                    json.dumps(definition.resolution_criteria),
                    json.dumps(finding_refs),
                    rationale,
                    identity.name,
                    idempotency_key,
                ),
            ).fetchone()[0]
        return next(
            item
            for item in self.list_actions(identity, case_id)
            if item["action"]["action_id"] == str(stored)
        )

    def _transition_action(
        self,
        identity: AnalystIdentity,
        case_id: UUID,
        action_id: UUID,
        *,
        expected_sequence: int,
        to_status: str,
        reason_code: str | None,
        reason_detail: str | None,
        evidence_references: list[str] | None,
        effort_minutes: int | None,
        cost_amount: str | None,
        cost_currency: str | None,
        idempotency_key: str,
    ) -> dict:
        actions = self.list_actions(identity, case_id)
        matched = next(
            (item for item in actions if item["action"]["action_id"] == str(action_id)),
            None,
        )
        if matched is None:
            raise InvestigatorAppError(404, "ACTION_NOT_FOUND", "Action not found")
        replay = next(
            (
                transition
                for transition in matched["transitions"]
                if transition["idempotency_key"] == idempotency_key
            ),
            None,
        )
        if replay is not None:
            requested_references = evidence_references or []
            if (
                replay["to_status"] == to_status
                and replay["reason_code"] == reason_code
                and replay["reason_detail"] == reason_detail
                and replay["evidence_references"] == requested_references
                and replay["actual_effort_minutes"] == effort_minutes
                and (
                    replay["actual_cost_amount"] is None
                    if cost_amount is None
                    else str(replay["actual_cost_amount"]) == str(cost_amount)
                )
                and replay["actual_cost_currency"] == cost_currency
            ):
                return matched
            raise InvestigatorAppError(
                409, "IDEMPOTENCY_CONFLICT", "Transition request conflicts with history"
            )
        current_status = matched["transitions"][-1]["to_status"]
        require_transition(current_status, to_status)
        require_terminal_reason(to_status, reason_code)
        reason_detail = validate_reason_detail(reason_detail)
        effort_minutes, cost_amount, cost_currency = validate_effort_cost(
            effort_minutes=effort_minutes,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
        )
        references = evidence_references or []
        if any(not isinstance(value, str) or not value.strip() for value in references):
            raise InvestigatorAppError(
                400, "INVALID_REFERENCE", "Invalid evidence reference"
            )
        with closing(self._action_connect()) as connection, connection.transaction():
            self._action_context(connection, identity.tenant_id)
            connection.execute(
                "SELECT investigator.transition_investigation_action("
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    identity.tenant_id,
                    action_id,
                    expected_sequence,
                    to_status,
                    reason_code,
                    reason_detail,
                    json.dumps(references),
                    effort_minutes,
                    cost_amount,
                    cost_currency,
                    identity.name,
                    idempotency_key,
                ),
            ).fetchone()
        return next(
            item
            for item in self.list_actions(identity, case_id)
            if item["action"]["action_id"] == str(action_id)
        )

    def transition_action(
        self,
        identity: AnalystIdentity,
        case_id: UUID,
        action_id: UUID,
        *,
        expected_sequence: int,
        to_status: str,
        reason_code: str | None,
        reason_detail: str | None,
        evidence_references: list[str] | None,
        effort_minutes: int | None,
        cost_amount: str | None,
        cost_currency: str | None,
        idempotency_key: str,
    ) -> dict:
        if to_status in {
            ActionStatus.RESPONSE_RECEIVED.value,
            ActionStatus.EVIDENCE_ACCEPTED.value,
        }:
            raise InvestigatorAppError(
                403,
                "CANONICAL_HANDOFF_REQUIRED",
                "Only the separate canonical handoff may record this status",
            )
        if evidence_references:
            raise InvestigatorAppError(
                403,
                "CANONICAL_HANDOFF_REQUIRED",
                "Analysts cannot attach authoritative evidence references",
            )
        return self._transition_action(
            identity,
            case_id,
            action_id,
            expected_sequence=expected_sequence,
            to_status=to_status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            evidence_references=[],
            effort_minutes=effort_minutes,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            idempotency_key=idempotency_key,
        )

    def _action_bound_evidence_delta(
        self,
        identity: AnalystIdentity,
        case_id: UUID,
        action_id: UUID,
        selected_snapshot_id: str,
        current_snapshot_id: str,
        reference_id: str,
    ) -> bool:
        expected_evidence_id = f"fixture-account-coverage-{action_id}"
        with closing(self._runtime_connect()) as runtime, runtime.transaction():
            self._runtime_context(runtime, identity.tenant_id, read_only=True)
            rows = runtime.execute(
                "SELECT snapshot_id,canonical_snapshot_payload "
                "FROM investigator.case_snapshot WHERE tenant_id=%s AND case_id=%s "
                "AND snapshot_id IN (%s,%s)",
                (
                    identity.tenant_id,
                    case_id,
                    UUID(selected_snapshot_id),
                    UUID(current_snapshot_id),
                ),
            ).fetchall()
        snapshots = {str(row[0]): row[1] for row in rows}
        selected_references = {
            item["reference_id"]
            for item in snapshots.get(selected_snapshot_id, {})
            .get("evidence", {})
            .get("accepted_evidence_refs", [])
        }
        current_items = {
            item["reference_id"]: item
            for item in snapshots.get(current_snapshot_id, {})
            .get("evidence", {})
            .get("accepted_evidence_refs", [])
        }
        current_item = current_items.get(reference_id)
        return bool(
            current_snapshot_id != selected_snapshot_id
            and reference_id not in selected_references
            and current_item is not None
            and current_item["artifact"]["evidence_id"] == expected_evidence_id
            and current_item["proposition_verification"]["proposition_type"]
            == "bank_account_coverage"
        )

    def synthetic_response(
        self,
        identity: AnalystIdentity,
        case_id: UUID,
        action_id: UUID,
        *,
        fixture: str,
    ) -> dict:
        if self._synthetic_operator is None:
            raise InvestigatorAppError(
                503,
                "SYNTHETIC_OPERATOR_UNAVAILABLE",
                "Synthetic operator is not configured",
            )
        if fixture not in {"useful_coverage", "duplicate_response", "unavailable"}:
            raise InvestigatorAppError(
                400, "INVALID_FIXTURE", "Unknown synthetic fixture"
            )
        actions = self.list_actions(identity, case_id)
        matched = next(
            (item for item in actions if item["action"]["action_id"] == str(action_id)),
            None,
        )
        if matched is None:
            raise InvestigatorAppError(404, "ACTION_NOT_FOUND", "Action not found")
        response_key = f"synthetic-response:{action_id}:{fixture}"
        receipt = next(
            (t for t in matched["transitions"] if t["idempotency_key"] == response_key),
            None,
        )
        final_key = (
            f"synthetic-accepted:{action_id}:{fixture}"
            if fixture == "useful_coverage"
            else f"synthetic-terminal:{action_id}:{fixture}"
        )
        finalized = next(
            (t for t in matched["transitions"] if t["idempotency_key"] == final_key),
            None,
        )
        # A receipt is not an outcome. Resume only its still-pending transition;
        # unrelated later history must not be overwritten by a retry.
        if finalized is not None and fixture != "useful_coverage":
            return {
                "outcome": finalized["to_status"],
                "reason_code": finalized["reason_code"],
                "reason_detail": finalized["reason_detail"],
                "synthetic": True,
                "replayed": True,
            }
        if (
            fixture == "useful_coverage"
            and matched["action"]["action_type"] != "REQUEST_ACCOUNT_CHANNEL_RECORD"
        ):
            raise InvestigatorAppError(
                400,
                "FIXTURE_NOT_PERMITTED",
                "This action has no supported coverage-evidence handoff",
            )
        current = matched["transitions"][-1]
        if finalized is None and not (
            (receipt is None and current["to_status"] == ActionStatus.REQUESTED.value)
            or (
                receipt is not None
                and current == receipt
                and current["to_status"] == ActionStatus.RESPONSE_RECEIVED.value
            )
        ):
            raise InvestigatorAppError(
                409,
                "INVALID_ACTION_STATE",
                "Response requires a requested action or its pending receipt",
            )
        result = self._synthetic_operator.submit(
            tenant_id=identity.tenant_id,
            case_id=case_id,
            action_id=action_id,
            fixture=fixture,
            expected_authority_revision=int(
                matched["action"]["selected_authority_revision"]
            ),
        )
        if not isinstance(result, dict) or result.get("synthetic") is not True:
            raise InvestigatorAppError(
                409, "INVALID_HANDOFF", "Synthetic handoff response is invalid"
            )
        outcome = str(result.get("outcome", ""))
        if outcome == ActionStatus.EVIDENCE_ACCEPTED.value:
            try:
                reference_id = str(UUID(str(result["evidence_reference"])))
                expected_snapshot_id = str(UUID(str(result["new_snapshot_id"])))
                expected_revision = int(result["authority_revision"])
            except (KeyError, TypeError, ValueError) as exc:
                raise InvestigatorAppError(
                    409, "INVALID_HANDOFF", "Synthetic handoff binding is invalid"
                ) from exc
            confirmed = self.current_analysis(identity, case_id)["reconstruction"]
            binding = confirmed["input_assessment"]
            provenance_groups = (
                confirmed["observed_values"],
                confirmed["claimed_values"],
                confirmed["derived_values"],
                confirmed["coverage_diagnostics"],
                confirmed["unresolved_quantities"],
                confirmed["contradictions_carried_forward"],
            )
            current_references = {
                item["reference_id"]
                for group in provenance_groups
                for value in group
                for item in value.get("provenance", [])
            }
            selected_snapshot_id = str(matched["action"]["selected_snapshot_id"])
            if (
                binding["snapshot_id"] != expected_snapshot_id
                or binding["authority_revision"] != expected_revision
                or reference_id not in current_references
                or not self._action_bound_evidence_delta(
                    identity,
                    case_id,
                    action_id,
                    selected_snapshot_id,
                    expected_snapshot_id,
                    reference_id,
                )
            ):
                raise InvestigatorAppError(
                    409,
                    "INVALID_HANDOFF",
                    "Canonical current analysis did not confirm the handoff",
                )
            result["evidence_reference"] = reference_id
        elif outcome in {
            ActionStatus.COMPLETED_UNRESOLVED.value,
            ActionStatus.STOPPED.value,
        }:
            if result.get("evidence_reference") is not None:
                raise InvestigatorAppError(
                    409, "INVALID_HANDOFF", "Unresolved handoff cannot attach evidence"
                )
            require_terminal_reason(outcome, result.get("reason_code"))
            validate_reason_detail(result.get("reason_detail"))
        else:
            raise InvestigatorAppError(
                409, "INVALID_HANDOFF", "Synthetic handoff outcome is unsupported"
            )
        if finalized is not None:
            # Accepted replays also traverse the canonical/currentness and
            # action-bound delta checks above; history is never authority.
            if finalized["evidence_references"] != [result["evidence_reference"]]:
                raise InvestigatorAppError(
                    409, "INVALID_HANDOFF", "Replay evidence differs from history"
                )
            result["outcome"] = finalized["to_status"]
            result["replayed"] = True
            return result
        response = self._transition_action(
            identity,
            case_id,
            action_id,
            expected_sequence=(
                int(receipt["transition_sequence"]) - 1
                if receipt is not None
                else int(current["transition_sequence"])
            ),
            to_status=ActionStatus.RESPONSE_RECEIVED.value,
            reason_code=None,
            reason_detail=None,
            evidence_references=(
                [str(result["evidence_reference"])]
                if result.get("evidence_reference")
                else []
            ),
            effort_minutes=None,
            cost_amount=None,
            cost_currency=None,
            idempotency_key=response_key,
        )
        response_sequence = next(
            int(t["transition_sequence"])
            for t in response["transitions"]
            if t["idempotency_key"] == response_key
        )
        if outcome == ActionStatus.EVIDENCE_ACCEPTED.value:
            self._transition_action(
                identity,
                case_id,
                action_id,
                expected_sequence=response_sequence,
                to_status=ActionStatus.EVIDENCE_ACCEPTED.value,
                reason_code=None,
                reason_detail=None,
                evidence_references=[str(result["evidence_reference"])],
                effort_minutes=None,
                cost_amount=None,
                cost_currency=None,
                idempotency_key=f"synthetic-accepted:{action_id}:{fixture}",
            )
        else:
            self._transition_action(
                identity,
                case_id,
                action_id,
                expected_sequence=response_sequence,
                to_status=outcome,
                reason_code=str(result["reason_code"]),
                reason_detail=str(result["reason_detail"]),
                evidence_references=[],
                effort_minutes=None,
                cost_amount=None,
                cost_currency=None,
                idempotency_key=f"synthetic-terminal:{action_id}:{fixture}",
            )
        return result


def _catalogue_payload() -> list[dict[str, object]]:
    return [item.canonical_record() for item in ACTION_CATALOGUE.values()]


_WORKSPACE_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="robots" content="noindex,nofollow"><title>OLIN Investigator</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#17231d;background:#eef1eb}*{box-sizing:border-box}
body{margin:0}.shell{max-width:1180px;margin:auto;padding:24px}.banner{background:#183e2e;color:white;padding:12px 24px;font-weight:800;letter-spacing:.08em}
.card{background:white;border:1px solid #cbd4cc;border-radius:16px;padding:20px;margin:16px 0}.hidden{display:none!important}
button,input,select,textarea{font:inherit;padding:10px;border:1px solid #9dac9f;border-radius:8px}button{background:#183e2e;color:white;cursor:pointer}button:disabled{opacity:.5}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.value{font-size:1.5rem;font-weight:800}.label{font-size:.78rem;text-transform:uppercase;color:#526158;letter-spacing:.05em}
.observed{border-left:5px solid #18794e}.claimed{border-left:5px solid #a96d00}.unknown{border-left:5px solid #6f7780}.disagreement{border-left:5px solid #9c2f2f}
.muted{color:#5e6b63}.history li{margin:.5rem 0}.error{background:#fff0f0;color:#851d1d}.ok{background:#edf8f1;color:#17603b}.actions{display:grid;gap:10px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="banner">SYNTHETIC DEMONSTRATION · NO CREDIT DECISION · NO MONEY MOVEMENT</div>
<main class="shell"><h1>OLIN Investigator</h1><p>Human-controlled investigation using current canonical evidence.</p>
<section id="login" class="card"><h2>Analyst access</h2><input id="name" placeholder="Analyst name"><input id="token" type="password" placeholder="Development token"><button onclick="login()">Sign in</button></section>
<section id="workspace" class="hidden"><div class="card"><label>Case UUID <input id="caseId"></label><button onclick="refreshCase()">Open / refresh current case</button><p id="status" class="muted"></p></div>
<div id="analysis"></div><div class="card"><h2>Human-selected next action</h2><div id="catalogue" class="actions"></div></div><div id="history" class="card"><h2>Action history</h2></div>
<section class="card"><h2>Analyst Brief and Audit Annex</h2><p>One authorized capture for both outputs. Historical AS OF its server time; refresh for a new check. Downloads cannot be remotely recalled.</p>
<button onclick="captureReport()">Capture / refresh report pair</button>
<button onclick="viewReport('brief')">View Analyst Brief</button><button onclick="viewReport('annex')">View Audit Annex</button>
<button onclick="downloadReport()">Download structured JSON</button><button onclick="printReport()">Print selected report</button>
<p id="reportStatus"></p><iframe id="reportFrame" title="Read-only analyst report" sandbox="allow-modals allow-same-origin" style="width:100%;height:650px;border:1px solid #ccc"></iframe></section>
<section class="card"><h2>Shadow research — separate and untrusted</h2><p>Freeze a round BEFORE choosing your initial human action. Then record that action above. Suggestions are withheld by the server until selection. A fake provider is a plumbing demonstration, not model intelligence. Human investigation does not depend on research availability.</p>
<button onclick="startShadow()">Freeze or resume pre-selection research context</button>
<button onclick="shadowOperation('generate')">Generate isolated shadow attempt</button>
<button onclick="shadowOperation('disclose')">Reveal after human selection</button>
<button onclick="shadowOperation('history')">Research history and performed outcome</button>
<button onclick="rateShadow()">Record research usefulness</button>
<pre id="shadowResult" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></section></section>
<div id="message"></div></main><script>
let sessionToken='', currentCase='', currentAnalysis=null;
let reportPair=null;
function clearReport(){reportPair=null;document.getElementById('reportFrame').srcdoc='';document.getElementById('reportStatus').textContent='Report unavailable until a fresh capture.'}
async function captureReport(){clearReport();const caseId=currentCase;try{const r=await api('/api/cases/'+encodeURIComponent(caseId)+'/report');if(caseId!==currentCase)return;reportPair=r;document.getElementById('reportStatus').textContent='Historical AS OF '+r.manifest.checked_at+' · '+r.manifest.report_input_digest;viewReport('brief')}catch(e){clearReport();document.getElementById('reportStatus').textContent='Report unavailable/stale: '+e.message}}
function viewReport(kind){if(!reportPair||reportPair.manifest.case_id!==currentCase)return;document.getElementById('reportFrame').srcdoc=reportPair.printable_html[kind]}
function downloadReport(){if(!reportPair||reportPair.manifest.case_id!==currentCase)return;const u=URL.createObjectURL(new Blob([JSON.stringify(reportPair,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='investigator-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
function printReport(){if(reportPair&&reportPair.manifest.case_id===currentCase)document.getElementById('reportFrame').contentWindow.print()}
let shadowRound='', shadowCase='';
const shadowPanel=document.getElementById('shadowResult');
async function startShadow(){shadowPanel.textContent='';try{let r;try{r=await api('/api/cases/'+encodeURIComponent(currentCase)+'/shadow')}catch(_){r=await api('/api/cases/'+encodeURIComponent(currentCase)+'/shadow',{method:'POST',body:JSON.stringify({idempotency_key:crypto.randomUUID()})})}shadowRound=r.round_id;shadowCase=currentCase;shadowPanel.textContent=JSON.stringify(r,null,2)}catch(e){shadowPanel.textContent='Research unavailable: '+e.message}}
async function shadowOperation(op){shadowPanel.textContent='';if(!shadowRound||shadowCase!==currentCase){shadowPanel.textContent='Freeze a comparison round for this case first.';return}try{const r=await api('/api/cases/'+encodeURIComponent(currentCase)+'/shadow/'+shadowRound+'/'+op,{method:'POST',body:'{}'});shadowPanel.textContent=JSON.stringify(r,null,2)}catch(e){shadowPanel.textContent='Research unavailable/stale: '+e.message}}
async function rateShadow(){if(!shadowRound||shadowCase!==currentCase)return;const usefulness=prompt('USEFUL, NOT_USEFUL or UNCERTAIN');if(!usefulness)return;const reason=prompt('Why? This is a human research interpretation, not evidence truth.');if(!reason)return;try{await api('/api/cases/'+encodeURIComponent(currentCase)+'/shadow/'+shadowRound+'/rate',{method:'POST',body:JSON.stringify({usefulness,reason,idempotency_key:crypto.randomUUID()})});notice('Research annotation recorded.')}catch(e){notice(e.message,true)}}
const nameInput=document.getElementById('name'),tokenInput=document.getElementById('token'),loginPanel=document.getElementById('login'),workspacePanel=document.getElementById('workspace'),caseInput=document.getElementById('caseId'),statusPanel=document.getElementById('status'),analysisPanel=document.getElementById('analysis'),cataloguePanel=document.getElementById('catalogue'),historyPanel=document.getElementById('history');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(sessionToken)headers.Authorization='Bearer '+sessionToken;const r=await fetch(path,{...options,headers,cache:'no-store'});const body=await r.json();if(!r.ok)throw new Error(body.message||body.code);return body}
function notice(text,bad=false){document.getElementById('message').innerHTML=`<div class="card ${bad?'error':'ok'}">${esc(text)}</div>`}
async function login(){try{const body=await api('/api/session',{method:'POST',body:JSON.stringify({name:nameInput.value,token:tokenInput.value})});sessionToken=body.access_token;tokenInput.value='';loginPanel.classList.add('hidden');workspacePanel.classList.remove('hidden');renderCatalogue(body.catalogue);notice('Authenticated analyst session.');}catch(e){notice(e.message,true)}}
function renderCatalogue(items){cataloguePanel.innerHTML=items.map(x=>`<div><strong>${esc(x.unresolved_question)}</strong><p>${esc(x.purpose)}</p><button onclick="selectAction('${esc(x.action_type)}')">Select this action</button></div>`).join('')}
async function refreshCase(){clearReport();currentCase=caseInput.value.trim();shadowPanel.textContent='Research display cleared. Reveal rechecks current authority.';statusPanel.textContent='Checking current server-authorized state…';analysisPanel.innerHTML='';try{const body=await api('/api/cases/'+encodeURIComponent(currentCase));currentAnalysis=body;renderAnalysis(body);await refreshHistory();statusPanel.textContent='Checked as of '+body.server_checked_at+'; refresh rechecks authority.';}catch(e){currentAnalysis=null;statusPanel.textContent='Current analysis unavailable.';notice(e.message,true)}}
function refs(x){return (x.provenance||[]).map(p=>esc(p.reference_id)+' / '+esc(p.source_id)+' / '+esc(p.verification_status)).join('<br>')||'No direct evidence reference (derived rule output).'}
function values(items,cls){return items.map(x=>`<div class="card ${cls}"><span class="label">${esc(x.value_type)} · ${esc(x.quantity)}</span><div class="value">${esc(x.value)} ${esc(x.unit)}</div><p>${esc(x.period_start)} — ${esc(x.period_end)}</p><small>Meaning: ${esc(x.dimensional_scope)} · rule ${esc(x.rule_id)}</small><details><summary>Evidence and provenance</summary><small>${refs(x)}</small></details></div>`).join('')}
function renderAnalysis(body){const r=body.reconstruction,b=r.input_assessment,c=body.change_summary;analysisPanel.innerHTML=`<div class="card"><h2>Current case</h2><p><b>${esc(body.case_id)}</b> · snapshot ${esc(b.snapshot_id)}</p><p>Authority revision ${esc(b.authority_revision)} · Phase 3 ${esc(b.phase3_rules_version)} · Phase 4 ${esc(r.rules_version)}</p><p>Server checked as of ${esc(body.server_checked_at)}</p></div><div class="grid">${values(r.observed_values,'observed')}${values(r.claimed_values,'claimed')}${values(r.derived_values,'disagreement')}</div><div class="card"><h2>Coverage</h2>${r.coverage_diagnostics.map(x=>`<p><b>${esc(x.coverage_type)}</b>: ${esc(x.status)} — ${esc(x.why)}</p>`).join('')}</div><div class="card unknown"><h2>Unknowns remain unknown</h2>${r.unresolved_quantities.map(x=>`<p><b>${esc(x.quantity)}</b>: ${esc(x.status)} — ${esc(x.why_unresolved)}</p>`).join('')}</div><div class="card disagreement"><h2>Reconciliation disagreements</h2>${r.contradictions_carried_forward.map(x=>`<p><b>${esc(x.contradiction_type)}</b> · ${esc(x.materiality)} · rule ${esc(x.rule_id)}</p>`).join('')||'<p>None in the current assessment.</p>'}</div><div class="card"><h2>Snapshot-bound change</h2><p>Historical selection snapshot: ${esc(c.historical_selected_snapshot_id||'none')}</p><p>Current snapshot: ${esc(c.current_snapshot_id)}</p><p>Canonical evidence added: ${c.canonical_evidence_added.map(x=>esc(x.reference_id)+' / '+esc(x.proposition_type)+' / '+esc(x.source_id)).join('<br>')||'none'}</p><p>Current values supported by added evidence: ${c.current_values_supported_by_added_evidence.map(esc).join(', ')||'none'}</p><p>Current coverage supported by added evidence: ${c.current_coverage_supported_by_added_evidence.map(esc).join(', ')||'none'}</p><p>Questions still unresolved: ${c.questions_still_unresolved.map(esc).join(', ')||'none listed'}</p><small>${esc(c.historical_notice)}</small></div>`}
async function selectAction(type){if(!currentAnalysis)return notice('Open a current case first.',true);const rationale=prompt('Why is this action useful for the unresolved question?');if(!rationale)return;try{await api('/api/cases/'+encodeURIComponent(currentCase)+'/actions',{method:'POST',body:JSON.stringify({action_type:type,rationale,idempotency_key:crypto.randomUUID()})});await refreshHistory();notice('Action selected and bound to the current snapshot.');}catch(e){notice(e.message,true)}}
async function refreshHistory(){const body=await api('/api/cases/'+encodeURIComponent(currentCase)+'/actions');historyPanel.innerHTML='<h2>Action history</h2>'+body.actions.map(renderAction).join('')}
function renderAction(item){const a=item.action,t=item.transitions,s=t[t.length-1];return `<article><h3>${esc(a.action_type)}</h3><p>${esc(a.unresolved_question)}</p><p><b>Status:</b> ${esc(s.to_status)} · selected snapshot ${esc(a.selected_snapshot_id)}</p><ol class="history">${t.map(x=>`<li>${esc(x.to_status)} · ${esc(x.transitioned_at)} · analyst ${esc(x.transitioned_by_analyst)} · service ${esc(x.transitioned_by)}</li>`).join('')}</ol>${actionButtons(a,s)}</article>`}
function actionButtons(a,s){if(['COMPLETED_RESOLVED','COMPLETED_UNRESOLVED','STOPPED','ESCALATED'].includes(s.to_status))return '';const seq=s.transition_sequence;let buttons='';if(s.to_status==='SELECTED')buttons+=`<button onclick="transition('${a.action_id}',${seq},'REQUESTED')">Mark requested</button> `;if(s.to_status==='REQUESTED'){if(a.action_type==='REQUEST_ACCOUNT_CHANNEL_RECORD')buttons+=`<button onclick="synthetic('${a.action_id}','useful_coverage')">Simulate supported response</button> `;buttons+=`<button onclick="synthetic('${a.action_id}','duplicate_response')">Simulate duplicate response</button> <button onclick="synthetic('${a.action_id}','unavailable')">Simulate unavailable</button> `}if(s.to_status==='EVIDENCE_ACCEPTED')buttons+=`<button onclick="transition('${a.action_id}',${seq},'COMPLETED_UNRESOLVED',{reason_code:'QUESTION_STILL_UNRESOLVED',reason_detail:'Accepted evidence narrowed but did not resolve the question.'})">Complete unresolved</button> `;if(['SELECTED','REQUESTED','RESPONSE_RECEIVED'].includes(s.to_status))buttons+=`<button onclick="stopAction('${a.action_id}',${seq},'STOPPED')">Stop</button> <button onclick="stopAction('${a.action_id}',${seq},'ESCALATED')">Escalate</button>`;return buttons}
async function transition(id,seq,to,extra={}){try{await api('/api/cases/'+encodeURIComponent(currentCase)+'/actions/'+id+'/transitions',{method:'POST',body:JSON.stringify({expected_sequence:seq,to_status:to,idempotency_key:crypto.randomUUID(),...extra})});await refreshHistory();}catch(e){notice(e.message,true)}}
async function synthetic(id,fixture){try{await api('/api/cases/'+encodeURIComponent(currentCase)+'/actions/'+id+'/synthetic-response',{method:'POST',body:JSON.stringify({fixture})});await refreshCase();notice('Synthetic response passed through the separate canonical operator; current analysis was recomputed.');}catch(e){notice(e.message,true)}}
async function stopAction(id,seq,status){const reason=prompt('Reason: EVIDENCE_UNAVAILABLE, PERMISSION_MISSING_OR_WITHDRAWN, QUESTION_STILL_UNRESOLVED, FURTHER_INVESTIGATION_NOT_JUSTIFIED, or SYNTHETIC_DEMO_LIMIT_REACHED');if(!reason)return;await transition(id,seq,status,{reason_code:reason,reason_detail:'Analyst recorded '+status.toLowerCase()+' reason.'})}
</script></body></html>"""


def build_handler(
    authenticator: InvestigatorAuthenticator,
    service: InvestigatorWorkflowService,
    shadow=None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "OlinInvestigator/1"

        def _json(self, status: int, body: object) -> None:
            encoded = json.dumps(
                body, ensure_ascii=False, separators=(",", ":")
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, private, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _body(self) -> dict:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = 0
            if not 0 < size <= MAX_BODY_BYTES:
                raise InvestigatorAppError(400, "INVALID_BODY", "Invalid request body")
            try:
                value = json.loads(self.rfile.read(size))
            except json.JSONDecodeError as exc:
                raise InvestigatorAppError(400, "INVALID_BODY", "Invalid JSON") from exc
            if not isinstance(value, dict):
                raise InvestigatorAppError(400, "INVALID_BODY", "JSON object required")
            return value

        def _identity(self) -> AnalystIdentity:
            return authenticator.authenticate(self.headers.get("Authorization", ""))

        def _parts(self) -> list[str]:
            return [part for part in urlparse(self.path).path.split("/") if part]

        def _dispatch(self, method: str) -> None:
            parts = self._parts()
            if method == "GET" and not parts:
                encoded = _WORKSPACE_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'",
                )
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            if method == "GET" and parts == ["favicon.ico"]:
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if method == "POST" and parts == ["api", "session"]:
                body = self._body()
                token = authenticator.issue(
                    str(body.get("name", "")), str(body.get("token", ""))
                )
                self._json(
                    200,
                    {
                        "access_token": token,
                        "catalogue": _catalogue_payload(),
                        "expires_in": SESSION_TTL_SECONDS,
                    },
                )
                return
            identity = self._identity()
            if len(parts) >= 3 and parts[:2] == ["api", "cases"]:
                try:
                    case_id = UUID(parts[2])
                except ValueError:
                    raise InvestigatorAppError(
                        404, "CASE_NOT_FOUND", "Case not found"
                    ) from None
                if method == "GET" and len(parts) == 3:
                    self._json(200, service.current_analysis(identity, case_id))
                    return
                if method == "GET" and parts[3:] == ["report"]:
                    if (
                        urlparse(self.path).query
                        or self.headers.get("Content-Length", "0") != "0"
                    ):
                        raise InvestigatorAppError(
                            400,
                            "INVALID_REPORT_INPUT",
                            "Report capture accepts no caller bindings",
                        )
                    self._json(200, service.current_report(identity, case_id))
                    return
                if len(parts) >= 4 and parts[3] == "shadow":
                    if shadow is None:
                        raise InvestigatorAppError(
                            503,
                            "RESEARCH_DISABLED",
                            "Shadow research is not configured; human workflow remains available",
                        )
                    body = self._body() if method == "POST" else {}
                    if method == "GET" and len(parts) == 4:
                        self._json(200, shadow.resume(identity, case_id))
                        return
                    if (
                        method == "POST"
                        and len(parts) == 4
                        and set(body) == {"idempotency_key"}
                    ):
                        self._json(
                            201,
                            shadow.create(identity, case_id, body["idempotency_key"]),
                        )
                        return
                    if method == "POST" and len(parts) == 6:
                        round_id = UUID(parts[4])
                        operation = parts[5]
                        if (
                            operation in {"generate", "disclose", "history"}
                            and not body
                        ):
                            self._json(
                                200,
                                getattr(shadow, operation)(identity, case_id, round_id),
                            )
                            return
                        if operation == "rate" and set(body) == {
                            "usefulness",
                            "reason",
                            "idempotency_key",
                        }:
                            self._json(
                                200,
                                shadow.rate(
                                    identity,
                                    case_id,
                                    round_id,
                                    body["usefulness"],
                                    body["reason"],
                                    body["idempotency_key"],
                                ),
                            )
                            return
                    raise InvestigatorAppError(
                        400,
                        "INVALID_RESEARCH_REQUEST",
                        "Closed research command required",
                    )
                if len(parts) == 4 and parts[3] == "actions":
                    if method == "GET":
                        self._json(
                            200, {"actions": service.list_actions(identity, case_id)}
                        )
                        return
                    if method == "POST":
                        body = self._body()
                        self._json(
                            201,
                            service.select_action(
                                identity,
                                case_id,
                                action_type=str(body.get("action_type", "")),
                                rationale=str(body.get("rationale", "")),
                                idempotency_key=str(body.get("idempotency_key", "")),
                            ),
                        )
                        return
                if len(parts) == 6 and parts[3] == "actions":
                    try:
                        action_id = UUID(parts[4])
                    except ValueError:
                        raise InvestigatorAppError(
                            404, "ACTION_NOT_FOUND", "Action not found"
                        ) from None
                    body = self._body()
                    if method == "POST" and parts[5] == "transitions":
                        self._json(
                            200,
                            service.transition_action(
                                identity,
                                case_id,
                                action_id,
                                expected_sequence=int(body.get("expected_sequence", 0)),
                                to_status=str(body.get("to_status", "")),
                                reason_code=body.get("reason_code"),
                                reason_detail=body.get("reason_detail"),
                                evidence_references=body.get("evidence_references"),
                                effort_minutes=body.get("effort_minutes"),
                                cost_amount=body.get("cost_amount"),
                                cost_currency=body.get("cost_currency"),
                                idempotency_key=str(body.get("idempotency_key", "")),
                            ),
                        )
                        return
                    if method == "POST" and parts[5] == "synthetic-response":
                        self._json(
                            200,
                            service.synthetic_response(
                                identity,
                                case_id,
                                action_id,
                                fixture=str(body.get("fixture", "")),
                            ),
                        )
                        return
            raise InvestigatorAppError(404, "NOT_FOUND", "Route not found")

        def do_GET(self) -> None:
            self._run("GET")

        def do_POST(self) -> None:
            self._run("POST")

        def _run(self, method: str) -> None:
            try:
                self._dispatch(method)
            except InvestigatorAppError as exc:
                self._json(exc.status, {"code": exc.code, "message": str(exc)})
            except (ValueError, TypeError) as exc:
                self._json(400, {"code": "INVALID_REQUEST", "message": str(exc)})
            except Exception:  # noqa: BLE001 - fail closed without leaking internals
                self._json(
                    500, {"code": "INTERNAL_ERROR", "message": "Request failed safely"}
                )

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return Handler


def _connect(dsn_name: str) -> Callable[[], Any]:
    dsn = os.environ.get(dsn_name, "")
    if not dsn:
        raise RuntimeError(f"{dsn_name} is required")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for Investigator") from exc
    return lambda: psycopg.connect(dsn)


def main() -> None:
    parser = argparse.ArgumentParser(description="OLIN Investigator Phase 5A")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8085)
    args = parser.parse_args()
    authenticator = InvestigatorAuthenticator.from_environment()
    operator = None
    if os.environ.get("OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_URL"):
        operator = LoopbackSyntheticOperator(
            os.environ["OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_URL"],
            os.environ.get("OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_TOKEN", ""),
        )
    service = InvestigatorWorkflowService(
        runtime_connect=_connect("OLIN_INVESTIGATOR_DATABASE_URL"),
        canonical_connect=_connect("OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL"),
        action_connect=_connect("OLIN_INVESTIGATOR_ACTION_DATABASE_URL"),
        synthetic_operator=operator,
    )
    shadow = None
    if os.environ.get("OLIN_INVESTIGATOR_SHADOW_RUNNER_URL"):
        from .investigator_shadow_service import ShadowResearchService, ShadowTransport

        shadow = ShadowResearchService(
            service,
            _connect("OLIN_INVESTIGATOR_RESEARCH_DATABASE_URL"),
            ShadowTransport(
                os.environ["OLIN_INVESTIGATOR_SHADOW_RUNNER_URL"],
                os.environ.get("OLIN_INVESTIGATOR_SHADOW_RUNNER_TOKEN", ""),
                provider=os.environ.get("OLIN_INVESTIGATOR_SHADOW_PROVIDER", "fake"),
                model=os.environ.get(
                    "OLIN_INVESTIGATOR_SHADOW_MODEL", "deterministic-fake-1"
                ),
            ),
            synthetic_cases=json.loads(
                os.environ.get("OLIN_INVESTIGATOR_SHADOW_SYNTHETIC_CASES", "[]")
            ),
        )
    server = ThreadingHTTPServer(
        (args.host, args.port), build_handler(authenticator, service, shadow)
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
