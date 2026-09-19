"""PostgreSQL 16 integration for the Phase 5A human workflow.

Set OLIN_INVESTIGATOR_TEST_ADMIN_DSN to an explicitly disposable database whose
name ends in ``_investigator_test`` and OLIN_INVESTIGATOR_TEST_DISPOSABLE=YES.
"""

from __future__ import annotations

import os
import secrets
import unittest
from pathlib import Path
from uuid import UUID, uuid4

ADMIN_DSN = os.getenv("OLIN_INVESTIGATOR_TEST_ADMIN_DSN", "").strip()
DISPOSABLE = os.getenv("OLIN_INVESTIGATOR_TEST_DISPOSABLE", "") == "YES"
REQUIRED = os.getenv("OLIN_INVESTIGATOR_REQUIRE_POSTGRES_TESTS", "") == "1"

try:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
except ImportError:
    psycopg = None

POSTGRES_AVAILABLE = bool(ADMIN_DSN and DISPOSABLE and psycopg is not None)
if REQUIRED and not POSTGRES_AVAILABLE:
    raise RuntimeError(
        "required Phase 5A PostgreSQL tests need psycopg and an explicitly disposable DSN"
    )

from olin.investigator_app import (
    AnalystIdentity,
    InvestigatorAppError,
    InvestigatorWorkflowService,
)
from olin.investigator_synthetic_operator import SyntheticEvidenceOperator


