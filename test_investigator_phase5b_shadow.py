"""Deterministic engineering tests, NOT real-model evaluation."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from olin.investigator_shadow import (
    ACTIONS,
    PROMPT,
    PROMPT_VERSION,
    TEXT_FIELDS,
    VERSION,
    canonical,
    digest,
    fake_proposal,
    validate_output,
)
from olin.investigator_shadow_runner import Runner
from olin.investigator_shadow_service import ShadowTransport


def context():
    return {
        "schema_version": "shadow-context-1",
        "synthetic_only": True,
        "uncertainties": ["BANK_ACCOUNT_COVERAGE"],
        "references": ["ref-1"],
        "actions": list(ACTIONS),
        "facts": [],
    }


class ShadowSchemaTests(unittest.TestCase):
    def test_citation_contract_keeps_aliases_structured_not_narrative(self):
        # Synthetic engineering fixture, not a repaired or newly generated response.
        value = fake_proposal(context())
        value["proposals"][0]["references"] = ["ref-1"]
        value["proposals"][0]["rationale"] = (
            "The cited observation leaves account coverage unknown; an account record "
            "could clarify its scope without establishing total revenue."
        )
        self.assertEqual(validate_output(value, context()), value)
        self.assertEqual(PROMPT_VERSION, "shadow-prompt-2")
        for instruction in (
            "ONLY in the dedicated references array",
            "no digits",
            "Do not spell out invented",
            "not proof of factual correctness",
        ):
            self.assertIn(instruction, PROMPT)
        for field in (*TEXT_FIELDS, "abstention_reason"):
            for text in (
                "See ref-1 for the observation.",
                "Revenue is 999.",
                "x" * 501,
                "Approve the loan.",
                "Run `curl`.",
            ):
                with self.subTest(field=field, text=text):
                    bad = copy.deepcopy(value)
                    if field == "abstention_reason":
                        bad["proposals"] = []
                        bad[field] = text
                    else:
                        bad["proposals"][0][field] = text
                    with self.assertRaises(ValueError):
                        validate_output(bad, context())
        value["proposals"][0]["references"] = ["ref-999"]
        with self.assertRaisesRegex(ValueError, "fabricated"):
            validate_output(value, context())

    def test_original_text_bounds_for_every_field_and_abstention(self):
        samples = [
            ("a" * 499, True),
            ("a" * 500, True),
            ("a" * 501, False),
            (" " + "a" * 499 + " ", False),
            ("Which accounts are represented?" + " " * 600, False),
            ("", False),
            (" \t\n", False),
            ("\t\nMeaningful question\t\n", True),
            (None, False),
            (42, False),
            ([], False),
            ({}, False),
            ("é" * 500, True),
            ("é" * 501, False),
            ("🌿" * 500, True),
            ("🌿" * 501, False),
        ]
        for field in (*TEXT_FIELDS, "abstention_reason"):
            for text, valid in samples:
                with self.subTest(
                    field=field,
                    text_type=type(text).__name__,
                    length=len(text) if isinstance(text, str) else None,
                ):
                    value = fake_proposal(context())
                    if field == "abstention_reason":
                        value["proposals"] = []
                        value[field] = text
                    else:
                        value["proposals"][0][field] = text
                    if valid:
                        self.assertEqual(validate_output(value, context()), value)
                    else:
                        with self.assertRaises(ValueError):
                            validate_output(value, context())

    def test_coordinator_rejects_oversized_runner_proposal(self):
        from olin.investigator_shadow_service import ShadowResearchService

        for field in TEXT_FIELDS:
            with self.subTest(field=field):
                runner = Runner({"mode": "fake"})
                output = runner.generate(context())
                output["proposal"]["proposals"][0][field] = "Question" + " " * 600
                service = ShadowResearchService(None, None, runner, synthetic_cases=[])
                record = {"context": context(), "events": []}
                with (
                    patch.object(service, "_call", return_value=record) as call,
                    patch.object(service, "_fresh"),
                    patch.object(service, "_bind_human", return_value=record),
                    patch.object(runner, "generate", return_value=output),
                ):
                    service.generate(None, None, None)
                final = call.call_args.args[4]
                self.assertEqual(final, {"status": "INVALID_OUTPUT", "proposal": None})

    def test_http_rejects_forged_context_actor_and_unauthenticated_research(self):
        import test_investigator_phase5a_workflow as app_tests
        from olin.investigator_app import build_handler

        probe = app_tests.Phase5AWorkflowTests()
        probe.setUp()
        workflow = app_tests.FakeService()
        shadow = MagicMock()
        handler = lambda auth, service: build_handler(auth, service, shadow)
        with patch.object(app_tests, "build_handler", side_effect=handler):
            status, _, _ = probe._request(
                workflow,
                "POST",
                f"/api/cases/{app_tests.CASE}/shadow",
                body={"idempotency_key": "test"},
            )
            self.assertEqual(status, 401)
            token = probe.auth.issue("ana", "test-only-analyst-token")
            for forged in (
                {"tenant_id": "other"},
                {"context": context()},
                {"actor": "admin"},
            ):
                status, _, _ = probe._request(
                    workflow,
                    "POST",
                    f"/api/cases/{app_tests.CASE}/shadow",
                    body={"idempotency_key": "test", **forged},
                    token=token,
                )
                self.assertEqual(status, 400)
        shadow.create.assert_not_called()

    def test_ui_renders_model_text_without_html_and_clears_on_refresh(self):
        from olin.investigator_app import _WORKSPACE_HTML

        self.assertIn(
            "shadowPanel.textContent=JSON.stringify(r,null,2)", _WORKSPACE_HTML
        )
        self.assertNotIn("shadowPanel.innerHTML", _WORKSPACE_HTML)
        self.assertIn("Research display cleared", _WORKSPACE_HTML)

    def test_projection_retains_real_normalization_scope_and_limitations(self):
        from olin.investigator_shadow import project
        from test_investigator_phase4_reconstruction import NOW, fact, reconstruct

        record = reconstruct(
            (
                fact(
                    reference_id=999,
                    proposition_type="daily_operating_costs",
                    proposition_value="1000",
                    period_start=NOW - timedelta(days=1),
                ),
            )
        ).canonical_record()
        projected, _ = project(record)
        original = next(
            x
            for x in record["derived_values"]
            if x["quantity"] == "normalized_monthly_operating_costs"
        )
        model_value = next(
            x
            for x in projected["facts"]
            if x.get("quantity") == "normalized_monthly_operating_costs"
        )
        for field in ("dimensional_scope", "assumptions", "formula", "rule_version"):
            self.assertEqual(model_value[field], original[field])
        self.assertTrue(model_value["assumptions"])

    def test_fake_is_explicit_and_deterministic(self):
        runner = Runner({"mode": "fake"})
        a = runner.generate(context())
        b = runner.generate(context())
        self.assertEqual(a["model"], "deterministic-fake-1")
        self.assertEqual(a["provider"], "fake")
        self.assertEqual(canonical(a["proposal"]), canonical(b["proposal"]))
        self.assertIsNone(a["usage"])
        self.assertIsNone(a["cost"])

    def test_closed_schema_rejects_extra_authority_fields(self):
        for key in ("verified", "independent", "score", "tenant_id", "tools"):
            value = fake_proposal(context())
            value[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_output(value, context())

    def test_fabricated_references_rejected(self):
        value = fake_proposal(context())
        value["proposals"][0]["references"] = ["other-tenant-ref"]
        with self.assertRaises(ValueError):
            validate_output(value, context())

    def test_unauthorized_actions_and_uncertainties_rejected(self):
        for field in ("action_type", "uncertainty"):
            value = fake_proposal(context())
            value["proposals"][0][field] = "EXECUTE_PROVIDER"
            with self.assertRaises(ValueError):
                validate_output(value, context())

    def test_malformed_and_oversized_output_rejected(self):
        for value in (
            None,
            [],
            "text",
            {"schema_version": VERSION},
            {
                "schema_version": VERSION,
                "proposals": [],
                "abstention_reason": "x" * 501,
            },
        ):
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                validate_output(value, context())

    def test_zero_is_valid_only_with_abstention(self):
        value = {
            "schema_version": VERSION,
            "proposals": [],
            "abstention_reason": "Insufficient admissible input.",
        }
        self.assertEqual(validate_output(value, context()), value)
        value["abstention_reason"] = None
        with self.assertRaises(ValueError):
            validate_output(value, context())
        for bad in ("approve", "Revenue is 123", "<script>execute()</script>"):
            value["abstention_reason"] = bad
            with self.assertRaises(ValueError):
                validate_output(value, context())

    def test_duplicate_or_padded_proposals_rejected(self):
        value = fake_proposal(context())
        value["proposals"] *= 2
        with self.assertRaises(ValueError):
            validate_output(value, context())
        value["proposals"] *= 2
        with self.assertRaises(ValueError):
            validate_output(value, context())

    def test_executable_numeric_or_authority_output_rejected(self):
        for text in (
            "<script>alert()</script>",
            "curl example",
            "Revenue is 123 MXN",
            "approve",
            "verified=true",
        ):
            value = fake_proposal(context())
            value["proposals"][0]["question"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_output(value, context())

    def test_frozen_evaluation_set_is_not_in_runner_prompt(self):
        cases = json.loads(
            Path("tests/fixtures/shadow_evaluation_v1.json").read_text()
        )["cases"]
        self.assertEqual(len(cases), 10)
        self.assertEqual(sum(c["split"] == "held-out" for c in cases), 3)
        for case in cases:
            # Rubric and split stay with evaluator. Not delivered to runner.
            supplied = context()
            supplied["uncertainties"] = case["uncertainties"]
            supplied["facts"] = [{"untrusted_test_text": case["text"]}]
            result = Runner({"mode": "fake"}).generate(supplied)
            validate_output(result["proposal"], supplied)
            self.assertNotIn("expected", supplied)
            if not case["uncertainties"] or case["id"] == "account-complete":
                self.assertEqual(result["proposal"]["proposals"], [])

    def test_real_adapter_disabled_without_explicit_resource_approval(self):
        for config in ({}, {"mode": "ollama"}, {"mode": "cloud"}):
            with self.assertRaises(ValueError):
                Runner(config)

    def _approved(self):
        return {
            "mode": "ollama",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": "test-model-only",
            "synthetic_only": True,
            "approval_reference": "synthetic-transport-test-not-inference-approval",
            "max_requests": 1,
            "max_input_tokens": 12000,
            "max_output_tokens": 500,
            "timeout_seconds": 2,
        }

    def test_real_transport_contract_without_live_inference(self):
        response = MagicMock(status=200)
        response.read.return_value = canonical(
            {
                "model": "test-model-only",
                "done": True,
                "message": {"content": canonical(fake_proposal(context()))},
                "prompt_eval_count": 100,
                "eval_count": 50,
            }
        ).encode()
        with patch(
            "olin.investigator_shadow_runner.http.client.HTTPConnection"
        ) as connection:
            connection.return_value.getresponse.return_value = response
            runner = Runner(self._approved())
            result = runner.generate(context())
            sent = json.loads(connection.return_value.request.call_args.kwargs["body"])
            self.assertNotIn("tools", sent)
            self.assertFalse(sent["think"])
            self.assertFalse(sent["stream"])
            self.assertEqual(sent["model"], "test-model-only")
            self.assertEqual(result["usage"]["output_tokens"], 50)
            with self.assertRaises(ValueError):
                runner.generate(context())
            self.assertEqual(connection.call_count, 1)

    def test_remote_destinations_and_unbounded_configuration_rejected(self):
        for key, value in (
            ("endpoint", "https://example.com/api/chat"),
            ("max_requests", 0),
            ("synthetic_only", False),
            ("timeout_seconds", 999),
        ):
            config = self._approved()
            config[key] = value
            with self.assertRaises(ValueError):
                Runner(config)
        with self.assertRaises(ValueError):
            ShadowTransport(
                "http://example.com", "test-only-transport-token-long-enough"
            )

    def test_serialization_is_reproducible(self):
        value = fake_proposal(context())
        self.assertEqual(digest(value), digest(copy.deepcopy(value)))

    def test_runner_has_no_database_or_workflow_tools(self):
        import ast

        source = Path("olin/investigator_shadow_runner.py").read_text()
        imports = [
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("investigator_app", imports)
        for forbidden in ("psycopg", "subprocess", "shell=True", "MCP", "load_dotenv"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
