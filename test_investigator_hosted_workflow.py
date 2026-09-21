"""Guarded application wiring: synthetic mocks only; no provider credential access."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from olin.investigator_shadow import fake_proposal
from olin.investigator_shadow_runner import build_handler, runner_from_environment
from olin.investigator_shadow_service import ShadowResearchService, ShadowTransport
from scripts import run_investigator_feedback_demo as demo
from test_investigator_phase5b_shadow import context
from test_investigator_shadow_openai import configuration, envelope


class HostedWorkflowTests(unittest.TestCase):
    def test_coordinator_rejects_provider_or_model_substitution(self):
        for provider, model in (
            ("fake", "deterministic-fake-1"),
            ("ollama", "synthetic-model"),
            ("openai", "wrong-model"),
        ):
            runner = MagicMock(mode="openai", model=configuration()["model"])
            runner.generate.return_value = {
                "provider": provider,
                "model": model,
                "proposal": fake_proposal(context()),
            }
            service = ShadowResearchService(None, None, runner, synthetic_cases=[])
            record = {"context": context(), "events": []}
            with (
                self.subTest(provider=provider, model=model),
                patch.object(service, "_call", return_value=record) as call,
                patch.object(service, "_fresh"),
                patch.object(service, "_bind_human", return_value=record),
            ):
                service.generate(None, None, None)
            self.assertEqual(
                call.call_args.args[4], {"status": "INVALID_OUTPUT", "proposal": None}
            )

    def test_failed_shadow_start_keeps_human_services_until_shutdown(self):
        fixture = MagicMock()
        fixture.return_value.case_id = uuid4()
        fixture.return_value.freeze.return_value = {"cohort_id": str(uuid4())}
        fixture.return_value.case._select_and_request.return_value = {
            "action": {"action_id": str(uuid4())}
        }
        fixture.base.tenant = uuid4()
        operator, runner, app = MagicMock(), MagicMock(), MagicMock()
        operator.poll.return_value = app.poll.return_value = None
        runner.poll.return_value = 1
        args = SimpleNamespace(
            port=8767, operator_port=8768, shadow_port=8769, shadow_mode="fake"
        )
        with (
            patch.object(demo, "check_ports"),
            patch.object(demo, "preflight_database", return_value=MagicMock()),
            patch.object(demo, "FeedbackPostgresTests", fixture),
            patch.object(
                demo,
                "child_environments",
                return_value=({"OLIN_SYNTHETIC_OPERATOR_TOKEN": "synthetic"}, {}),
            ),
            patch.object(
                demo, "start_child", side_effect=[operator, runner, app]
            ) as start,
            patch.object(demo, "wait_ready"),
            patch.object(
                demo,
                "wait_shadow_ready",
                side_effect=demo.StartupFailure("synthetic unavailable"),
            ),
            patch.object(demo.time, "sleep", side_effect=KeyboardInterrupt),
            patch.object(demo, "stop_children") as stop,
            patch.object(demo, "cleanup_fixture"),
            patch("builtins.print") as output,
            self.assertRaises(KeyboardInterrupt),
        ):
            demo.run(args)
        self.assertEqual(start.call_count, 3)
        self.assertEqual(json.loads(output.call_args.args[0])["shadow"], "UNAVAILABLE")
        self.assertEqual(stop.call_args.args[0], [operator, runner, app])

    def test_hosted_failures_through_real_loopback_handler(self):
        for kind, expected in (
            ("refusal", "REFUSAL"),
            ("invalid", "INVALID_OUTPUT"),
            ("incomplete", "FAILED"),
            ("timeout", "TIMEOUT"),
            ("http", "FAILED"),
        ):
            environment, _ = self.environments()
            data = envelope()
            if kind == "refusal":
                data["output"][0]["content"] = [
                    {"type": "refusal", "refusal": "synthetic sensitive text"}
                ]
            elif kind == "invalid":
                data["output"][0]["content"][0]["text"] = (
                    '{"unexpected":"synthetic sensitive text"}'
                )
            elif kind == "incomplete":
                data["status"] = "incomplete"
            response = MagicMock(status=400 if kind == "http" else 200)
            response.read.return_value = json.dumps(data).encode()
            with (
                self.subTest(kind=kind),
                patch(
                    "olin.investigator_shadow_openai.read_dedicated_credential",
                    return_value="synthetic-private-test-value",
                ),
                patch(
                    "olin.investigator_shadow_openai.http.client.HTTPSConnection"
                ) as https,
            ):
                https.return_value.getresponse.return_value = response
                if kind == "timeout":
                    https.return_value.getresponse.side_effect = TimeoutError()
                runner = runner_from_environment(environment)
                token = environment["OLIN_SHADOW_RUNNER_TOKEN"]
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0), build_handler(runner, token)
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                try:
                    transport = ShadowTransport(
                        f"http://127.0.0.1:{server.server_port}",
                        token,
                        provider="openai",
                        model=configuration()["model"],
                    )
                    result = transport.generate(context())
                    self.assertEqual(result, {"failure": expected})
                    self.assertEqual(https.call_count, 1)
                    self.assertEqual(runner.used, 1)
                    self.assertNotIn("synthetic", json.dumps(result))
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def environments(self, mode="openai"):
        base = SimpleNamespace(tenant=uuid4(), _dsn=lambda role: "synthetic-" + role)
        fixture = SimpleNamespace(base=base)
        config = configuration() if mode == "openai" else {"mode": "fake"}
        app = {}
        with patch.dict(
            demo.os.environ, {"OLIN_SHADOW_CREDENTIAL_FILE": "/synthetic/not-opened"}
        ):
            runner = demo.shadow_environments(
                fixture, app, {"case": str(uuid4())}, 8769, config
            )
        return runner, app

    def test_separate_process_custody_and_identity(self):
        runner, app = self.environments()
        self.assertNotIn("OLIN_SHADOW_CREDENTIAL_FILE", app)
        self.assertNotIn("/synthetic/not-opened", json.dumps(app))
        self.assertFalse(
            any(
                "DATABASE" in key or "ACTION" in key or "EVIDENCE" in key
                for key in runner
            )
        )
        self.assertNotIn("credential", runner["OLIN_SHADOW_RUNNER_CONFIG"])
        self.assertEqual(app["OLIN_INVESTIGATOR_SHADOW_PROVIDER"], "openai")
        self.assertEqual(
            runner["OLIN_SHADOW_RUNNER_TOKEN"],
            app["OLIN_INVESTIGATOR_SHADOW_RUNNER_TOKEN"],
        )

    def test_only_runner_loads_credential_lazily_mocked_https(self):
        environment, app = self.environments()
        response = MagicMock(status=200)
        response.read.return_value = json.dumps(envelope()).encode()
        with (
            patch(
                "olin.investigator_shadow_openai.read_dedicated_credential",
                return_value="synthetic-dedicated-test-value",
            ) as load,
            patch(
                "olin.investigator_shadow_openai.http.client.HTTPSConnection"
            ) as https,
        ):
            runner = runner_from_environment(environment)
            load.assert_not_called()
            https.return_value.getresponse.return_value = response
            result = runner.generate(context())
            load.assert_called_once_with("/synthetic/not-opened")
            self.assertEqual(result["provider"], "openai")
            self.assertEqual(result["model"], app["OLIN_INVESTIGATOR_SHADOW_MODEL"])
            self.assertEqual(https.call_args.args[0], "api.openai.com")
            body = https.return_value.request.call_args.kwargs["body"]
            self.assertNotIn(b"synthetic-dedicated-test-value", body)
            self.assertNotIn(b"DATABASE", body)

    def test_runner_rejects_extra_custody_and_relative_path(self):
        environment, _ = self.environments()
        for key in (
            "OPENAI_API_KEY",
            "DATABASE_URL",
            "OLIN_INVESTIGATOR_ACTION_DATABASE_URL",
            "OLIN_INVESTIGATOR_SESSION_SECRET",
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                runner_from_environment({**environment, key: "synthetic-forbidden"})
        environment["OLIN_SHADOW_CREDENTIAL_FILE"] = "relative"
        with self.assertRaises(ValueError):
            runner_from_environment(environment)

    def test_fake_has_no_credential_and_no_fallback(self):
        environment, app = self.environments("fake")
        environment["__CF_USER_TEXT_ENCODING"] = "synthetic-locale"
        self.assertNotIn("OLIN_SHADOW_CREDENTIAL_FILE", environment)
        self.assertEqual(runner_from_environment(environment).mode, "fake")
        self.assertEqual(app["OLIN_INVESTIGATOR_SHADOW_PROVIDER"], "fake")
        environment["OLIN_SHADOW_CREDENTIAL_FILE"] = "/synthetic/not-opened"
        with self.assertRaises(ValueError):
            runner_from_environment(environment)

    def test_opt_in_requires_approval_without_opening_file(self):
        with patch.dict(demo.os.environ, {}, clear=True):
            self.assertIsNone(demo.shadow_configuration("none"))
            self.assertEqual(demo.shadow_configuration("fake"), {"mode": "fake"})
            with self.assertRaises(ValueError):
                demo.shadow_configuration("openai")

    def test_openai_identity_still_requires_loopback_and_token(self):
        transport = ShadowTransport(
            "http://127.0.0.1:8769",
            "synthetic-token-long-enough",
            provider="openai",
            model=configuration()["model"],
        )
        self.assertEqual(transport.mode, "openai")
        for url in (
            "https://api.openai.com",
            "http://example.com",
            "http://127.0.0.1:8769/generate",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ShadowTransport(
                    url,
                    "synthetic-token-long-enough",
                    provider="openai",
                    model=configuration()["model"],
                )

    def test_readiness_does_not_generate_or_load_credential(self):
        child = MagicMock()
        child.poll.return_value = None
        conn = MagicMock()
        identity = {"provider": "openai", "model": configuration()["model"]}
        conn.getresponse.return_value.status = 200
        conn.getresponse.return_value.read.return_value = json.dumps(identity).encode()
        with patch.object(demo.http.client, "HTTPConnection", return_value=conn):
            demo.wait_shadow_ready(child, 8769, "synthetic-token", identity)
        self.assertEqual(conn.request.call_args.args, ("GET", "/ready"))
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
