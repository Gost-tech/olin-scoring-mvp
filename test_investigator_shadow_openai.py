"""Hosted adapter contract: synthetic mocks ONLY; no real credential or network."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from olin.investigator_shadow import OUTPUT_SCHEMA, PROMPT, canonical, fake_proposal
from olin.investigator_shadow_openai import (
    AMENDMENT,
    ENDPOINT,
    MODEL,
    REQUEST_RESERVE_USD,
    read_dedicated_credential,
)
from olin.investigator_shadow_runner import Runner
from scripts import evaluate_investigator_shadow as ev
from test_investigator_phase5b_shadow import context


def configuration():
    return {
        "mode": "openai",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "authority_amendment": AMENDMENT,
        "synthetic_only": True,
        "synthetic_transmission_approved": True,
        "approval_reference": "mock-only-not-execution-approval",
        "transmission_approval_reference": "mock-only-not-transmission-approval",
        "max_requests": 3,
        "max_input_tokens": 16384,
        "max_output_tokens": 1024,
        "timeout_seconds": 30,
        "total_budget_usd": "1.00",
    }


def envelope():
    return {
        "model": MODEL,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": canonical(fake_proposal(context()))}
                ],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


class HostedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.credential = "synthetic-not-a-provider-credential"
        self.transport = self.enterContext(
            patch("olin.investigator_shadow_openai.http.client.HTTPSConnection")
        )
        self.enterContext(
            patch(
                "olin.investigator_shadow_runner.http.client.HTTPConnection",
                side_effect=AssertionError("no fallback transport"),
            )
        )
        self.response = self.transport.return_value.getresponse.return_value
        self.response.status = 200
        self.response.read.return_value = canonical(envelope()).encode()

    def worker(self):
        with patch.object(
            ev, "read_dedicated_credential", return_value=self.credential
        ):
            return ev.worker(
                {
                    "config": configuration(),
                    "context": context(),
                    "credential_file": "/not-read/mock-credential",
                }
            )

    def test_missing_configuration_approval_budget_and_destination_fail_closed(self):
        for field in configuration():
            cfg = configuration()
            del cfg[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                ev.configuration("real", cfg)
        for field, value in (
            ("mode", "fake"),
            ("model", "another-model"),
            ("endpoint", "https://example.com/v1/responses"),
            ("endpoint", ENDPOINT + "?key=forbidden"),
            ("synthetic_only", False),
            ("synthetic_transmission_approved", False),
            ("approval_reference", " "),
            ("transmission_approval_reference", ""),
            ("max_requests", 4),
            ("max_requests", True),
            ("max_output_tokens", 2048),
            ("timeout_seconds", 31),
            ("total_budget_usd", "0.01"),
            ("total_budget_usd", "NaN"),
            ("total_budget_usd", "Infinity"),
            ("total_budget_usd", "2.00"),
        ):
            cfg = configuration()
            cfg[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                ev.configuration("real", cfg)
        self.transport.assert_not_called()
        self.assertEqual(str(3 * REQUEST_RESERVE_USD), "0.913824")

    def test_config_validation_does_not_load_credentials(self):
        with patch.object(ev, "read_dedicated_credential", side_effect=AssertionError):
            ev.configuration("real", configuration())
        self.transport.assert_not_called()
        with self.assertRaises(ValueError):
            Runner(configuration()).generate(context())
        self.transport.assert_not_called()

    def test_exact_payload_has_no_tools_credentials_or_evaluation_metadata(self):
        result = self.worker()
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["provider"], "openai")
        self.transport.assert_called_once_with("api.openai.com", 443, timeout=30)
        request = self.transport.return_value.request.call_args
        self.assertEqual(request.args, ("POST", "/v1/responses"))
        body = json.loads(request.kwargs["body"])
        self.assertEqual(body["input"], canonical(context()))
        self.assertEqual(body["instructions"], PROMPT + canonical(OUTPUT_SCHEMA))
        self.assertEqual(body["max_output_tokens"], 1024)
        self.assertFalse(body["store"])
        self.assertFalse(body["background"])
        self.assertEqual(body["service_tier"], "default")
        self.assertNotIn("tools", body)
        for word in (
            self.credential,
            "approval_reference",
            "tenant_id",
            "human_action",
            "expected",
            "split",
            "credential_file",
        ):
            self.assertNotIn(word, request.kwargs["body"])
        self.assertNotIn(self.credential, canonical(result))
        self.assertEqual(result["usage"], {"input_tokens": 100, "output_tokens": 50})

    def test_bounded_requests_and_input_without_retries(self):
        runner = Runner(configuration(), credential_loader=lambda: self.credential)
        for _ in range(3):
            runner.generate(context())
        with self.assertRaises(ValueError):
            runner.generate(context())
        self.assertEqual(self.transport.call_count, 3)
        oversized = context()
        oversized["facts"] = ["x" * 17000]
        with self.assertRaises(ValueError):
            Runner(configuration(), credential_loader=lambda: self.credential).generate(
                oversized
            )
        self.assertEqual(self.transport.call_count, 3)

    def test_refusal_incomplete_and_no_hidden_fallback(self):
        for state in ("REFUSAL", "INCOMPLETE"):
            value = envelope()
            if state == "REFUSAL":
                value["output"][0]["content"] = [
                    {"type": "refusal", "refusal": "declined"}
                ]
            else:
                value["status"] = "incomplete"
            self.response.read.return_value = canonical(value).encode()
            self.assertEqual(self.worker()["status"], state)
        self.assertEqual(self.transport.call_count, 2)

    def test_malformed_oversized_schema_and_tool_outputs_rejected(self):
        bad_schema = envelope()
        value = fake_proposal(context())
        value["proposals"][0]["question"] = "Question" + " " * 600
        bad_schema["output"][0]["content"][0]["text"] = canonical(value)
        tool = envelope()
        tool["output"] = [{"type": "function_call", "name": "bad"}]
        other_model = envelope()
        other_model["model"] = "different"
        malformed_content = envelope()
        malformed_content["output"][0]["content"] = [None]
        for raw in (
            b"invalid",
            b"x" * 32001,
            canonical(bad_schema).encode(),
            canonical(tool).encode(),
            canonical(other_model).encode(),
            canonical(malformed_content).encode(),
            b"[]",
        ):
            self.response.read.return_value = raw
            self.assertEqual(self.worker()["status"], "INVALID_OUTPUT")

    def test_timeouts_transport_errors_redirects_are_not_retried(self):
        for exc, status in (
            (TimeoutError(), "TIMEOUT_AMBIGUOUS"),
            (OSError(), "TRANSPORT_FAILURE_AMBIGUOUS"),
        ):
            self.transport.return_value.request.side_effect = exc
            self.assertEqual(self.worker()["status"], status)
        self.transport.return_value.request.side_effect = None
        for code in (302, 401, 429, 500):
            self.response.status = code
            self.assertEqual(self.worker()["status"], "TRANSPORT_FAILURE_AMBIGUOUS")
        self.assertEqual(self.transport.call_count, 6)

    def test_credential_echo_is_never_published(self):
        self.response.read.return_value = self.credential.encode()
        value = self.worker()
        self.assertEqual(value["status"], "REDACTED_PROVIDER_RESPONSE")
        self.assertEqual(value["raw_response_base64"], [])

    def test_dry_run_refuses_hosted_configuration(self):
        with self.assertRaises(ValueError):
            ev.configuration("dry-run", configuration())
        self.transport.assert_not_called()

    def test_parent_passes_path_not_secret_and_no_inherited_custody(self):
        with patch.object(
            ev.subprocess,
            "run",
            return_value=MagicMock(returncode=0, stdout='{"status":"REFUSAL"}'),
        ) as run:
            ev.isolated_attempt(
                configuration(), context(), credential_file="/private/mock"
            )
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["credential_file"], "/private/mock")
        self.assertEqual(set(payload), {"config", "context", "credential_file"})
        self.assertEqual(
            set(run.call_args.kwargs["env"]),
            {"PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE"},
        )
        self.assertNotIn(self.credential, str(run.call_args))

    def test_only_private_regular_explicit_credential_file_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test-only"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(self.credential)
            self.assertEqual(read_dedicated_credential(str(path)), self.credential)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_dedicated_credential(str(path))
            path.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                read_dedicated_credential(str(link))


if __name__ == "__main__":
    unittest.main()
