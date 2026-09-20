"""Synthetic-only PostgreSQL attribution, correction and denominator proofs."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_investigator_postgres_shadow as shadow_tests
import test_investigator_postgres_workflow as pg
from olin.investigator_app import AnalystIdentity, InvestigatorAppError
from olin.investigator_feedback import FeedbackService


@unittest.skipUnless(pg.POSTGRES_AVAILABLE, "explicit disposable PostgreSQL required")
class FeedbackPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shadow_tests.InvestigatorPostgresShadowTests.setUpClass()
        cls.base = pg.InvestigatorPostgresWorkflowTests
        cls.base.admin.execute(
            Path("db/migrations/0008_investigator_feedback_cohort.sql").read_text()
        )
        cls.roles = []
        for prefix, group in (
            ("olin_feedback_t_", "olin_investigator_feedback"),
            ("olin_cohort_t_", "olin_investigator_cohort_operator"),
        ):
            role = prefix + cls.base.tenant.hex
            password = pg.secrets.token_urlsafe(24)
            cls.base.admin.execute(
                pg.sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(pg.sql.Identifier(role), pg.sql.Literal(password))
            )
            cls.base.admin.execute(
                pg.sql.SQL("GRANT {} TO {}").format(
                    pg.sql.Identifier(group), pg.sql.Identifier(role)
                )
            )
            cls.base.passwords[role] = password
            cls.roles.append(role)

    @classmethod
    def tearDownClass(cls):
        for role in cls.roles:
            cls.base.admin.execute(
                pg.sql.SQL("DROP ROLE {}").format(pg.sql.Identifier(role))
            )
        for role in ("olin_investigator_feedback", "olin_investigator_cohort_operator"):
            cls.base.admin.execute(
                pg.sql.SQL("DROP OWNED BY {}").format(pg.sql.Identifier(role))
            )
            cls.base.admin.execute(
                pg.sql.SQL("DROP ROLE {}").format(pg.sql.Identifier(role))
            )
        shadow_tests.InvestigatorPostgresShadowTests.tearDownClass()

    def setUp(self):
        self.case = self.base()
        self.case.setUp()
        self.identity = AnalystIdentity(
            "SYNTHETIC-analyst", self.base.tenant, "analyst"
        )
        self.case_id = self.case.case_id
        self.feedback = FeedbackService(
            self.case.service,
            self.base._connect(self.roles[0]),
            b"synthetic-only-receipt-secret-long-enough",
        )

    def body(self, **overrides):
        result = {
            "kind": "FEEDBACK",
            "receipt": self.feedback.report(self.identity, self.case_id)[
                "feedback_receipt"
            ],
            "action_id": None,
            "observation_status": "OBSERVED",
            "judgment": "USEFUL",
            "explanation": "SYNTHETIC fixture judgment, not actual human feedback",
            "source_description": None,
            "source_reference": None,
            "occurred_at": None,
            "predecessor": None,
            "expected_version": 0,
            "correction_reason": None,
            "idempotency_key": str(uuid4()),
        }
        result.update(overrides)
        return result

    def freeze(self, members, cohort=None, expected=0, key=None):
        definition = {
            "synthetic_only": True,
            "source_reference": "SYNTHETIC declared fixture universe",
            "eligibility_version": "synthetic-cohort-1",
            "amendment_reason": "SYNTHETIC initial freeze or explicit amendment",
            "members": [
                {
                    "case_id": str(c),
                    "eligible": True,
                    "reason": "Explicit synthetic member",
                }
                for c in members
            ],
        }
        with self.base._connect(self.roles[1])() as conn, conn.transaction():
            conn.execute("SET LOCAL ROLE olin_investigator_cohort_operator")
            conn.execute(
                "SELECT set_config('olin.tenant_id',%s,true)",
                (str(self.identity.tenant_id),),
            )
            return conn.execute(
                "SELECT investigator.freeze_cohort(%s,%s,%s,%s::jsonb,%s)",
                (
                    self.identity.tenant_id,
                    cohort or uuid4(),
                    expected,
                    json.dumps(definition),
                    key or str(uuid4()),
                ),
            ).fetchone()[0]

    def test_attributed_judgment_replay_and_no_authority_mutation(self):
        body = self.body()
        before = self.case.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]["input_assessment"]
        first = self.feedback.append(self.identity, self.case_id, body)
        for _ in range(3):
            self.assertEqual(
                first, self.feedback.append(self.identity, self.case_id, body)
            )
        self.assertEqual(first["actor"], "SYNTHETIC-analyst")
        self.assertEqual(
            first["authenticated_organization"],
            "tenant:" + str(self.identity.tenant_id),
        )
        self.assertEqual(first["attribution"], "ANALYST_JUDGMENT")
        self.assertIsNone(first["payload"]["occurred_at"])
        body["explanation"] = "Changed replay"
        with self.assertRaises(InvestigatorAppError):
            self.feedback.append(self.identity, self.case_id, body)
        after = self.case.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]["input_assessment"]
        for key in ("snapshot_digest", "authority_digest", "evidence_state_digest"):
            self.assertEqual(before[key], after[key])

    def test_forged_identity_trust_and_report_rejected(self):
        original = self.body()
        for key in (
            "actor",
            "tenant_id",
            "organization",
            "verified",
            "bank_confirmed",
            "source",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.feedback.append(
                    self.identity, self.case_id, {**original, key: "forged"}
                )
        for receipt in ("forged", original["receipt"] + "x"):
            with self.assertRaises(InvestigatorAppError):
                self.feedback.append(
                    self.identity, self.case_id, {**original, "receipt": receipt}
                )
        with self.assertRaises(ValueError):
            self.feedback.append(
                self.identity, self.case_id, {**original, "action_id": str(uuid4())}
            )

    def test_concurrent_identical_retries_converge_after_lost_response(self):
        body = self.body()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.feedback.append(self.identity, self.case_id, body),
                    range(2),
                )
            )
        self.assertEqual(results[0], results[1])
        self.assertEqual(
            len(self.feedback.history(self.identity, self.case_id)["annotations"]), 1
        )
        self.assertEqual(
            results[0], self.feedback.append(self.identity, self.case_id, body)
        )

    def test_cross_tenant_and_role_denied(self):
        body = self.body()
        for identity in (
            AnalystIdentity("other", self.base.other_tenant, "analyst"),
            AnalystIdentity("admin", self.base.tenant, "admin"),
        ):
            with self.assertRaises(InvestigatorAppError):
                self.feedback.history(identity, self.case_id)
            with self.assertRaises(InvestigatorAppError):
                self.feedback.append(identity, self.case_id, body)

    def test_external_report_is_not_bank_owned_or_preexposure(self):
        body = self.body(
            kind="EXTERNAL_OUTCOME",
            judgment=None,
            source_description="SYNTHETIC person reportedly representing a lender",
            source_reference="synthetic-note",
            occurred_at="2026-01-01T00:00:00Z",
        )
        record = self.feedback.append(self.identity, self.case_id, body)
        self.assertEqual(record["attribution"], "ANALYST_REPORTED_EXTERNAL")
        self.assertGreater(record["recorded_at"], body["occurred_at"])
        self.assertIn(
            "NOT ESTABLISHED",
            self.feedback.history(self.identity, self.case_id)["notice"],
        )

    def test_correction_keeps_original_and_concurrent_attempt_loses_safely(self):
        original = self.feedback.append(self.identity, self.case_id, self.body())
        effective = self.feedback.history(self.identity, self.case_id)[
            "effective_records"
        ][0]
        body = self.body(
            receipt=effective["correction_receipt"],
            predecessor=original["record_id"],
            expected_version=1,
            correction_reason="SYNTHETIC transcription correction",
            judgment="NOT_USEFUL",
        )
        other = {**body, "idempotency_key": str(uuid4()), "judgment": "UNCERTAIN"}

        def submit(value):
            try:
                return self.feedback.append(self.identity, self.case_id, value)
            except InvestigatorAppError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (body, other)))
        self.assertEqual(sum(x is not None for x in results), 1)
        history = self.feedback.history(self.identity, self.case_id)
        self.assertEqual(len(history["annotations"]), 2)
        self.assertEqual(history["effective_records"][0]["version"], 2)
        self.assertEqual(history["annotations"][0]["record_id"], original["record_id"])

    def test_transaction_failure_leaves_no_annotation(self):
        connect = self.feedback.connect

        class RollbackConnection:
            def __init__(self):
                self.conn = connect()

            def transaction(self):
                return self.conn.transaction()

            def execute(self, sql, args=None):
                result = self.conn.execute(sql, args)
                if "append_feedback" in sql:
                    raise RuntimeError("synthetic process failure before commit")
                return result

            def close(self):
                self.conn.close()

        body = self.body()
        with (
            patch.object(self.feedback, "connect", RollbackConnection),
            self.assertRaises(InvestigatorAppError),
        ):
            self.feedback.append(self.identity, self.case_id, body)
        self.assertEqual(
            self.feedback.history(self.identity, self.case_id)["annotations"], []
        )
        self.feedback.append(self.identity, self.case_id, body)

    def test_historical_report_survives_evidence_revocation_not_access_revocation(self):
        body = self.body()
        record, revision = self.base.admin.execute(
            "SELECT canonical_record,authority_revision FROM evidence_authority.investigator_evidence_projection_change WHERE tenant_id=%s AND case_id=%s ORDER BY authority_revision DESC LIMIT 1",
            (self.identity.tenant_id, self.case_id),
        ).fetchone()
        record["usability"], record["unusable_reason"] = "UNUSABLE", "EVIDENCE_REVOKED"
        with self.base._connect(self.base.authority_role)() as conn, conn.transaction():
            self.case.operator._authority_context(conn, self.identity.tenant_id)
            conn.execute(
                "SELECT evidence_authority.commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(record), revision, "EVIDENCE_REVOKED"),
            )
        with self.assertRaises(InvestigatorAppError):
            self.feedback.report(self.identity, self.case_id)
        self.feedback.append(self.identity, self.case_id, body)
        self.base.admin.execute(
            pg.sql.SQL("REVOKE olin_investigator_feedback FROM {}").format(
                pg.sql.Identifier(self.roles[0])
            )
        )
        try:
            with self.assertRaises(InvestigatorAppError):
                self.feedback.history(self.identity, self.case_id)
        finally:
            self.base.admin.execute(
                pg.sql.SQL("GRANT olin_investigator_feedback TO {}").format(
                    pg.sql.Identifier(self.roles[0])
                )
            )

    def test_cohort_preserves_missing_negative_stopped_and_versions(self):
        cases = [self.case_id]
        for _ in range(2):
            case = self.base()
            case.setUp()
            cases.append(case.case_id)
        frozen = self.freeze(cases)
        self.feedback.append(
            self.identity, self.case_id, self.body(judgment="NOT_USEFUL")
        )
        response = self.feedback.cohorts(self.identity)
        cohort = next(
            c for c in response["cohorts"] if c["cohort_id"] == frozen["cohort_id"]
        )
        self.assertEqual(cohort["declared_denominator"], 3)
        self.assertEqual(cohort["counts"]["FEEDBACK"]["NOT_YET_OBSERVED"], 2)
        self.assertEqual(cohort["counts"]["EXTERNAL_OUTCOME"]["NOT_YET_OBSERVED"], 3)
        with self.assertRaises(pg.psycopg.Error):
            self.freeze(cases[:1], frozen["cohort_id"], 1)
        self.freeze(cases, frozen["cohort_id"], 1)
        history = self.feedback.cohorts(self.identity)["membership_history"]
        self.assertEqual(sum(c["cohort_id"] == frozen["cohort_id"] for c in history), 2)

    def test_writer_cannot_update_history_freeze_or_mutate_evidence(self):
        with self.base._connect(self.roles[0])() as conn:
            for sql in (
                "UPDATE investigator.feedback_annotation SET version=9",
                "DELETE FROM investigator.feedback_annotation",
                "SELECT investigator.freeze_cohort(NULL,NULL,0,'{}','bad')",
                "SELECT * FROM evidence_authority.investigator_evidence_projection_change",
                "SELECT * FROM investigator.shadow_event",
            ):
                with (
                    self.subTest(sql=sql),
                    self.assertRaises(pg.psycopg.Error),
                    conn.transaction(),
                ):
                    conn.execute("SET LOCAL ROLE olin_investigator_feedback")
                    conn.execute(sql)

    def test_all_missing_statuses_remain_distinct(self):
        for status in (
            "PENDING",
            "UNKNOWN",
            "UNAVAILABLE",
            "NOT_APPLICABLE",
            "WINDOW_INCOMPLETE",
        ):
            record = self.feedback.append(
                self.identity,
                self.case_id,
                self.body(observation_status=status, judgment=None),
            )
            self.assertEqual(record["payload"]["observation_status"], status)
            self.assertIsNone(record["payload"]["judgment"])
