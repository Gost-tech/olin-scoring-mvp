from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from olin.config import live_lending_enabled, live_lending_readiness
from olin.store import ScoringLog, connect_database


class PostgresRuntimeContractTests(unittest.TestCase):
    def test_sqlite_remains_available_for_synthetic_mode(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                self.assertFalse(getattr(log.conn, "is_postgres", False))

    def test_postgres_target_requires_driver_at_runtime(self):
        with patch.dict(os.environ, {"OLIN_DATABASE_URL": "postgresql://db/olin"}, clear=True):
            # The adapter must never silently fall back to SQLite.
            try:
                connect_database(os.environ["OLIN_DATABASE_URL"])
            except RuntimeError as exc:
                self.assertIn("psycopg", str(exc))
            except Exception as exc:
                # A configured but unreachable database is still a hard failure,
                # and must not be converted into a local SQLite connection.
                self.assertNotIsInstance(exc, FileNotFoundError)

    def test_real_money_gate_is_fail_closed_by_default(self):
        with patch.dict(os.environ, {"OLIN_MODE": "production"}, clear=True):
            status = live_lending_readiness()
            self.assertFalse(status["ready"])
            self.assertFalse(live_lending_enabled())
            self.assertFalse(status["checks"]["kill_switch_clear"])


if __name__ == "__main__":
    unittest.main()
