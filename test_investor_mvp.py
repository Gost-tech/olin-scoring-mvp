"""Acceptance contract for the connected investor MVP.

The test proves that partner intake and the analyst workspace share one
persisted shadow case. It deliberately excludes real data and money movement.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from test_shadow_mvp import running_server


def request_json(url: str, method: str = "GET", payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        finally:
            exc.close()


class InvestorMVPTests(unittest.TestCase):
    def test_partner_case_survives_the_full_analyst_loop(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file, patch.dict(
            os.environ, {"OLIN_MODE": "demo"}, clear=False
        ):
            with running_server(db_file.name) as base:
                status, scenarios = request_json(base + "/api/demo/scenarios")
                self.assertEqual(status, 200)
                payload = scenarios[0]["payload"]
                payload["merchant_name"] = "Comercio Demo Inversionista"
                payload["partner_case_reference"] = "INVESTOR-MVP-001"

                status, created = request_json(
                    base + "/api/applications", "POST", payload
                )
                self.assertEqual(status, 201)
                app_id = created["application_id"]
                self.assertEqual(created["analyst_ui"], "/")
                self.assertEqual(
                    created["case_path"], f"/api/applications/{app_id}"
                )

                status, queue = request_json(base + "/api/apps")
                self.assertEqual(status, 200)
                self.assertIn(app_id, [case["application_id"] for case in queue])

                status, _ = request_json(
                    base + f"/api/apps/{app_id}/decision",
                    "POST",
                    {
                        "decision": "MANUAL_REVIEW",
                        "reason": "Validación del MVP por el analista.",
                    },
                )
                self.assertEqual(status, 200)

                status, persisted = request_json(
                    base + f"/api/applications/{app_id}"
                )
                self.assertEqual(status, 200)
                self.assertEqual(persisted["analyst_decision"], "MANUAL_REVIEW")
                self.assertEqual(
                    persisted["analyst_reason"],
                    "Validación del MVP por el analista.",
                )

                status, blocked = request_json(
                    base + f"/api/apps/{app_id}/disburse", "POST", {}
                )
                self.assertEqual(status, 403)
                self.assertIn("shadow", blocked["error"].lower())

    def test_intake_links_directly_to_the_persisted_case(self):
        intake = os.path.join(
            os.path.dirname(__file__), "olin", "shadow_intake.html"
        )
        with open(intake, encoding="utf-8") as handle:
            html = handle.read()
        self.assertIn("/?case=${encodeURIComponent(data.application_id)}", html)
        self.assertIn("Abrir este expediente", html)


if __name__ == "__main__":
    unittest.main()
