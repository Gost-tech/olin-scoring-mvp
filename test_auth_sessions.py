from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from olin.api.auth import authenticate, authenticate_session, issue_session


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.users = json.dumps({
            "bank_ingestion": {"token": "p" * 40, "role": "partner"},
            "risk_reviewer": {"token": "r" * 40, "role": "analyst"},
            "olin_operator": {"token": "a" * 40, "role": "admin"},
        })
        self.env = {
            "OLIN_MODE": "production",
            "OLIN_USERS": self.users,
            "OLIN_REQUIRE_SHORT_LIVED_SESSIONS": "1",
            "OLIN_SESSION_SECRET": "s" * 40,
            "OLIN_SESSION_TTL_MINUTES": "15",
        }

    def test_named_key_exchanges_for_short_lived_session(self):
        headers = {"Authorization": f"Bearer {'p' * 40}"}
        with patch.dict(os.environ, self.env, clear=True):
            issued = issue_session(headers, now=1_800_000_000)
            user = authenticate_session(issued["access_token"], now=1_800_000_100)
        self.assertEqual("bank_ingestion", user.name)
        self.assertEqual("partner", user.role)
        self.assertEqual("session", user.credential_kind)
        self.assertEqual(900, issued["expires_in"])

    def test_expired_or_tampered_session_is_rejected(self):
        headers = {"Authorization": f"Bearer {'p' * 40}"}
        with patch.dict(os.environ, self.env, clear=True):
            issued = issue_session(headers, now=1_800_000_000)
            self.assertIsNone(authenticate_session(issued["access_token"], now=1_800_001_000))
            self.assertIsNone(authenticate_session(issued["access_token"] + "x", now=1_800_000_100))

    def test_long_lived_key_is_not_accepted_as_an_api_session(self):
        headers = {"Authorization": f"Bearer {'p' * 40}"}
        with patch.dict(os.environ, self.env, clear=True):
            self.assertIsNone(authenticate(headers))
            issued = issue_session(headers, now=1_800_000_000)
            session_headers = {"Authorization": f"Bearer {issued['access_token']}"}
            with patch("olin.api.auth.time.time", return_value=1_800_000_100):
                self.assertIsNotNone(authenticate(session_headers))


if __name__ == "__main__":
    unittest.main()
