"""Disposable synthetic Phase7 setup + least-privilege analyst child process.

Uses existing canonical test fixture authority, never production provisioning.
Requires explicitly disposable *_investigator_test PostgreSQL; destroys only
its fixture schemas at shutdown. Do not run alongside database tests.
"""

import argparse
import http.client
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import test_investigator_postgres_workflow as pg
from test_investigator_postgres_feedback import FeedbackPostgresTests


class StartupFailure(RuntimeError):
    """Redacted launcher failure; never include underlying DSNs or child output."""


def preflight_database():
    if not pg.POSTGRES_AVAILABLE or not pg.DISPOSABLE:
        raise StartupFailure("Explicit disposable PostgreSQL confirmation required")
    conn = None
    try:
        if any(name.startswith("PG") for name in os.environ):
            raise StartupFailure(
                "Libpq environment overrides prohibited; use the explicit disposable DSN"
            )
        info = pg.conninfo_to_dict(pg.ADMIN_DSN)
        if (
            set(info) - {"host", "port", "dbname", "user", "password"}
            or info.get("host") != "127.0.0.1"
            or not info.get("port", "").isdigit()
            or not info.get("dbname", "").endswith("_investigator_test")
        ):
            raise StartupFailure(
                "Explicit loopback port and *_investigator_test database required"
            )
        conn = pg.psycopg.connect(
            pg.ADMIN_DSN, hostaddr="127.0.0.1", autocommit=True, connect_timeout=5
        )
        conn.execute("SET statement_timeout='5s'; SET lock_timeout='1s'")
        if not conn.execute("SELECT pg_try_advisory_lock(726081907)").fetchone()[0]:
            raise StartupFailure("Disposable launcher already owns this cluster")
        version, encoding, database = conn.execute(
            "SELECT current_setting('server_version_num')::integer, current_setting('server_encoding'), current_database()"
        ).fetchone()
        occupied = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%') "
            "OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public') "
            "OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public') "
            "OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname LIKE 'olin_%') "
            "OR EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid())"
        ).fetchone()[0]
        if (
            version // 10000 != 16
            or encoding != "UTF8"
            or database != info["dbname"]
            or occupied
        ):
            raise StartupFailure(
                "Empty isolated UTF-8 PostgreSQL16 database and unused fixture roles required"
            )
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        raise


def check_ports(*ports):
    if len(set(ports)) != len(ports):
        raise StartupFailure("Application and operator ports must differ")
    for port in ports:
        if not 1024 <= port <= 65535:
            raise StartupFailure("Unprivileged loopback ports required")
        try:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", port))
        except OSError:
            raise StartupFailure("Requested loopback port is unavailable") from None


def child_environments(fixture, operator_port):
    base = fixture.base
    common = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    token = secrets.token_urlsafe(48)
    operator = {
        **common,
        "OLIN_SYNTHETIC_RUNTIME_DATABASE_URL": base._dsn(base.runtime_role),
        "OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL": base._dsn(
            base.authority_role
        ),
        "OLIN_SYNTHETIC_OPERATOR_TOKEN": token,
    }
    app = {
        **common,
        "OLIN_INVESTIGATOR_DATABASE_URL": base._dsn(base.runtime_role),
        "OLIN_INVESTIGATOR_ACTION_DATABASE_URL": base._dsn(base.action_role),
        "OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL": base._dsn(base.reader_role),
        "OLIN_INVESTIGATOR_FEEDBACK_DATABASE_URL": base._dsn(fixture.roles[0]),
        "OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_URL": f"http://127.0.0.1:{operator_port}",
        "OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_TOKEN": token,
        "OLIN_INVESTIGATOR_SESSION_SECRET": secrets.token_urlsafe(48),
        "OLIN_INVESTIGATOR_USERS": json.dumps(
            {
                "SYNTHETIC-analyst": {
                    "token": "synthetic-feedback-demo-only",
                    "tenant_id": str(base.tenant),
                    "role": "analyst",
                }
            }
        ),
    }
    return operator, app


