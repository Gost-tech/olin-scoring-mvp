import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olin.operations import control_room
from olin.store import ScoringLog
from test_shadow_mvp import request, running_server


class OperationsControlRoomTests(unittest.TestCase):
    def test_empty_database_has_stable_shape_and_unassigned_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "ops.db")
            with ScoringLog(database):
                pass
            result = control_room(database)
        self.assertEqual(result["counts"]["total"], 0)
        self.assertEqual(result["items"], [])
        self.assertFalse(result["owners"]["ownership_ready"])
        self.assertEqual(result["mode"], "read_only_exception_projection")

    def test_authenticated_http_control_room_is_read_only(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file, patch.dict(
            os.environ, {"OLIN_MODE": "demo"}, clear=True,
        ):
            with running_server(db_file.name) as base:
                status, raw, _headers = request(
                    base, "/api/v1/operations/control-room"
                )
        self.assertEqual(status, 200)
        result = json.loads(raw)["data"]
        self.assertEqual(result["mode"], "read_only_exception_projection")


if __name__ == "__main__":
    unittest.main()
