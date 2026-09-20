"""Real PostgreSQL research-role, disclosure, replay and currentness proofs."""

from __future__ import annotations

import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import test_investigator_postgres_workflow as pg
from olin.investigator_app import AnalystIdentity, InvestigatorAppError
from olin.investigator_shadow_runner import Runner
from olin.investigator_shadow_service import ShadowResearchService
from test_investigator_shadow_applicability import saved_cases


@unittest.skipUnless(pg.POSTGRES_AVAILABLE, "explicitly disposable PostgreSQL required")
class InvestigatorPostgresShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = pg.InvestigatorPostgresWorkflowTests
        cls.base.setUpClass()
        cls.role = "olin_research_t_" + cls.base.tenant.hex
        password = pg.secrets.token_urlsafe(24)
        cls.base.admin.execute(
            Path("db/migrations/0007_investigator_shadow_research.sql").read_text()
        )
        cls.base.admin.execute(
            pg.sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOINHERIT NOSUPERUSER NOBYPASSRLS"
            ).format(pg.sql.Identifier(cls.role), pg.sql.Literal(password))
        )
        cls.base.admin.execute(
            pg.sql.SQL("GRANT olin_investigator_research TO {}").format(
                pg.sql.Identifier(cls.role)
            )
        )
        cls.base.passwords[cls.role] = password

    @classmethod
    def tearDownClass(cls):
        cls.base.admin.execute(
            pg.sql.SQL("DROP ROLE {}").format(pg.sql.Identifier(cls.role))
        )
        cls.base.admin.execute("DROP OWNED BY olin_investigator_research")
        cls.base.admin.execute("DROP ROLE olin_investigator_research")
        cls.base.tearDownClass()

    def setUp(self):
        self.case = self.base(
            "test_a_complete_useful_human_journey_recomputes_current_analysis"
        )
        self.case.setUp()
        self.runner = Runner({"mode": "fake"})
        self.shadow = ShadowResearchService(
            self.case.service,
            self.base._connect(self.role),
            self.runner,
            synthetic_cases=[self.case.case_id],
        )
        self.identity = self.case.identity
        self.case_id = self.case.case_id

    def create(self):
        return UUID(
            self.shadow.create(self.identity, self.case_id, "first")["round_id"]
        )

    def select(self):
        return self.case._select_and_request(str(self.case_id))

    def test_a_blinded_round_then_disclosure_preserves_human_baseline(self):
        r = self.create()
        with self.assertRaises(InvestigatorAppError):
            self.shadow.disclose(self.identity, self.case_id, r)
        action = self.select()
        generated = self.shadow.generate(self.identity, self.case_id, r)
        self.assertNotIn("proposal", str(generated))
        revealed = self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(revealed["result"]["provider"], "fake")
        self.assertEqual(revealed["human_action_id"], action["action"]["action_id"])
        self.assertTrue(revealed["agreement"])
        self.assertEqual(
            revealed["action_applicability"]["proposals"][0]["status"], "APPLICABLE"
        )
        self.assertEqual(
            revealed["action_applicability"]["proposals"][0]["narrative_semantics"],
            "REQUIRES_SEMANTIC_REVIEW",
        )
        self.assertEqual(revealed["unperformed_proposal_outcomes"], "UNKNOWN")
        replay = self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(replay["first_disclosed_at"], revealed["first_disclosed_at"])
        self.shadow.rate(
            self.identity,
            self.case_id,
            r,
            "UNCERTAIN",
            "Fake output is not intelligence",
            "rating",
        )

    def test_complete_account_proposal_is_not_applicable_or_agreement(self):
        current = self.case.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]
        self.case.operator.useful_coverage(
            tenant_id=self.identity.tenant_id,
            case_id=self.case_id,
            action_id=uuid4(),
            expected_revision=current["input_assessment"]["authority_revision"],
        )
        r = self.create()
        record = self.shadow._call(self.identity, self.case_id, r)
        e = record["context"]["action_eligibility"]
        self.assertNotIn("REQUEST_ACCOUNT_CHANNEL_RECORD", e["capabilities"])
        self.assertNotIn("REQUEST_ACCOUNT_CHANNEL_RECORD", record["context"]["actions"])
        with self.assertRaises(InvestigatorAppError):
            self.shadow.disclose(self.identity, self.case_id, r)
        self.select()
        actions_before = self.case.service.list_actions(self.identity, self.case_id)
        binding_before = self.case.service.current_analysis(
            self.identity, self.case_id
        )["reconstruction"]["input_assessment"]
        # Mocked structural success cannot masquerade as applicable guidance.
        output = json.loads(json.dumps(saved_cases()[1]["proposal"]))
        for proposal in output["proposals"]:
            proposal["references"] = record["context"]["references"]
        with patch.object(
            self.runner,
            "generate",
            return_value={
                "proposal": output,
                "provider": "fake",
                "model": self.runner.model,
            },
        ):
            self.shadow.generate(self.identity, self.case_id, r)
        shown = self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(shown["result"]["status"], "VALID")
        self.assertEqual(shown["result"]["proposal"], output)
        self.assertEqual(
            [p["status"] for p in shown["action_applicability"]["proposals"]],
            ["NOT_APPLICABLE", "APPLICABLE"],
        )
        self.assertFalse(shown["agreement"])
        self.assertEqual(shown["comparison_rule"], "APPLICABLE_ACTION_TYPE_OVERLAP_V2")
        self.assertEqual(
            self.case.service.list_actions(self.identity, self.case_id), actions_before
        )
        binding_after = self.case.service.current_analysis(self.identity, self.case_id)[
            "reconstruction"
        ]["input_assessment"]
        self.assertEqual(
            {k: v for k, v in binding_before.items() if k != "checked_at"},
            {k: v for k, v in binding_after.items() if k != "checked_at"},
        )

    def test_b_context_contains_neither_human_choice_nor_future_evidence(self):
        r = self.create()
        original = self.shadow._call(self.identity, self.case_id, r)
        self.select()
        with patch.object(
            self.runner, "generate", wraps=self.runner.generate
        ) as generate:
            self.shadow.generate(self.identity, self.case_id, r)
        sent = generate.call_args.args[0]
        self.assertEqual(sent, original["context"])
        text = str(sent)
        for secret in (
            str(self.identity.tenant_id),
            str(self.case_id),
            self.identity.name,
            "analyst_rationale",
            "selected_at",
            "action_id",
            "DATABASE",
            "expected",
        ):
            self.assertNotIn(secret, text)

    def test_c_cross_tenant_and_forged_round_fail_closed(self):
        r = self.create()
        other = AnalystIdentity(self.identity.name, uuid4(), "analyst")
        with self.assertRaises(pg.psycopg.errors.InsufficientPrivilege):
            self.shadow._call(other, self.case_id, r)
        with self.assertRaises(InvestigatorAppError):
            self.shadow.disclose(self.identity, self.case_id, uuid4())

    def test_d_changed_evidence_excludes_round_not_human_workflow(self):
        r = self.create()
        selected = self.select()
        self.shadow.generate(self.identity, self.case_id, r)
        self.case.service.synthetic_response(
            self.identity,
            self.case_id,
            UUID(selected["action"]["action_id"]),
            fixture="useful_coverage",
        )
        with self.assertRaises(InvestigatorAppError):
            self.shadow.disclose(self.identity, self.case_id, r)
        record = self.shadow._call(self.identity, self.case_id, r)
        self.assertIsNotNone(self.shadow._event(record, "EXCLUDED"))
        self.assertIsNone(self.shadow._event(record, "DISCLOSED"))
        self.case.service.current_analysis(self.identity, self.case_id)

    def test_e_duplicate_generation_and_disclosure_do_not_repeat_inference(self):
        r = self.create()
        self.assertEqual(r, self.create())
        self.select()
        for _ in range(3):
            self.shadow.generate(self.identity, self.case_id, r)
            self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(self.runner.used, 1)
        record = self.shadow._call(self.identity, self.case_id, r)
        for kind in ("STARTED", "FINISHED", "DISCLOSED", "HUMAN_SELECTED"):
            self.assertEqual(sum(e["kind"] == kind for e in record["events"]), 1)

    def test_f_timeout_records_denominator_and_human_remains_usable(self):
        r = self.create()
        self.select()
        with patch.object(self.runner, "generate", side_effect=TimeoutError):
            self.shadow.generate(self.identity, self.case_id, r)
        revealed = self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(revealed["result"]["status"], "TIMEOUT")
        self.assertIsNone(revealed["agreement"])
        self.case.service.current_analysis(self.identity, self.case_id)

    def test_g_completed_write_is_recoverable_after_lost_http_response(self):
        r = self.create()
        self.select()
        call = self.shadow._call

        def fail_after_commit(*args, **kwargs):
            result = call(*args, **kwargs)
            if len(args) > 3 and args[3] == "FINISHED":
                raise RuntimeError("lost response after commit")
            return result

        with (
            patch.object(self.shadow, "_call", side_effect=fail_after_commit),
            self.assertRaises(RuntimeError),
        ):
            self.shadow.generate(self.identity, self.case_id, r)
        self.shadow.generate(self.identity, self.case_id, r)
        self.assertEqual(self.runner.used, 1)
        self.assertEqual(
            self.shadow.disclose(self.identity, self.case_id, r)["result"]["status"],
            "VALID",
        )

    def test_h_research_role_cannot_mutate_evidence_actions_or_history(self):
        r = self.create()
        for query in (
            "UPDATE investigator.shadow_round SET analyst='forged'",
            "DELETE FROM investigator.shadow_event",
            "SELECT * FROM investigator.investigation_action",
            "SELECT * FROM evidence_authority.investigator_evidence_projection_change",
        ):
            with (
                self.assertRaises(pg.psycopg.errors.InsufficientPrivilege),
                self.base._connect(self.role)() as conn,
            ):
                conn.execute("SET LOCAL ROLE olin_investigator_research")
                conn.execute(query)
        self.assertIsNotNone(self.shadow._call(self.identity, self.case_id, r))

    def test_i_model_wait_holds_no_database_transaction(self):
        r = self.create()
        self.select()
        generate = self.runner.generate

        def inspect(context):
            active = self.base.admin.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE usename IN (%s,%s,%s,%s) AND xact_start IS NOT NULL",
                (
                    self.role,
                    self.base.runtime_role,
                    self.base.reader_role,
                    self.base.action_role,
                ),
            ).fetchone()[0]
            self.assertEqual(active, 0)
            return generate(context)

        with patch.object(self.runner, "generate", side_effect=inspect):
            self.shadow.generate(self.identity, self.case_id, r)

    def test_j_revocation_before_attempt_excludes_round(self):
        r = self.create()
        self.select()
        record, revision = self.base.admin.execute(
            "SELECT canonical_record,authority_revision FROM evidence_authority.investigator_evidence_projection_change "
            "WHERE tenant_id=%s AND case_id=%s ORDER BY authority_revision DESC LIMIT 1",
            (self.identity.tenant_id, self.case_id),
        ).fetchone()
        record["usability"], record["unusable_reason"] = "UNUSABLE", "EVIDENCE_REVOKED"
        with self.base._connect(self.base.authority_role)() as authority:
            self.case.operator._authority_context(authority, self.identity.tenant_id)
            authority.execute(
                "SELECT evidence_authority.commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(record), revision, "EVIDENCE_REVOKED"),
            )
        with self.assertRaises(InvestigatorAppError):
            self.shadow.generate(self.identity, self.case_id, r)
        self.assertEqual(self.runner.used, 0)
        self.assertIsNotNone(
            self.shadow._event(
                self.shadow._call(self.identity, self.case_id, r), "EXCLUDED"
            )
        )

    def test_k_direct_disclosure_requires_durable_human_and_completion(self):
        r = self.create()
        with self.assertRaises(pg.psycopg.errors.RaiseException):
            self.shadow._call(self.identity, self.case_id, r, "DISCLOSED", {}, "forged")
        self.assertIsNone(
            self.shadow._event(
                self.shadow._call(self.identity, self.case_id, r), "DISCLOSED"
            )
        )

    def test_l_concurrent_attempts_invoke_at_most_once(self):
        r = self.create()
        self.select()

        def generate(_):
            try:
                return self.shadow.generate(self.identity, self.case_id, r)
            except (
                pg.psycopg.errors.RaiseException,
                pg.psycopg.errors.UniqueViolation,
            ):
                return {"status": "SAFE_CONFLICT"}

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(generate, range(2)))
        self.assertEqual(self.runner.used, 1)
        events = self.shadow._call(self.identity, self.case_id, r)["events"]
        self.assertEqual(sum(e["kind"] == "STARTED" for e in events), 1)
        self.assertEqual(sum(e["kind"] == "FINISHED" for e in events), 1)

    def test_m_refusal_and_invalid_output_are_not_dropped(self):
        r = self.create()
        self.select()
        with patch.object(self.runner, "generate", return_value={"failure": "REFUSAL"}):
            self.shadow.generate(self.identity, self.case_id, r)
        result = self.shadow.disclose(self.identity, self.case_id, r)
        self.assertEqual(result["result"]["status"], "REFUSAL")
        self.assertIsNone(result["agreement"])

    def test_n_history_links_only_performed_action_and_never_discloses_proposals(self):
        r = self.create()
        selected = self.select()
        self.shadow.generate(self.identity, self.case_id, r)
        self.shadow.disclose(self.identity, self.case_id, r)
        self.case.service.synthetic_response(
            self.identity,
            self.case_id,
            UUID(selected["action"]["action_id"]),
            fixture="useful_coverage",
        )
        history = self.shadow.history(self.identity, self.case_id, r)
        self.assertEqual(
            history["current_coverage_supported_by_performed_action"],
            ["BANK_ACCOUNT_COVERAGE"],
        )
        self.assertNotIn("proposal", history)
        self.assertEqual(history["unperformed_proposal_outcomes"], "UNKNOWN")

    def test_o_interrupted_started_attempt_expires_without_reinference(self):
        r = self.create()
        self.select()
        with (
            patch.object(
                self.runner,
                "generate",
                side_effect=RuntimeError("process interruption"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.shadow.generate(self.identity, self.case_id, r)
        self.assertEqual(
            self.shadow.generate(self.identity, self.case_id, r)["status"], "PROCESSING"
        )
        # Real server-clock expiry, not a forged timestamp or mutable ledger.
        time.sleep(35)
        time.sleep(31)
        result = self.shadow.generate(self.identity, self.case_id, r)
        self.assertEqual(result["status"], "AMBIGUOUS")
        for _ in range(2):
            self.shadow.generate(self.identity, self.case_id, r)
        record = self.shadow._call(self.identity, self.case_id, r)
        self.assertEqual(sum(e["kind"] == "STARTED" for e in record["events"]), 1)
        self.assertEqual(sum(e["kind"] == "FINISHED" for e in record["events"]), 1)
        self.assertEqual(self.runner.used, 0)
        self.assertEqual(
            self.shadow.disclose(self.identity, self.case_id, r)["result"]["status"],
            "AMBIGUOUS",
        )


if __name__ == "__main__":
    unittest.main()
