"""Launcher custody/lifecycle tests; database semantics remain in PostgreSQL suites."""

import argparse
import json
import socket
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts import run_investigator_feedback_demo as demo


class LauncherTests(unittest.TestCase):
    def test_inherited_libpq_override_rejected_before_connection(self):
        for name in ("PGHOSTADDR", "PGSERVICE", "PGOPTIONS"):
            with (
                self.subTest(name=name),
                patch.object(demo.pg, "POSTGRES_AVAILABLE", True),
                patch.object(demo.pg, "DISPOSABLE", True),
                patch.dict(demo.os.environ, {name: "synthetic-override"}),
                self.assertRaisesRegex(demo.StartupFailure, "overrides prohibited"),
            ):
                demo.preflight_database()

    def test_explicit_guard_before_mutation(self):
        with (
            patch.object(demo.pg, "DISPOSABLE", False),
            patch.object(demo.FeedbackPostgresTests, "setUpClass") as setup,
        ):
            with self.assertRaises(demo.StartupFailure):
                demo.preflight_database()
            setup.assert_not_called()

    @unittest.skipIf(demo.pg.psycopg is None, "locked psycopg dependency unavailable")
    def test_database_preflight_checks_encoding_version_empty_and_identity(self):
        for version, encoding, name, occupied in (
            (160015, "SQL_ASCII", "demo_investigator_test", False),
            (180000, "UTF8", "demo_investigator_test", False),
            (160015, "UTF8", "production", False),
            (160015, "UTF8", "demo_investigator_test", True),
        ):
            conn = MagicMock()
            conn.execute.return_value.fetchone.side_effect = [
                (True,),
                (version, encoding, name),
                (occupied,),
            ]
            with (
                self.subTest(encoding=encoding, version=version, occupied=occupied),
                patch.object(demo.pg, "POSTGRES_AVAILABLE", True),
                patch.object(demo.pg, "DISPOSABLE", True),
                patch.object(
                    demo.pg,
                    "ADMIN_DSN",
                    "host=127.0.0.1 port=55443 dbname=demo_investigator_test",
                ),
                patch.object(demo.pg.psycopg, "connect", return_value=conn),
            ):
                with self.assertRaises(demo.StartupFailure):
                    demo.preflight_database()
                conn.close.assert_called_once()
                self.assertFalse(
                    any(
                        "DROP" in str(x) or "CREATE" in str(x)
                        for x in conn.execute.call_args_list
                    )
                )

    @unittest.skipIf(demo.pg.psycopg is None, "locked psycopg dependency unavailable")
    def test_remote_or_implicit_database_rejected_before_connection(self):
        for dsn in (
            "dbname=demo_investigator_test",
            "host=example.com port=5432 dbname=demo_investigator_test",
            "host=127.0.0.1 port=5432 dbname=production",
            "host=127.0.0.1 hostaddr=192.0.2.1 port=5432 dbname=demo_investigator_test",
            "host=127.0.0.1 service=untrusted port=5432 dbname=demo_investigator_test",
        ):
            with (
                self.subTest(dsn=dsn),
                patch.object(demo.pg, "POSTGRES_AVAILABLE", True),
                patch.object(demo.pg, "DISPOSABLE", True),
                patch.object(demo.pg, "ADMIN_DSN", dsn),
                patch.object(demo.pg.psycopg, "connect") as connect,
            ):
                with self.assertRaises(demo.StartupFailure):
                    demo.preflight_database()
                connect.assert_not_called()

    def test_occupied_and_identical_ports_fail_before_setup(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            with self.assertRaises(demo.StartupFailure):
                demo.check_ports(port, 8768 if port != 8768 else 8769)
        with self.assertRaises(demo.StartupFailure):
            demo.check_ports(8767, 8767)

    def test_sanitized_children_and_transport_binding(self):
        base = SimpleNamespace(
            tenant=uuid4(),
            runtime_role="runtime",
            authority_role="authority",
            action_role="action",
            reader_role="reader",
            _dsn=lambda role: "synthetic-dsn-" + role,
        )
        fixture = SimpleNamespace(base=base, roles=["feedback"])
        with patch.dict(
            demo.os.environ,
            {
                "OPENAI_API_KEY": "synthetic-forbidden",
                "OLIN_INVESTIGATOR_TEST_ADMIN_DSN": "synthetic-admin",
                "PGPASSWORD": "synthetic-forbidden",
            },
        ):
            operator, app = demo.child_environments(fixture, 8768)
        self.assertEqual(
            set(operator),
            {
                "PATH",
                "PYTHONPATH",
                "OLIN_SYNTHETIC_RUNTIME_DATABASE_URL",
                "OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL",
                "OLIN_SYNTHETIC_OPERATOR_TOKEN",
            },
        )
        self.assertEqual(
            app["OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_URL"], "http://127.0.0.1:8768"
        )
        self.assertEqual(
            operator["OLIN_SYNTHETIC_OPERATOR_TOKEN"],
            app["OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_TOKEN"],
        )
        self.assertEqual(
            json.loads(app["OLIN_INVESTIGATOR_USERS"])["SYNTHETIC-analyst"][
                "tenant_id"
            ],
            str(base.tenant),
        )
        for forbidden in (
            "OPENAI_API_KEY",
            "PGPASSWORD",
            "OLIN_INVESTIGATOR_TEST_ADMIN_DSN",
            "OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL",
        ):
            self.assertNotIn(forbidden, app)
        self.assertNotIn("synthetic-dsn-authority", app.values())
        self.assertFalse(any("COHORT" in k or "RESEARCH" in k for k in app))

    def test_spawn_never_puts_credentials_in_arguments_or_inherits_streams(self):
        with patch.object(demo.subprocess, "Popen") as popen:
            demo.start_child(
                "olin.investigator_app", 8767, {"only": "synthetic-private"}
            )
        args, kwargs = popen.call_args
        self.assertNotIn("synthetic-private", str(args))
        self.assertIn("127.0.0.1", args[0])
        self.assertEqual(kwargs["env"], {"only": "synthetic-private"})
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(kwargs["start_new_session"])

    def test_readiness_is_bounded_authenticated_and_nonmutating(self):
        child = MagicMock()
        child.poll.return_value = None
        conn = MagicMock()
        response = conn.getresponse.return_value
        response.status = 409
        response.read.return_value = b'{"error":"synthetic operation failed safely"}'
        with patch.object(demo.http.client, "HTTPConnection", return_value=conn):
            demo.wait_ready(child, 8768, token="synthetic-transport-token")
        self.assertEqual(
            json.loads(conn.request.call_args.args[2]), {"fixture": "__readiness__"}
        )
        conn.close.assert_called_once()
        response.status = 404
        with (
            patch.object(demo.http.client, "HTTPConnection", return_value=conn),
            patch.object(demo.time, "monotonic", side_effect=[0, 0, 20]),
            patch.object(demo.time, "sleep"),
            self.assertRaises(demo.StartupFailure),
        ):
            demo.wait_ready(child, 8768, token="wrong")
        child.poll.return_value = 1
        with self.assertRaises(demo.StartupFailure):
            demo.wait_ready(child, 8768)

    def test_unavailable_operator_fails_closed(self):
        from olin.investigator_app import (
            InvestigatorAppError,
            LoopbackSyntheticOperator,
        )

        conn = MagicMock()
        conn.request.side_effect = OSError("synthetic unavailable")
        with (
            patch(
                "olin.investigator_app.http.client.HTTPConnection", return_value=conn
            ),
            self.assertRaises(InvestigatorAppError) as raised,
        ):
            LoopbackSyntheticOperator(
                "http://127.0.0.1:8768", "synthetic-local"
            ).submit(
                tenant_id=uuid4(),
                case_id=uuid4(),
                action_id=uuid4(),
                fixture="useful_coverage",
                expected_authority_revision=1,
            )
        self.assertEqual(raised.exception.status, 503)

    def test_partial_startup_cleans_only_owned_children_and_fixture(self):
        for failing_ready in (1, 2):
            fixture = MagicMock()
            fixture.return_value.case_id = uuid4()
            fixture.return_value.case._select_and_request.return_value = {
                "action": {"action_id": str(uuid4())}
            }
            child = MagicMock()
            child.poll.return_value = None
            conn = MagicMock()
            ready = (
                [demo.StartupFailure("synthetic failure")]
                if failing_ready == 1
                else [None, demo.StartupFailure("synthetic failure")]
            )
            with (
                self.subTest(stage=failing_ready),
                patch.object(demo, "check_ports"),
                patch.object(demo, "preflight_database", return_value=conn),
                patch.object(demo, "FeedbackPostgresTests", fixture),
                patch.object(
                    demo,
                    "child_environments",
                    return_value=({"OLIN_SYNTHETIC_OPERATOR_TOKEN": "synthetic"}, {}),
                ),
                patch.object(demo, "start_child", return_value=child) as start,
                patch.object(demo, "wait_ready", side_effect=ready),
                patch.object(demo, "stop_children") as stop,
                patch.object(demo, "cleanup_fixture") as cleanup,
                patch("builtins.print") as output,
            ):
                with self.assertRaises(demo.StartupFailure):
                    demo.run(argparse.Namespace(port=8767, operator_port=8768))
                self.assertEqual(start.call_count, failing_ready)
                self.assertEqual(len(stop.call_args.args[0]), failing_ready)
                cleanup.assert_called_once_with(conn, fixture)
                conn.close.assert_called_once()
                output.assert_not_called()

    def test_partial_fixture_failure_is_cleaned_without_starting_children(self):
        fixture = MagicMock()
        fixture.setUpClass.side_effect = RuntimeError("synthetic setup interruption")
        conn = MagicMock()
        with (
            patch.object(demo, "check_ports"),
            patch.object(demo, "preflight_database", return_value=conn),
            patch.object(demo, "FeedbackPostgresTests", fixture),
            patch.object(demo, "start_child") as start,
            patch.object(demo, "cleanup_fixture") as cleanup,
        ):
            with self.assertRaises(RuntimeError):
                demo.run(argparse.Namespace(port=8767, operator_port=8768))
            start.assert_not_called()
            cleanup.assert_called_once_with(conn, fixture)
            conn.close.assert_called_once()

    def test_shutdown_waits_then_kills_only_owned_unresponsive_child(self):
        child = MagicMock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 5), 0]
        demo.stop_children([child])
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_shutdown_attempts_all_children_after_one_reap_failure(self):
        first, second = MagicMock(), MagicMock()
        first.poll.return_value = second.poll.return_value = None
        second.wait.side_effect = OSError("synthetic reap failure")
        with self.assertRaises(demo.StartupFailure):
            demo.stop_children([first, second])
        first.terminate.assert_called_once()
        first.wait.assert_called_once()
        second.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
