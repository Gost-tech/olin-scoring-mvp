from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from olin.investigator.workflow import (
    ACTION_CATALOGUE,
    ACTION_CATALOGUE_VERSION,
    ActionStatus,
    ActionType,
    WorkflowValidationError,
    action_definition,
    require_terminal_reason,
    require_transition,
    validate_effort_cost,
)
from olin.investigator_app import (
    AnalystIdentity,
    InvestigatorAppError,
    InvestigatorAuthenticator,
    InvestigatorWorkflowService,
    LoopbackSyntheticOperator,
    build_handler,
)
from olin.investigator_synthetic_operator import _resolution, _semantics

TENANT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
CASE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ACTION = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class FakeService:
    def __init__(self):
        self.calls = []

    def current_analysis(self, identity, case_id):
        self.calls.append(("analysis", identity, case_id))
        return {
            "case_id": str(case_id),
            "demonstration": "SYNTHETIC DEMONSTRATION",
            "server_checked_at": "2026-09-19T12:00:00.000000Z",
            "tenant_id": str(identity.tenant_id),
        }

    def list_actions(self, identity, case_id):
        self.calls.append(("list", identity, case_id))
        return []

    def select_action(self, identity, case_id, **values):
        self.calls.append(("select", identity, case_id, values))
        return {"action": {"action_id": str(ACTION)}, "transitions": []}

    def transition_action(self, identity, case_id, action_id, **values):
        self.calls.append(("transition", identity, case_id, action_id, values))
        return {"action": {"action_id": str(action_id)}, "transitions": []}

    def synthetic_response(self, identity, case_id, action_id, **values):
        self.calls.append(("synthetic", identity, case_id, action_id, values))
        return {"outcome": "COMPLETED_UNRESOLVED", "synthetic": True}