@unittest.skipUnless(
    POSTGRES_AVAILABLE, "explicitly disposable PostgreSQL DSN/psycopg required"
)
class InvestigatorPostgresWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = conninfo_to_dict(ADMIN_DSN)
        if not str(parsed.get("dbname", "")).endswith("_investigator_test"):
            raise RuntimeError("PostgreSQL workflow tests require *_investigator_test")
        cls.root = Path(__file__).resolve().parent
        cls.tenant = uuid4()
        cls.other_tenant = uuid4()
        cls.runtime_role = "olin_inv_t_" + cls.tenant.hex
        cls.action_role = "olin_action_t_" + cls.tenant.hex
        cls.authority_role = "olin_evidence_t_" + cls.tenant.hex
        cls.reader_role = "olin_canonical_t_" + cls.tenant.hex
        cls.passwords = {
            role: secrets.token_urlsafe(24)
            for role in (
                cls.runtime_role,
                cls.action_role,
                cls.authority_role,
                cls.reader_role,
            )
        }
        cls.admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        for migration in (
            "0001_investigator_phase0.sql",
            "0002_investigator_case_event_snapshot.sql",
            "0003_investigator_evidence_consent_passport.sql",
            "0004_investigator_evidence_reasoning_readiness.sql",
            "0005_investigator_phase3_assertion_metadata.sql",
            "0006_investigator_human_action_workflow.sql",
        ):
            cls.admin.execute(
                (cls.root / "db" / "migrations" / migration).read_text(encoding="utf-8")
            )
        for role, password in cls.passwords.items():
            inheritance = "INHERIT" if role == cls.reader_role else "NOINHERIT"
            cls.admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} {} NOSUPERUSER "
                    "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(
                    sql.Identifier(role),
                    sql.Literal(password),
                    sql.SQL(inheritance),
                )
            )
        cls.admin.execute(
            sql.SQL("GRANT olin_investigator_runtime TO {}").format(
                sql.Identifier(cls.runtime_role)
            )
        )
        cls.admin.execute(
            sql.SQL("GRANT olin_investigator_action_writer TO {}").format(
                sql.Identifier(cls.action_role)
            )
        )
        cls.admin.execute(
            sql.SQL("GRANT olin_investigator_evidence_authority TO {}").format(
                sql.Identifier(cls.authority_role)
            )
        )
        cls.admin.execute(
            sql.SQL("GRANT olin_investigator_evidence_reader TO {}").format(
                sql.Identifier(cls.reader_role)
            )
        )
        cls.admin.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                sql.Identifier(cls.reader_role)
            )
        )
        cls.identity = AnalystIdentity("phase5a-analyst", cls.tenant, "analyst")

    @classmethod
    def _dsn(cls, role):
        values = conninfo_to_dict(ADMIN_DSN)
        values.update(user=role, password=cls.passwords[role])
        return make_conninfo(**values)

    @classmethod
    def _connect(cls, role):
        return lambda: psycopg.connect(cls._dsn(role))

    def setUp(self):
        self.case_id = uuid4()
        self.operator = SyntheticEvidenceOperator(
            self._connect(self.runtime_role), self._connect(self.authority_role)
        )
        self.operator.setup_target_case(tenant_id=self.tenant, case_id=self.case_id)

        class InProcessOperator:
            def __init__(inner, operator):
                inner.operator = operator

            def submit(inner, **values):
                return inner.operator.handle(values)

        self.service = InvestigatorWorkflowService(
            runtime_connect=self._connect(self.runtime_role),
            canonical_connect=self._connect(self.reader_role),
            action_connect=self._connect(self.action_role),
            synthetic_operator=InProcessOperator(self.operator),
        )

    @classmethod
    def tearDownClass(cls):
        for role, group in (
            (cls.runtime_role, "olin_investigator_runtime"),
            (cls.action_role, "olin_investigator_action_writer"),
            (cls.authority_role, "olin_investigator_evidence_authority"),
            (cls.reader_role, "olin_investigator_evidence_reader"),
        ):
            cls.admin.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(group), sql.Identifier(role)
                )
            )
            cls.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        cls.admin.execute("DROP SCHEMA IF EXISTS evidence_authority CASCADE")
        cls.admin.execute("DROP SCHEMA investigator CASCADE")
        cls.admin.execute("DROP ROLE IF EXISTS olin_investigator_evidence_reader")
        cls.admin.execute("DROP ROLE IF EXISTS olin_investigator_action_writer")
        cls.admin.execute("DROP ROLE olin_investigator_evidence_authority")
        cls.admin.execute("DROP ROLE olin_investigator_runtime")
        cls.admin.execute("DROP ROLE olin_investigator_owner")
        cls.admin.close()

    def _select_and_request(self, key: str):
        selected = self.service.select_action(
            self.identity,
            self.case_id,
            action_type="REQUEST_ACCOUNT_CHANNEL_RECORD",
            rationale="Determine whether bank account coverage is complete.",
            idempotency_key=f"select-{key}",
        )
        return self.service.transition_action(
            self.identity,
            self.case_id,
            UUID(selected["action"]["action_id"]),
            expected_sequence=1,
            to_status="REQUESTED",
            reason_code=None,
            reason_detail=None,
            evidence_references=[],
            effort_minutes=None,
            cost_amount=None,
            cost_currency=None,
            idempotency_key=f"request-{key}",
        )

    def test_a_complete_useful_human_journey_recomputes_current_analysis(self):
        before = self.service.current_analysis(self.identity, self.case_id)
        reconstruction = before["reconstruction"]
        self.assertEqual(
            [x["value"] for x in reconstruction["observed_values"]], ["118000"]
        )
        self.assertEqual(
            [x["value"] for x in reconstruction["claimed_values"]], ["260000"]
        )
        self.assertEqual(
            [
                x["value"]
                for x in reconstruction["derived_values"]
                if x["quantity"] == "revenue_reconciliation_gap"
            ],
            ["142000"],
        )
        requested = self._select_and_request("useful")
        action_id = UUID(requested["action"]["action_id"])
        self.service.synthetic_response(
            self.identity, self.case_id, action_id, fixture="useful_coverage"
        )
        replay = self.service.synthetic_response(
            self.identity, self.case_id, action_id, fixture="useful_coverage"
        )
        self.assertTrue(replay["replayed"])
        after = self.service.current_analysis(self.identity, self.case_id)
        coverage = {
            item["coverage_type"]: item["status"]
            for item in after["reconstruction"]["coverage_diagnostics"]
        }
        self.assertEqual(coverage["BANK_ACCOUNT_COVERAGE"], "COMPLETE")
        self.assertEqual(coverage["REVENUE_CHANNEL_COVERAGE"], "UNKNOWN")
        self.assertIn(
            "total_sustainable_revenue",
            {x["quantity"] for x in after["reconstruction"]["unresolved_quantities"]},
        )
        self.assertNotEqual(
            before["reconstruction"]["input_assessment"]["snapshot_id"],
            after["reconstruction"]["input_assessment"]["snapshot_id"],
        )
        self.assertEqual(
            [
                item["proposition_type"]
                for item in after["change_summary"]["canonical_evidence_added"]
            ],
            ["bank_account_coverage"],
        )
        self.assertEqual(
            after["change_summary"]["current_coverage_supported_by_added_evidence"],
            ["BANK_ACCOUNT_COVERAGE"],
        )
        history = self.service.list_actions(self.identity, self.case_id)[0]
        self.assertEqual(history["action"]["selected_by_analyst"], "phase5a-analyst")
        self.assertTrue(
            all(
                item["transitioned_by_analyst"] == "phase5a-analyst"
                for item in history["transitions"]
            )
        )

    def test_b_duplicate_response_does_not_change_current_support(self):
        before = self.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]
        requested = self._select_and_request("duplicate")
        action_id = UUID(requested["action"]["action_id"])
        self.service.synthetic_response(
            self.identity, self.case_id, action_id, fixture="duplicate_response"
        )
        after = self.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]
        self.assertEqual(before["observed_values"], after["observed_values"])
        self.assertEqual(before["coverage_diagnostics"], after["coverage_diagnostics"])
        history = self.service.list_actions(self.identity, self.case_id)[0][
            "transitions"
        ]
        self.assertEqual(history[-1]["to_status"], "COMPLETED_UNRESOLVED")

    def test_c_unavailable_response_stops_without_adverse_inference(self):
        requested = self._select_and_request("unavailable")
        action_id = UUID(requested["action"]["action_id"])
        self.service.synthetic_response(
            self.identity, self.case_id, action_id, fixture="unavailable"
        )
        history = self.service.list_actions(self.identity, self.case_id)[0][
            "transitions"
        ]
        self.assertEqual(history[-1]["to_status"], "STOPPED")
        self.assertEqual(history[-1]["reason_code"], "EVIDENCE_UNAVAILABLE")
        current = self.service.current_analysis(self.identity, self.case_id)
        self.assertIn(
            "total_sustainable_revenue",
            {x["quantity"] for x in current["reconstruction"]["unresolved_quantities"]},
        )

    def test_d_duplicate_commands_converge_and_stale_transition_fails(self):
        first = self._select_and_request("idempotent")
        replay = self.service.select_action(
            self.identity,
            self.case_id,
            action_type="REQUEST_ACCOUNT_CHANNEL_RECORD",
            rationale="Determine whether bank account coverage is complete.",
            idempotency_key="select-idempotent",
        )
        self.assertEqual(first["action"]["action_id"], replay["action"]["action_id"])
        with self.assertRaises(psycopg.errors.SerializationFailure):
            self.service.transition_action(
                self.identity,
                self.case_id,
                UUID(first["action"]["action_id"]),
                expected_sequence=1,
                to_status="STOPPED",
                reason_code="EVIDENCE_UNAVAILABLE",
                reason_detail="stale writer",
                evidence_references=[],
                effort_minutes=None,
                cost_amount=None,
                cost_currency=None,
                idempotency_key="stale-transition",
            )
        history = self.service.list_actions(self.identity, self.case_id)[0][
            "transitions"
        ]
        self.assertEqual(len(history), 2)
        self.assertNotIn(
            "stale-transition", {item["idempotency_key"] for item in history}
        )

    def test_e_cross_tenant_and_stale_snapshot_selection_fail_closed(self):
        with self.assertRaises(InvestigatorAppError):
            self.service.current_analysis(
                AnalystIdentity("other", self.other_tenant, "analyst"), self.case_id
            )
        current = self.service.current_analysis(self.identity, self.case_id)
        case_version = current["case_version"]
        with self._connect(self.runtime_role)() as runtime, runtime.transaction():
            runtime.execute("SET LOCAL ROLE olin_investigator_runtime")
            runtime.execute(
                "SELECT set_config('olin.tenant_id',%s,true)", (str(self.tenant),)
            )
            parent = runtime.execute(
                "SELECT event_id FROM investigator.investigation_event WHERE tenant_id=%s "
                "AND case_id=%s AND event_sequence=%s",
                (self.tenant, self.case_id, case_version),
            ).fetchone()[0]
            runtime.execute(
                "SELECT investigator.append_event(%s,%s,%s,%s,%s,statement_timestamp(),"
                "'{}'::jsonb,1,%s,%s,%s)",
                (
                    self.tenant,
                    self.case_id,
                    case_version,
                    uuid4(),
                    "INVESTIGATION_EVENT_RECORDED",
                    f"stale-{self.case_id}",
                    "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
                    parent,
                ),
            )
        with self.assertRaises(InvestigatorAppError):
            self.service.select_action(
                self.identity,
                self.case_id,
                action_type="REQUEST_ACCOUNT_CHANNEL_RECORD",
                rationale="This selection must not use the stale analysis.",
                idempotency_key="stale-select",
            )

    def test_f_action_writer_cannot_manufacture_accepted_evidence(self):
        original = self.service.current_analysis(self.identity, self.case_id)
        preexisting_reference = original["reconstruction"]["observed_values"][0][
            "provenance"
        ][0]["reference_id"]
        requested = self._select_and_request("forged-acceptance")
        action_id = UUID(requested["action"]["action_id"])
        with self._connect(self.action_role)() as connection, connection.transaction():
            connection.execute("SET LOCAL ROLE olin_investigator_action_writer")
            connection.execute(
                "SELECT set_config('olin.tenant_id',%s,true)", (str(self.tenant),)
            )
            connection.execute(
                "SELECT investigator.transition_investigation_action("
                "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)",
                (
                    self.tenant,
                    action_id,
                    2,
                    "RESPONSE_RECEIVED",
                    None,
                    None,
                    "[]",
                    None,
                    None,
                    None,
                    "phase5a-analyst",
                    "direct-response",
                ),
            )
        for key, reference_id in (
            ("preexisting-acceptance", preexisting_reference),
            ("forged-acceptance", str(uuid4())),
        ):
            with (
                self.subTest(reference_id=reference_id),
                self.assertRaises(psycopg.errors.InsufficientPrivilege),
                self._connect(self.action_role)() as connection,
                connection.transaction(),
            ):
                connection.execute("SET LOCAL ROLE olin_investigator_action_writer")
                connection.execute(
                    "SELECT set_config('olin.tenant_id',%s,true)",
                    (str(self.tenant),),
                )
                connection.execute(
                    "SELECT investigator.transition_investigation_action("
                    "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)",
                    (
                        self.tenant,
                        action_id,
                        3,
                        "EVIDENCE_ACCEPTED",
                        None,
                        None,
                        f'["{reference_id}"]',
                        None,
                        None,
                        None,
                        "phase5a-analyst",
                        key,
                    ),
                )
        history = self.service.list_actions(self.identity, self.case_id)[0][
            "transitions"
        ]
        self.assertEqual(history[-1]["to_status"], "RESPONSE_RECEIVED")

    def test_g_snapshot_creation_failure_is_recoverable_by_retry(self):
        requested = self._select_and_request("recover-snapshot")
        action_id = UUID(requested["action"]["action_id"])
        create_snapshot = self.operator._create_current_snapshot

        def fail_once(*_args, **_kwargs):
            raise RuntimeError("injected snapshot failure")

        self.operator._create_current_snapshot = fail_once
        with self.assertRaises(RuntimeError):
            self.service.synthetic_response(
                self.identity, self.case_id, action_id, fixture="useful_coverage"
            )
        self.operator._create_current_snapshot = create_snapshot
        recovered = self.service.synthetic_response(
            self.identity, self.case_id, action_id, fixture="useful_coverage"
        )
        self.assertTrue(recovered["replayed"])
        current = self.service.current_analysis(self.identity, self.case_id)
        self.assertEqual(
            {
                item["coverage_type"]: item["status"]
                for item in current["reconstruction"]["coverage_diagnostics"]
            }["BANK_ACCOUNT_COVERAGE"],
            "COMPLETE",
        )


if __name__ == "__main__":
    unittest.main()
