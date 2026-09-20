"""HTTP/receipt contract tests; these do not substitute for PostgreSQL proof."""

import json
import unittest
from unittest.mock import patch

import test_investigator_phase5a_workflow as workflow_tests
from olin.investigator_app import build_handler
from olin.investigator_feedback import FeedbackService


class FeedbackUnitTests(unittest.TestCase):
    def test_demo_refuses_before_setup_without_disposable_confirmation(self):
        from scripts import run_investigator_feedback_demo as demo

        with (
            patch.object(demo.pg, "DISPOSABLE", False),
            patch.object(demo.pg, "POSTGRES_AVAILABLE", True),
            patch.object(demo.FeedbackPostgresTests, "setUpClass") as setup,
            patch("sys.argv", ["demo"]),
        ):
            with self.assertRaises(RuntimeError):
                demo.main()
            setup.assert_not_called()

    def test_http_requires_auth_and_no_store(self):
        helper = workflow_tests.Phase5AWorkflowTests()
        helper.setUp()

        class FakeFeedback:
            def history(self, identity, case):
                return {"actor": identity.name, "case": str(case)}

            def cohorts(self, identity):
                return {"cohorts": [], "tenant": str(identity.tenant_id)}

        factory = lambda auth, service: build_handler(
            auth, service, feedback=FakeFeedback()
        )
        with patch.object(workflow_tests, "build_handler", factory):
            for path in (f"/api/cases/{workflow_tests.CASE}/feedback", "/api/cohorts"):
                self.assertEqual(
                    helper._request(workflow_tests.FakeService(), "GET", path)[0], 401
                )
                token = helper.auth.issue("ana", "test-only-analyst-token")
                status, headers, _ = helper._request(
                    workflow_tests.FakeService(), "GET", path, token=token
                )
                self.assertEqual(status, 200)
                self.assertIn("no-store", headers["cache-control"])

    def test_effective_history_retains_negative_and_missing(self):
        records = [
            {
                "stream_id": "a",
                "version": 1,
                "record_id": "old",
                "recorded_at": "a",
                "judgment": "USEFUL",
            },
            {
                "stream_id": "a",
                "version": 2,
                "record_id": "new",
                "recorded_at": "b",
                "judgment": "NOT_USEFUL",
            },
            {
                "stream_id": "b",
                "version": 1,
                "record_id": "missing",
                "recorded_at": "c",
                "judgment": None,
            },
        ]
        self.assertEqual(
            [x["judgment"] for x in FeedbackService.effective(records)],
            ["NOT_USEFUL", None],
        )
        self.assertEqual(len(records), 3)

    def test_ui_uses_text_content_not_untrusted_html(self):
        from olin.investigator_app import _WORKSPACE_HTML

        script = _WORKSPACE_HTML.split("async function loadFeedback()", 1)[1].split(
            "function clearReport", 1
        )[0]
        self.assertNotIn("innerHTML", script)
        self.assertIn("p.textContent=JSON.stringify", script)
        self.assertIn("fb('cohortView').textContent", script)

    def test_receipt_is_domain_separated_and_bounded(self):
        from olin.investigator_app import InvestigatorAppError

        service = FeedbackService(
            None, None, b"synthetic-test-secret-not-a-real-secret"
        )
        helper = workflow_tests.Phase5AWorkflowTests()
        helper.setUp()
        identity = helper.auth.authenticate(
            "Bearer " + helper.auth.issue("ana", "test-only-analyst-token")
        )
        for receipt in (
            None,
            "x" * 16001,
            "invalid.bad",
            json.dumps({"report_input_digest": "0" * 64}),
        ):
            with self.assertRaises(InvestigatorAppError):
                service._receipt(identity, workflow_tests.CASE, receipt)
