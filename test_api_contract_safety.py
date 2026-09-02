"""Bank-facing authentication, traceability, and terminology contracts."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from olin.api.auth import authenticate
from olin.store import ScoringLog
from test_product_mvp import partner_payload
from test_shadow_mvp import request, running_server


class APIContractSafetyTests(unittest.TestCase):
    def test_standard_bearer_authentication_is_supported(self):
        users = {"bank": {"token": "bank-secret", "role": "partner"}}
        with patch.dict(os.environ, {
            "OLIN_MODE": "production", "OLIN_USERS": json.dumps(users),
        }, clear=True):
            user = authenticate({"Authorization": "Bearer bank-secret"})
        self.assertIsNotNone(user)
        self.assertEqual("bank", user.name)

    def test_bank_response_is_traceable_and_not_an_official_approval(self):
        users = {"bank": {"token": "bank-secret", "role": "partner"}}
        env = {
            "OLIN_MODE": "production",
            "OLIN_USERS": json.dumps(users),
            "OLIN_BANK_WEBHOOK_SECRET": "webhook-secret-at-least-32-characters",
            "OLIN_ALLOW_LEGACY_CONSENT": "1",
        }
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, env, clear=True), running_server(tmp.name) as base:
                body = json.dumps(partner_payload()).encode()
                req = urllib.request.Request(
                    f"{base}/api/applications", data=body, method="POST",
                    headers={
                        "Authorization": "Bearer bank-secret",
                        "Content-Type": "application/json",
                        "X-Request-ID": "bank-uat-request-001",
                    },
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    result = json.loads(response.read())
                    self.assertEqual("bank-uat-request-001", response.headers["X-Request-ID"])
        self.assertEqual("decision_support_only", result["recommendation_scope"])
        self.assertTrue(result["requires_bank_decision"])
        self.assertNotIn("decision", result)
        self.assertNotIn("approved_amount_mxn", result)

    def test_error_body_and_header_share_request_id(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, {"OLIN_MODE": "demo"}, clear=True), running_server(tmp.name) as base:
                req = urllib.request.Request(
                    f"{base}/api/applications/missing", method="GET",
                    headers={"X-Request-ID": "bank-error-request-001"},
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(req, timeout=3)
                error = raised.exception
                payload = json.loads(error.read())
                self.assertEqual("bank-error-request-001", error.headers["X-Request-ID"])
                self.assertEqual("bank-error-request-001", payload["error"]["request_id"])
                error.close()


if __name__ == "__main__":
    unittest.main()
