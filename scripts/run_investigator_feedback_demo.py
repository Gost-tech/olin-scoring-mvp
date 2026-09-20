"""Disposable synthetic Phase7 setup + least-privilege analyst child process.

Uses existing canonical test fixture authority, never production provisioning.
Requires explicitly disposable *_investigator_test PostgreSQL; destroys only
its fixture schemas at shutdown. Do not run alongside database tests.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import test_investigator_postgres_workflow as pg
from test_investigator_postgres_feedback import FeedbackPostgresTests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if not pg.POSTGRES_AVAILABLE or not pg.DISPOSABLE:
        raise RuntimeError(
            "Explicit disposable PostgreSQL confirmation and test DSN required"
        )
    fixture = FeedbackPostgresTests
    fixture.setUpClass()
    child = None
    try:
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
                from uuid import UUID

                case.case.service.synthetic_response(
                    case.case.identity,
                    case.case_id,
                    UUID(action["action"]["action_id"]),
                    fixture="unavailable",
                )
        from uuid import UUID

        cohort = first.freeze([UUID(c) for c in cases.values()])
        base = fixture.base
        # Fresh child environment: no admin, operator, canonical-writer or model credentials.
        env = {
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "OLIN_INVESTIGATOR_DATABASE_URL": base._dsn(base.runtime_role),
            "OLIN_INVESTIGATOR_ACTION_DATABASE_URL": base._dsn(base.action_role),
            "OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL": base._dsn(
                base.reader_role
            ),
            "OLIN_INVESTIGATOR_FEEDBACK_DATABASE_URL": base._dsn(fixture.roles[0]),
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
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "olin.investigator_app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            env=env,
        )
        print(
            json.dumps(
                {
                    "synthetic_only": True,
                    "cases": cases,
                    "cohort_id": cohort["cohort_id"],
                    "url": f"http://127.0.0.1:{args.port}",
                }
            ),
            flush=True,
        )
        child.wait()
    finally:
        if child and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        fixture.tearDownClass()


if __name__ == "__main__":
    main()
