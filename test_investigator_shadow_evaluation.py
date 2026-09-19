"""Evaluation plumbing; all provider responses are fake/mocked, never real inference."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import test_investigator_postgres_workflow as pg
from olin.investigator_shadow import fake_proposal
from scripts import evaluate_investigator_shadow as ev
from test_investigator_phase5b_shadow import context


class EvaluationUnitTests(unittest.TestCase):
    def test_interrupted_publication_never_exposes_partial_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            with (
                patch.object(ev.os, "link", side_effect=RuntimeError("interrupted")),
                self.assertRaises(RuntimeError),
            ):
                ev.save_once(path, {"state": "FINISHED"})
            self.assertFalse(path.exists())
            ev.save_once(path, {"state": "AMBIGUOUS"})
            self.assertEqual(ev.load_private(path), {"state": "AMBIGUOUS"})

    def test_dry_run_disallows_real_configuration(self):
        self.assertEqual(ev.configuration("dry-run", None), {"mode": "fake"})
        with self.assertRaises(ValueError):
            ev.configuration("dry-run", {"mode": "ollama"})

    def test_real_refuses_missing_approval_and_limits(self):
        for config in (None, {}, {"mode": "fake"}, {"mode": "ollama"}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                ev.configuration("real", config)

    def test_fake_worker_never_opens_provider_transport(self):
        with patch(
            "olin.investigator_shadow_runner.http.client.HTTPConnection",
            side_effect=AssertionError("no network"),
        ):
            result = ev.worker({"config": {"mode": "fake"}, "context": context()})
        self.assertEqual(result["provider"], "fake")
        self.assertEqual(result["status"], "VALID")
        self.assertTrue(result["raw_response_base64"])

    def test_isolated_process_receives_no_custody_or_rubrics(self):
        with patch.object(
            ev.subprocess,
            "run",
            return_value=MagicMock(returncode=0, stdout='{"status":"REFUSAL"}'),
        ) as run:
            self.assertEqual(
                ev.isolated_attempt({"mode": "fake"}, context())["status"], "REFUSAL"
            )
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(set(payload), {"config", "context"})
        self.assertEqual(
            set(run.call_args.kwargs["env"]),
            {"PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE"},
        )
        for forbidden in (
            "expected",
            "forbidden",
            "split",
            "human_action",
            "rationale",
        ):
            self.assertNotIn(forbidden, payload["context"])

    def test_process_timeout_is_ambiguous_without_fallback_or_retry(self):
        with patch.object(
            ev.subprocess, "run", side_effect=ev.subprocess.TimeoutExpired("worker", 35)
        ) as run:
            result = ev.isolated_attempt({"mode": "fake"}, context())
        self.assertEqual(result["status"], "TIMEOUT_AMBIGUOUS")
        self.assertEqual(run.call_count, 1)

    def test_private_artifacts_no_overwrite_or_public_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = ev.private_directory(directory) / "record.json"
            ev.save_once(path, {"state": "STARTED"})
            with self.assertRaises(FileExistsError):
                ev.save_once(path, {"state": "FINISHED"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            Path(directory).chmod(0o755)
            with self.assertRaises(ValueError):
                ev.private_directory(directory)

    def test_versions_and_split_are_frozen(self):
        dataset = ev.frozen_dataset()
        self.assertEqual(len(dataset["cases"]), 10)
        self.assertEqual(sum(c["split"] == "held-out" for c in dataset["cases"]), 3)
        with patch.object(ev, "PROMPT", "changed"), self.assertRaises(ValueError):
            ev.frozen_dataset()

    def test_invalid_raw_real_response_preserved_without_inference(self):
        config = {
            "mode": "ollama",
            "model": "test-only-model",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "synthetic_only": True,
            "approval_reference": "mock-only-no-inference",
            "max_requests": 1,
            "max_input_tokens": 16384,
            "max_output_tokens": 1024,
            "timeout_seconds": 30,
        }
        ev.configuration("real", config)
        response = MagicMock(status=200)
        response.read.return_value = b"not valid JSON"
        with patch(
            "olin.investigator_shadow_runner.http.client.HTTPConnection"
        ) as connection:
            connection.return_value.getresponse.return_value = response
            result = ev.worker({"config": config, "context": context()})
        self.assertEqual(result["status"], "INVALID_OUTPUT")
        self.assertEqual(
            ev.base64.b64decode(result["raw_response_base64"][0]), b"not valid JSON"
        )
        self.assertEqual(connection.call_count, 1)


@unittest.skipUnless(pg.POSTGRES_AVAILABLE, "explicit disposable PostgreSQL required")
class EvaluationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = pg.InvestigatorPostgresWorkflowTests
        cls.base.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.base.tearDownClass()

    def setUp(self):
        self.fixture = self.base(
            "test_a_complete_useful_human_journey_recomputes_current_analysis"
        )
        self.fixture.setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.manifest = ev.prepare(
            self.fixture.operator,
            self.fixture.service,
            self.fixture.identity,
            uuid4(),
            self.path,
        )

    def evaluate(self, **kwargs):
        return ev.evaluate(
            self.fixture.service,
            self.fixture.identity,
            self.path,
            mode="dry-run",
            **kwargs,
        )

    def test_authorized_dry_run_actual_three_case_coverage(self):
        report = self.evaluate()
        self.assertEqual(report["attempted_cases"], 3)
        self.assertEqual(report["real_inference"], "NOT_EXECUTED")
        eligible = [r for r in report["results"] if r["attempted"]]
        self.assertEqual(
            [r["rubric_id"] for r in eligible],
            ["coverage-unknown", "account-complete", "cost-debt-unknown"],
        )
        self.assertTrue(all(r["provider"] == "fake" for r in eligible))
        self.assertTrue(
            all(r["human_review"] == "NOT_REVIEWED" for r in report["results"])
        )
        self.assertTrue(
            all(r["investigation_outcome"] == "UNKNOWN" for r in report["results"])
        )
        for row in self.manifest["cases"]:
            self.assertIn("authority_digest", row["binding"])
            self.assertNotIn("expected", row["context"])
            self.assertNotIn("split", row["context"])
            self.assertNotIn("untrusted_test_text", str(row["context"]))
        self.assertTrue((self.path / "summary.md").exists())

    def test_missing_summary_recovers_without_repeating_any_attempt(self):
        write = ev.write_once

        def fail_summary(path, text):
            if path.name == "summary.json":
                raise RuntimeError("interruption after report")
            return write(path, text)

        attempt = MagicMock(return_value={"status": "REFUSAL", "proposal": None})
        with (
            patch.object(ev, "write_once", side_effect=fail_summary),
            self.assertRaises(RuntimeError),
        ):
            self.evaluate(attempt=attempt)
        self.assertTrue((self.path / "report.json").exists())
        self.assertFalse((self.path / "summary.json").exists())
        self.evaluate(attempt=attempt)
        self.assertEqual(attempt.call_count, 3)
        self.assertTrue((self.path / "summary.json").exists())
        self.assertTrue((self.path / "summary.md").exists())

    def test_failures_remain_in_denominator_and_replay_never_reinvokes(self):
        statuses = iter(("INVALID_OUTPUT", "TIMEOUT_AMBIGUOUS", "REFUSAL"))
        attempt = MagicMock(
            side_effect=lambda *_: {"status": next(statuses), "proposal": None}
        )
        result = self.evaluate(attempt=attempt)
        self.assertEqual(
            {r["status"] for r in result["results"] if r["attempted"]},
            {"INVALID_OUTPUT", "TIMEOUT_AMBIGUOUS", "REFUSAL"},
        )
        self.evaluate(attempt=attempt)
        self.assertEqual(attempt.call_count, 3)

    def test_interrupted_started_record_recovers_without_reinference(self):
        class Interruption(BaseException):
            pass

        with self.assertRaises(Interruption):
            self.evaluate(attempt=MagicMock(side_effect=Interruption))
        attempt = MagicMock(return_value={"status": "REFUSAL", "proposal": None})
        result = self.evaluate(attempt=attempt)
        self.assertEqual(result["results"][0]["status"], "AMBIGUOUS")
        self.assertEqual(attempt.call_count, 2)
        self.evaluate(attempt=attempt)
        self.assertEqual(attempt.call_count, 2)

    def test_request_budget_stops_before_extra_attempt(self):
        with patch.object(
            ev, "configuration", return_value={"mode": "fake", "max_requests": 1}
        ):
            result = self.evaluate()
        self.assertEqual(result["attempted_cases"], 1)
        self.assertEqual(
            sum(
                r["pipeline_status"] == "REQUEST_LIMIT_REACHED"
                for r in result["results"]
            ),
            2,
        )

    def test_revoked_context_never_calls_worker_for_that_case(self):
        case_id = UUID(self.manifest["cases"][0]["case_id"])
        record, revision = self.base.admin.execute(
            "SELECT canonical_record,authority_revision FROM evidence_authority.investigator_evidence_projection_change "
            "WHERE tenant_id=%s AND case_id=%s ORDER BY authority_revision DESC LIMIT 1",
            (self.fixture.identity.tenant_id, case_id),
        ).fetchone()
        record["usability"], record["unusable_reason"] = "UNUSABLE", "EVIDENCE_REVOKED"
        with self.base._connect(self.base.authority_role)() as authority:
            self.fixture.operator._authority_context(
                authority, self.fixture.identity.tenant_id
            )
            authority.execute(
                "SELECT evidence_authority.commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                (json.dumps(record), revision, "EVIDENCE_REVOKED"),
            )
        attempt = MagicMock(return_value={"status": "REFUSAL", "proposal": None})
        result = self.evaluate(attempt=attempt)
        self.assertFalse(result["results"][0]["attempted"])
        self.assertEqual(
            result["results"][0]["pipeline_status"], "AUTHORIZATION_REJECTED"
        )
        self.assertEqual(attempt.call_count, 2)

    def test_payload_has_no_rubrics_and_cannot_mutate_evidence(self):
        before = self.base.admin.execute(
            "SELECT count(*) FROM investigator.investigation_evidence_reference"
        ).fetchone()[0]

        def attempt(config, supplied):
            for word in (
                "expected",
                "forbidden",
                "split",
                "human_selection",
                "analyst_rationale",
            ):
                self.assertNotIn(word, supplied)
            output = fake_proposal(supplied)
            output["verified"] = True
            return {"status": "VALID", "proposal": output}

        report = self.evaluate(attempt=attempt)
        self.assertTrue(
            all(
                r["status"] == "INVALID_OUTPUT"
                for r in report["results"]
                if r["attempted"]
            )
        )
        after = self.base.admin.execute(
            "SELECT count(*) FROM investigator.investigation_evidence_reference"
        ).fetchone()[0]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