def start_child(module, port, env):
    return subprocess.Popen(
        [sys.executable, "-m", module, "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def shadow_configuration(mode):
    """Validate opt-in configuration without reading any credential file."""
    if mode == "none":
        return None
    if mode == "fake":
        return {"mode": "fake"}
    from olin.investigator_shadow_openai import validate_config

    config = json.loads(os.environ.get("OLIN_SHADOW_RUNNER_CONFIG", "{}"))
    validate_config(config)
    path = os.environ.get("OLIN_SHADOW_CREDENTIAL_FILE", "")
    if not os.path.isabs(path):
        raise StartupFailure("Absolute runner-only credential path required")
    return config


def shadow_environments(fixture, app, cases, port, config):
    token = secrets.token_urlsafe(48)
    runner = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "OLIN_SHADOW_RUNNER_CONFIG": json.dumps(config),
        "OLIN_SHADOW_RUNNER_TOKEN": token,
    }
    if config["mode"] == "openai":
        runner["OLIN_SHADOW_CREDENTIAL_FILE"] = os.environ[
            "OLIN_SHADOW_CREDENTIAL_FILE"
        ]
    app.update(
        {
            "OLIN_INVESTIGATOR_RESEARCH_DATABASE_URL": fixture.base._dsn(
                "olin_research_t_" + fixture.base.tenant.hex
            ),
            "OLIN_INVESTIGATOR_SHADOW_RUNNER_URL": f"http://127.0.0.1:{port}",
            "OLIN_INVESTIGATOR_SHADOW_RUNNER_TOKEN": token,
            "OLIN_INVESTIGATOR_SHADOW_PROVIDER": config["mode"],
            "OLIN_INVESTIGATOR_SHADOW_MODEL": config.get(
                "model", "deterministic-fake-1"
            ),
            "OLIN_INVESTIGATOR_SHADOW_SYNTHETIC_CASES": json.dumps(
                list(cases.values())
            ),
        }
    )
    return runner


def wait_shadow_ready(child, port, token, identity, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise StartupFailure("Shadow runner exited before readiness")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        try:
            conn.request("GET", "/ready", headers={"Authorization": "Bearer " + token})
            response = conn.getresponse()
            body = response.read(1025)
            if response.status == 200 and json.loads(body) == identity:
                return
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        time.sleep(0.05)
    raise StartupFailure("Shadow runner readiness timed out")


def wait_ready(child, port, *, token=None, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise StartupFailure("Child exited before readiness")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        try:
            if token:
                # Existing authenticated handler rejects this unknown fixture before DB work.
                conn.request(
                    "POST",
                    "/v1/synthetic-evidence",
                    b'{"fixture":"__readiness__"}',
                    {
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                )
            else:
                conn.request("GET", "/")
            response = conn.getresponse()
            body = response.read(262145)
            ready = (
                (
                    response.status == 409
                    and body == b'{"error":"synthetic operation failed safely"}'
                )
                if token
                else (response.status == 200 and b"SYNTHETIC DEMONSTRATION" in body)
            )
            if ready and child.poll() is None:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        time.sleep(0.05)
    raise StartupFailure("Child readiness timed out")


def stop_children(children):
    failed = False
    for child in reversed(children):
        try:
            if child.poll() is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            failed = True
    if failed:
        raise StartupFailure("Owned child cleanup could not be confirmed")


def cleanup_fixture(conn, fixture):
    # Preflight proved these schemas/roles absent. Restrict cleanup to exact
    # migration roles and the generated fixture logins, including partial setup.
    roles = {
        "olin_investigator_" + name
        for name in (
            "owner",
            "runtime",
            "evidence_authority",
            "evidence_reader",
            "action_writer",
            "research",
            "feedback",
            "cohort_operator",
        )
    }
    base = getattr(fixture, "base", pg.InvestigatorPostgresWorkflowTests)
    roles.update(getattr(base, "passwords", {}).keys())
    tenant = getattr(base, "tenant", None)
    if tenant is not None:
        roles.update(
            prefix + tenant.hex
            for prefix in (
                "olin_inv_t_",
                "olin_action_t_",
                "olin_evidence_t_",
                "olin_canonical_t_",
                "olin_research_t_",
                "olin_feedback_t_",
                "olin_cohort_t_",
            )
        )
    conn.execute("DROP SCHEMA IF EXISTS investigator CASCADE")
    conn.execute("DROP SCHEMA IF EXISTS evidence_authority CASCADE")
    for role in sorted(roles):
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
            conn.execute(pg.sql.SQL("DROP OWNED BY {}").format(pg.sql.Identifier(role)))
            conn.execute(pg.sql.SQL("DROP ROLE {}").format(pg.sql.Identifier(role)))
    admin = getattr(base, "admin", None)
    if admin is not None:
        admin.close()


def run(args):
    mode = getattr(args, "shadow_mode", "none")
    config = shadow_configuration(mode)
    check_ports(args.port, args.operator_port)
    if config and args.shadow_port in {args.port, args.operator_port}:
        raise StartupFailure("Shadow port must be separate")
    conn = preflight_database()
    fixture = FeedbackPostgresTests
    children = []
    try:
        fixture.setUpClass()
        cases = {}
        first = None
        for label in ("useful", "uncertain", "unobserved"):
            case = fixture()
            case.setUp()
            if first is None:
                first = case
            cases[label] = str(case.case_id)
            if label == "uncertain":
                action = case.case._select_and_request("synthetic-feedback-stopped")
                case.case.service.synthetic_response(
                    case.case.identity,
                    case.case_id,
                    UUID(action["action"]["action_id"]),
                    fixture="unavailable",
                )
        cohort = first.freeze([UUID(c) for c in cases.values()])
        operator_env, app_env = child_environments(fixture, args.operator_port)
        operator = start_child(
            "olin.investigator_synthetic_operator", args.operator_port, operator_env
        )
        children.append(operator)
        wait_ready(
            operator,
            args.operator_port,
            token=operator_env["OLIN_SYNTHETIC_OPERATOR_TOKEN"],
        )
        shadow_status = "DISABLED"
        if config:
            runner_env = shadow_environments(
                fixture, app_env, cases, args.shadow_port, config
            )
            try:
                check_ports(args.shadow_port)
                runner = start_child(
                    "olin.investigator_shadow_runner", args.shadow_port, runner_env
                )
                children.append(runner)
                wait_shadow_ready(
                    runner,
                    args.shadow_port,
                    runner_env["OLIN_SHADOW_RUNNER_TOKEN"],
                    {
                        "provider": config["mode"],
                        "model": app_env["OLIN_INVESTIGATOR_SHADOW_MODEL"],
                    },
                )
                shadow_status = "READY_RESEARCH_ONLY_" + config["mode"].upper()
            except (StartupFailure, OSError):
                # No fallback, restart, or inference probe; human services remain usable.
                shadow_status = "UNAVAILABLE"
        app = start_child("olin.investigator_app", args.port, app_env)
        children.append(app)
        wait_ready(app, args.port)
        if operator.poll() is not None:
            raise StartupFailure("Operator exited during application startup")
        print(
            json.dumps(
                {
                    "status": "READY",
                    "synthetic_only": True,
                    "cases": cases,
                    "cohort_id": cohort["cohort_id"],
                    "url": f"http://127.0.0.1:{args.port}",
                    "shadow": shadow_status,
                }
            ),
            flush=True,
        )
        while operator.poll() is None and app.poll() is None:
            time.sleep(0.2)
        raise StartupFailure("Connected service exited; stopping owned services")
    finally:
        # A second Ctrl-C/TERM must not interrupt cleanup of owned processes.
        handlers = {
            sig: signal.signal(sig, signal.SIG_IGN)
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            stop_children(children)
            cleanup_fixture(conn, fixture)
        finally:
            conn.close()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--operator-port", type=int, default=8768)
    parser.add_argument(
        "--shadow-mode", choices=("none", "fake", "openai"), default="none"
    )
    parser.add_argument("--shadow-port", type=int, default=8769)
    args = parser.parse_args()
    if not pg.POSTGRES_AVAILABLE or not pg.DISPOSABLE:
        raise RuntimeError(
            "Explicit disposable PostgreSQL confirmation and test DSN required"
        )

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args)
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001 - redact child/driver failures at CLI boundary
        print(
            "Connected synthetic startup/run failed safely; check isolated database, ports and child configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    main()
