"""Deterministic report contracts; fake HTTP dispatch is not database proof."""

import unittest

import test_investigator_phase5a_workflow as workflow_tests
from olin.investigator_reports import ReportInput, canonical, render_html
from test_investigator_phase5a_workflow import CASE, FakeService


class ReportUnitTests(unittest.TestCase):
    def test_html_escapes_untrusted_text(self):
        text = render_html("Brief", {"rationale": '<script>alert("x")</script>'})
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_frozen_input_cannot_be_mutated_through_decoding(self):
        frozen = ReportInput(canonical({"nested": {"value": "unknown"}}))
        frozen.record["nested"]["value"] = "zero"
        self.assertEqual(frozen.record["nested"]["value"], "unknown")

    def test_http_auth_and_no_caller_bindings(self):
        helper = workflow_tests.Phase5AWorkflowTests()
        helper.setUp()
        service = FakeService()
        service.current_report = lambda identity, case: {
            "manifest": {"case_id": str(case)}
        }
        path = f"/api/cases/{CASE}/report"
        self.assertEqual(helper._request(service, "GET", path)[0], 401)
        token = helper.auth.issue("ana", "test-only-analyst-token")
        status, headers, body = helper._request(service, "GET", path, token=token)
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["cache-control"])
        self.assertEqual(body["manifest"]["case_id"], str(CASE))
        for suffix in (
            "?snapshot_id=forged",
            "?report_input_digest=forged",
            "?tenant=forged",
        ):
            self.assertEqual(
                helper._request(service, "GET", path + suffix, token=token)[0], 400
            )
        self.assertEqual(
            helper._request(service, "POST", path, body={}, token=token)[0], 404
        )