class Phase5AWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.auth = InvestigatorAuthenticator(
            {
                "ana": {
                    "token": "test-only-analyst-token",
                    "role": "analyst",
                    "tenant_id": str(TENANT),
                },
                "bea": {
                    "token": "test-only-other-token",
                    "role": "analyst",
                    "tenant_id": str(OTHER_TENANT),
                },
            },
            "test-only-session-secret-32-characters-minimum",
        )

    def _request(self, service, method, path, *, body=None, token=None):
        payload = b"" if body is None else json.dumps(body).encode()
        headers = [f"{method} {path} HTTP/1.1", "Host: investigator.test"]
        if payload:
            headers.extend(
                ["Content-Type: application/json", f"Content-Length: {len(payload)}"]
            )
        if token:
            headers.append(f"Authorization: Bearer {token}")
        raw = ("\r\n".join(headers) + "\r\n\r\n").encode() + payload

        class Socket:
            def __init__(self):
                self.input = BytesIO(raw)
                self.output = BytesIO()

            def makefile(self, mode, buffering=None):
                del buffering
                if "r" in mode:
                    return self.input
                return self.output

            def sendall(self, value):
                self.output.write(value)

        connection = Socket()
        build_handler(self.auth, service)(connection, ("127.0.0.1", 1), object())
        response = connection.output.getvalue()
        head, encoded = response.split(b"\r\n\r\n", 1)
        status = int(head.split(b" ", 2)[1])
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            key, value = line.decode().split(":", 1)
            headers[key.lower()] = value.strip()
        return status, headers, json.loads(encoded) if encoded else None

    def test_catalogue_is_small_explicit_and_versioned(self):
        self.assertEqual(len(ACTION_CATALOGUE), 2)
        self.assertEqual(
            set(ACTION_CATALOGUE),
            {
                ActionType.REQUEST_ACCOUNT_CHANNEL_RECORD,
                ActionType.CLARIFY_MERCHANT_ASSERTION_SCOPE,
            },
        )
        self.assertTrue(
            all(
                item.catalogue_version == ACTION_CATALOGUE_VERSION
                and item.prerequisites
                and item.resolution_criteria
                for item in ACTION_CATALOGUE.values()
            )
        )

    def test_unknown_action_and_invalid_transitions_fail_closed(self):
        with self.assertRaises(WorkflowValidationError):
            action_definition("AUTONOMOUS_PROVIDER_CRAWL")
        require_transition(ActionStatus.SELECTED, ActionStatus.REQUESTED)
        require_transition(ActionStatus.REQUESTED, ActionStatus.RESPONSE_RECEIVED)
        with self.assertRaises(WorkflowValidationError):
            require_transition(ActionStatus.SELECTED, ActionStatus.EVIDENCE_ACCEPTED)
        with self.assertRaises(WorkflowValidationError):
            require_transition(
                ActionStatus.EVIDENCE_ACCEPTED, ActionStatus.COMPLETED_RESOLVED
            )
        with self.assertRaises(WorkflowValidationError):
            require_transition(ActionStatus.STOPPED, ActionStatus.REQUESTED)

    def test_unresolved_terminal_state_requires_closed_reason(self):
        require_terminal_reason(ActionStatus.STOPPED, "EVIDENCE_UNAVAILABLE")
        with self.assertRaises(WorkflowValidationError):
            require_terminal_reason(ActionStatus.STOPPED, None)
        with self.assertRaises(WorkflowValidationError):
            require_terminal_reason(ActionStatus.REQUESTED, "EVIDENCE_UNAVAILABLE")

    def test_unknown_cost_is_not_zero_and_actual_cost_is_bounded(self):
        self.assertEqual(
            validate_effort_cost(
                effort_minutes=None, cost_amount=None, cost_currency=None
            ),
            (None, None, None),
        )
        self.assertEqual(
            validate_effort_cost(
                effort_minutes=15, cost_amount="12.50", cost_currency="MXN"
            ),
            (15, "12.50", "MXN"),
        )
        with self.assertRaises(WorkflowValidationError):
            validate_effort_cost(
                effort_minutes=None, cost_amount=None, cost_currency="MXN"
            )

    def test_session_is_tenant_bound_short_lived_and_tamper_evident(self):
        token = self.auth.issue("ana", "test-only-analyst-token", now=100)
        identity = self.auth.authenticate(f"Bearer {token}", now=101)
        self.assertEqual(identity, AnalystIdentity("ana", TENANT, "analyst"))
        with self.assertRaises(InvestigatorAppError):
            self.auth.authenticate(f"Bearer {token}x", now=101)
        with self.assertRaises(InvestigatorAppError):
            self.auth.authenticate(f"Bearer {token}", now=100 + 15 * 60)

    def test_external_synthetic_operator_target_is_rejected(self):
        with self.assertRaises(RuntimeError):
            LoopbackSyntheticOperator(
                "https://provider.example/api", "test-only-operator-token"
            )

    def test_http_requires_auth_and_derives_tenant_from_session(self):
        service = FakeService()
        status, _, _ = self._request(service, "GET", f"/api/cases/{CASE}")
        self.assertEqual(status, 401)
        status, _, session = self._request(
            service,
            "POST",
            "/api/session",
            body={"name": "ana", "token": "test-only-analyst-token"},
        )
        self.assertEqual(status, 200)
        status, headers, body = self._request(
            service,
            "GET",
            f"/api/cases/{CASE}?tenant_id={OTHER_TENANT}",
            token=session["access_token"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["cache-control"], "no-store, private, max-age=0")
        self.assertEqual(body["tenant_id"], str(TENANT))
        self.assertEqual(service.calls[-1][1].tenant_id, TENANT)

    def test_http_never_accepts_actor_or_tenant_fields_for_action_selection(self):
        service = FakeService()
        _, _, session = self._request(
            service,
            "POST",
            "/api/session",
            body={"name": "ana", "token": "test-only-analyst-token"},
        )
        status, _, _ = self._request(
            service,
            "POST",
            f"/api/cases/{CASE}/actions",
            token=session["access_token"],
            body={
                "action_type": "REQUEST_ACCOUNT_CHANNEL_RECORD",
                "rationale": "Resolve current coverage uncertainty.",
                "idempotency_key": "selection-1",
                "tenant_id": str(OTHER_TENANT),
                "actor": "forged-admin",
            },
        )
        self.assertEqual(status, 201)
        call = service.calls[-1]
        self.assertEqual(call[1].name, "ana")
        self.assertEqual(call[1].tenant_id, TENANT)
        self.assertNotIn("tenant_id", call[3])
        self.assertNotIn("actor", call[3])

    def test_workspace_is_synthetic_and_has_no_lending_controls(self):
        source = (Path(__file__).parent / "olin" / "investigator_app.py").read_text()
        self.assertIn("SYNTHETIC DEMONSTRATION", source)
        for prohibited in (
            "Institución aprueba",
            "Aprobar crédito",
            "approved_mxn",
            "Puntaje Olin",
            "score_application",
            "disburse",
        ):
            self.assertNotIn(prohibited, source)

    def test_operator_source_has_no_live_provider_or_network_provider_import(self):
        source = (
            Path(__file__).parent / "olin" / "investigator_synthetic_operator.py"
        ).read_text()
        for prohibited in ("belvo", "syncfy", "requests.", "openai", "anthropic"):
            self.assertNotIn(prohibited, source.lower())
        self.assertIn('args.host not in {"127.0.0.1", "localhost"}', source)

    def test_analyst_transition_cannot_promote_or_attach_evidence(self):
        service = InvestigatorWorkflowService(
            runtime_connect=lambda: None,
            canonical_connect=lambda: None,
            action_connect=lambda: None,
        )
        identity = AnalystIdentity("ana", TENANT, "analyst")
        common = {
            "expected_sequence": 2,
            "reason_code": None,
            "reason_detail": None,
            "effort_minutes": None,
            "cost_amount": None,
            "cost_currency": None,
            "idempotency_key": "forged-evidence",
        }
        with self.assertRaises(InvestigatorAppError) as promoted:
            service.transition_action(
                identity,
                CASE,
                ACTION,
                to_status="EVIDENCE_ACCEPTED",
                evidence_references=[str(uuid4())],
                **common,
            )
        self.assertEqual(promoted.exception.code, "CANONICAL_HANDOFF_REQUIRED")
        with self.assertRaises(InvestigatorAppError) as attached:
            service.transition_action(
                identity,
                CASE,
                ACTION,
                to_status="STOPPED",
                evidence_references=[str(uuid4())],
                **(common | {"reason_code": "EVIDENCE_UNAVAILABLE"}),
            )
        self.assertEqual(attached.exception.code, "CANONICAL_HANDOFF_REQUIRED")

    def test_malformed_operator_response_cannot_create_accepted_transition(self):
        class MalformedOperator:
            def submit(self, **_values):
                return {
                    "synthetic": True,
                    "outcome": "EVIDENCE_ACCEPTED",
                    "evidence_reference": "not-a-uuid",
                    "new_snapshot_id": str(uuid4()),
                    "authority_revision": 3,
                }

        service = InvestigatorWorkflowService(
            runtime_connect=lambda: None,
            canonical_connect=lambda: None,
            action_connect=lambda: None,
            synthetic_operator=MalformedOperator(),
        )
        service.list_actions = lambda _identity, _case: [
            {
                "action": {
                    "action_id": str(ACTION),
                    "action_type": "REQUEST_ACCOUNT_CHANNEL_RECORD",
                    "selected_authority_revision": 2,
                },
                "transitions": [
                    {
                        "to_status": "REQUESTED",
                        "transition_sequence": 2,
                        "idempotency_key": "requested",
                        "evidence_references": [],
                    }
                ],
            }
        ]
        with self.assertRaises(InvestigatorAppError) as invalid:
            service.synthetic_response(
                AnalystIdentity("ana", TENANT, "analyst"),
                CASE,
                ACTION,
                fixture="useful_coverage",
            )
        self.assertEqual(invalid.exception.code, "INVALID_HANDOFF")

    def test_well_formed_preexisting_operator_reference_creates_no_transition(self):
        reference_id = str(uuid4())
        selected_snapshot_id = str(uuid4())
        current_snapshot_id = str(uuid4())

        class PreexistingOperator:
            def submit(self, **_values):
                return {
                    "synthetic": True,
                    "outcome": "EVIDENCE_ACCEPTED",
                    "evidence_reference": reference_id,
                    "new_snapshot_id": current_snapshot_id,
                    "authority_revision": 3,
                }

        service = InvestigatorWorkflowService(
            runtime_connect=lambda: None,
            canonical_connect=lambda: None,
            action_connect=lambda: None,
            synthetic_operator=PreexistingOperator(),
        )
        service.list_actions = lambda _identity, _case: [
            {
                "action": {
                    "action_id": str(ACTION),
                    "action_type": "REQUEST_ACCOUNT_CHANNEL_RECORD",
                    "selected_authority_revision": 2,
                    "selected_snapshot_id": selected_snapshot_id,
                },
                "transitions": [
                    {
                        "to_status": "REQUESTED",
                        "transition_sequence": 2,
                        "idempotency_key": "requested",
                        "evidence_references": [],
                    }
                ],
            }
        ]
        service.current_analysis = lambda _identity, _case: {
            "reconstruction": {
                "input_assessment": {
                    "snapshot_id": current_snapshot_id,
                    "authority_revision": 3,
                },
                "observed_values": [{"provenance": [{"reference_id": reference_id}]}],
                "claimed_values": [],
                "derived_values": [],
                "coverage_diagnostics": [],
                "unresolved_quantities": [],
                "contradictions_carried_forward": [],
            }
        }
        service._action_bound_evidence_delta = lambda *_args: False
        transitions = []
        service._transition_action = lambda *_args, **values: transitions.append(values)

        with self.assertRaises(InvestigatorAppError) as invalid:
            service.synthetic_response(
                AnalystIdentity("ana", TENANT, "analyst"),
                CASE,
                ACTION,
                fixture="useful_coverage",
            )
        self.assertEqual(invalid.exception.code, "INVALID_HANDOFF")
        self.assertEqual(transitions, [])

    def test_synthetic_coverage_fixture_is_canonical_and_explicitly_scoped(self):
        now = datetime.now(timezone.utc)
        flat, _, projection = _resolution(
            tenant_id=TENANT,
            case_id=CASE,
            reference_id=uuid4(),
            subject_id="synthetic-business",
            subject_digest="1" * 64,
            evidence_id="fixture-coverage",
            evidence_class="VERIFIED_FACT",
            verification_status="VERIFIED_FOR_PROPOSITION",
            proposition_type="bank_account_coverage",
            proposition_value="COMPLETE",
            proposition_unit="STATUS",
            verification_method="signed_provider_record_match",
            period_start=now - timedelta(days=30),
            period_end=now - timedelta(days=1),
            source_id="fixture_bank_registry",
            issuer_id="fixture-bank-issuer",
            source_class="regulated_financial_institution",
            acquisition_method="synthetic_fixture",
            semantics=_semantics(
                "coverage-lineage",
                "fixture-bank-issuer",
                economic_event_id="coverage-period",
            ),
            now=now,
        )
        self.assertEqual(flat["authority_digest"], projection["authority_digest"])
        self.assertEqual(flat["proposition_type"], "bank_account_coverage")
        self.assertEqual(flat["proposition_value"], "COMPLETE")
        self.assertEqual(flat["proposition_unit"], "STATUS")
        self.assertEqual(flat["acquisition_method"], "synthetic_fixture")


if __name__ == "__main__":
    unittest.main()
