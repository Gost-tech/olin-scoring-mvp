"""Real disposable PostgreSQL reporting capture/currentness regressions."""

import json
import unittest
from unittest.mock import patch
from uuid import UUID

import olin.investigator_reports as reports
import test_investigator_postgres_workflow as pg
from olin.investigator_app import AnalystIdentity, InvestigatorAppError
from olin.investigator_reports import capture, render


@unittest.skipUnless(pg.POSTGRES_AVAILABLE, "explicit disposable PostgreSQL required")
class ReportPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.InvestigatorPostgresWorkflowTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        pg.InvestigatorPostgresWorkflowTests.tearDownClass()

    def setUp(self):
        self.case = pg.InvestigatorPostgresWorkflowTests()
        self.case.setUp()
        self.service = self.case.service
        self.identity = self.case.identity
        self.case_id = self.case.case_id

    def test_original_pair_deterministic_bound_and_non_mutating(self):
        actions = self.service.list_actions(self.identity, self.case_id)
        frozen = capture(self.service, self.identity, self.case_id)
        pair = render(frozen)
        self.assertEqual(pair, render(frozen))
        self.assertEqual(pair["brief"]["manifest"], pair["annex"]["manifest"])
        self.assertEqual(
            actions, self.service.list_actions(self.identity, self.case_id)
        )
        r = pair["annex"]["reconstruction"]
        self.assertEqual(r["observed_values"][0]["value"], "118000")
        self.assertEqual(r["claimed_values"][0]["value"], "260000")
        self.assertEqual(r["derived_values"][0]["value"], "142000")
        self.assertEqual(pair["brief"]["bank_question"], "NOT PROVIDED")
        self.assertEqual(pair["annex"]["human_signoffs"], "NOT PROVIDED")
        self.assertTrue(
            all(x["value_type"] == "UNKNOWN_VALUE" for x in r["unresolved_quantities"])
        )
        self.assertNotIn("shadow", json.dumps(pair["annex"]["action_history"]))

    def test_cross_tenant_and_role_denied(self):
        for identity in (
            AnalystIdentity("other", self.case.other_tenant, "analyst"),
            AnalystIdentity("fake", self.identity.tenant_id, "admin"),
        ):
            with self.assertRaises(InvestigatorAppError):
                self.service.current_report(identity, self.case_id)

    def test_oversized_capture_fails_without_truncation(self):
        with (
            patch.object(reports, "MAX_REPORT_INPUT_BYTES", 1),
            self.assertRaises(InvestigatorAppError),
        ):
            self.service.current_report(self.identity, self.case_id)

    def test_unlisted_history_fields_never_enter_reports(self):
        self.case._select_and_request("report-projection")
        original = reports._actions

        def extra(*args):
            rows = original(*args)
            rows[0]["action"]["private_research_response"] = (
                "UNTRUSTED_RESEARCH_SENTINEL"
            )
            return rows

        with patch.object(reports, "_actions", side_effect=extra):
            pair = self.service.current_report(self.identity, self.case_id)
        self.assertNotIn("UNTRUSTED_RESEARCH_SENTINEL", json.dumps(pair))
        self.assertNotIn("idempotency_key", json.dumps(pair))

    def test_revoked_evidence_cannot_generate_report(self):
        self.service.current_report(self.identity, self.case_id)
        record, revision = self.case.admin.execute(
            "SELECT canonical_record,authority_revision FROM evidence_authority.investigator_evidence_projection_change WHERE tenant_id=%s AND case_id=%s ORDER BY authority_revision DESC LIMIT 1",
            (self.identity.tenant_id, self.case_id),
        ).fetchone()
        record["usability"] = "UNUSABLE"
        record["unusable_reason"] = "EVIDENCE_REVOKED"
        with (
            self.case._connect(self.case.authority_role)() as authority,
            authority.transaction(),
        ):
            self.case.operator._authority_context(authority, self.identity.tenant_id)
            authority.execute(
                "SELECT evidence_authority.commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(record), revision, "EVIDENCE_REVOKED"),
            )
        with self.assertRaises(InvestigatorAppError):
            self.service.current_report(self.identity, self.case_id)

    def test_historical_invalidation_is_audit_only_not_current_authority(self):
        from datetime import datetime, timezone

        old = self.service.current_report(self.identity, self.case_id)["manifest"]
        with (
            self.case._connect(self.case.runtime_role)() as runtime,
            runtime.transaction(),
        ):
            self.case.operator._runtime_context(runtime, self.identity.tenant_id)
            runtime.execute(
                "SELECT investigator.invalidate_snapshot(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.identity.tenant_id,
                    self.case_id,
                    UUID(old["snapshot_id"]),
                    old["event_cutoff"],
                    "PROVENANCE_FAILURE",
                    "synthetic-review-reference",
                    datetime.now(timezone.utc),
                    "report-invalidation",
                ),
            )
        with self.assertRaises(InvestigatorAppError):
            self.service.current_report(self.identity, self.case_id)
        with (
            self.case._connect(self.case.runtime_role)() as runtime,
            runtime.transaction(),
        ):
            self.case.operator._runtime_context(runtime, self.identity.tenant_id)
            runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (
                    self.identity.tenant_id,
                    self.case_id,
                    old["event_cutoff"] + 1,
                    "report-replacement-snapshot",
                ),
            )
        pair = self.service.current_report(self.identity, self.case_id)
        self.assertNotEqual(pair["manifest"]["snapshot_id"], old["snapshot_id"])
        historical = pair["annex"]["historical_snapshot_invalidations"]
        self.assertEqual(len(historical), 1)
        self.assertEqual(historical[0]["snapshot_id"], old["snapshot_id"])
        self.assertEqual(historical[0]["reason_code"], "PROVENANCE_FAILURE")
        self.assertNotIn("authentication_reference", historical[0])

    def test_connections_closed_before_render(self):
        connections = []
        originals = [
            self.service._runtime_connect,
            self.service._canonical_connect,
            self.service._action_connect,
        ]

        def connect(factory):
            connection = factory()
            connections.append(connection)
            return connection

        from functools import partial

        with (
            patch.object(
                self.service, "_runtime_connect", partial(connect, originals[0])
            ),
            patch.object(
                self.service, "_canonical_connect", partial(connect, originals[1])
            ),
            patch.object(
                self.service, "_action_connect", partial(connect, originals[2])
            ),
        ):
            frozen = capture(self.service, self.identity, self.case_id)
        self.assertTrue(connections and all(c.closed for c in connections))
        self.assertEqual(render(frozen)["manifest"]["case_id"], str(self.case_id))

    def test_concurrent_authority_change_is_fenced(self):
        from concurrent.futures import ThreadPoolExecutor

        original = reports._actions
        checked = []

        def attempt_authority_change():
            record, revision = self.case.admin.execute(
                "SELECT canonical_record,authority_revision FROM evidence_authority.investigator_evidence_projection_change WHERE tenant_id=%s AND case_id=%s ORDER BY authority_revision DESC LIMIT 1",
                (self.identity.tenant_id, self.case_id),
            ).fetchone()
            record["usability"] = "UNUSABLE"
            record["unusable_reason"] = "EVIDENCE_REVOKED"
            with (
                self.case._connect(self.case.authority_role)() as authority,
                authority.transaction(),
            ):
                self.case.operator._authority_context(
                    authority, self.identity.tenant_id
                )
                authority.execute("SET LOCAL lock_timeout='100ms'")
                with self.assertRaises(pg.psycopg.errors.LockNotAvailable):
                    authority.execute(
                        "SELECT evidence_authority.commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                        (json.dumps(record), revision, "EVIDENCE_REVOKED"),
                    )

        def held(*args):
            value = original(*args)
            if not checked:
                checked.append(True)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(attempt_authority_change).result(timeout=3)
            return value

        with patch.object(reports, "_actions", side_effect=held):
            pair = self.service.current_report(self.identity, self.case_id)
        self.assertEqual(pair["brief"]["manifest"], pair["annex"]["manifest"])
        self.assertTrue(checked)

    def test_updated_coverage_and_unresolved_history(self):
        action = self.case._select_and_request("report-useful")
        self.service.synthetic_response(
            self.identity,
            self.case_id,
            UUID(action["action"]["action_id"]),
            fixture="useful_coverage",
        )
        pair = self.service.current_report(self.identity, self.case_id)
        coverage = {x["coverage_type"]: x["status"] for x in pair["brief"]["coverage"]}
        self.assertEqual(coverage["BANK_ACCOUNT_COVERAGE"], "COMPLETE")
        self.assertEqual(coverage["REVENUE_CHANNEL_COVERAGE"], "UNKNOWN")
        self.assertEqual(len(pair["brief"]["newly_supported_evidence"]), 1)

    def test_unavailable_preserves_stop_reason(self):
        action = self.case._select_and_request("report-stop")
        self.service.synthetic_response(
            self.identity,
            self.case_id,
            UUID(action["action"]["action_id"]),
            fixture="unavailable",
        )
        brief = self.service.current_report(self.identity, self.case_id)["brief"]
        self.assertEqual(brief["human_actions"][0]["status"], "STOPPED")
        self.assertEqual(brief["human_actions"][0]["reason"], "EVIDENCE_UNAVAILABLE")
        self.assertEqual(brief["newly_supported_evidence"], [])

    def test_concurrent_durable_history_change_fails_capture(self):
        action = self.case._select_and_request("report-concurrent")
        original = reports._actions
        calls = []

        def changing(*args):
            value = original(*args)
            calls.append(1)
            if len(calls) == 1:
                self.service.transition_action(
                    self.identity,
                    self.case_id,
                    UUID(action["action"]["action_id"]),
                    expected_sequence=2,
                    to_status="STOPPED",
                    reason_code="EVIDENCE_UNAVAILABLE",
                    reason_detail="No record available",
                    evidence_references=[],
                    effort_minutes=None,
                    cost_amount=None,
                    cost_currency=None,
                    idempotency_key="concurrent-stop",
                )
            return value

        with (
            patch.object(reports, "_actions", side_effect=changing),
            self.assertRaises(InvestigatorAppError),
        ):
            self.service.current_report(self.identity, self.case_id)
        self.assertEqual(
            self.service.current_report(self.identity, self.case_id)["brief"][
                "human_actions"
            ][0]["status"],
            "STOPPED",
        )
