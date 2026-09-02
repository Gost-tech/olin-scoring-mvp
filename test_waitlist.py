from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from olin.waitlist import WaitlistStore, generate_encryption_key, parse_submission
from test_shadow_mvp import running_server


def payload(email: str = "ana@banco.mx") -> dict:
    return {
        "email": email,
        "contact_name": "Ana Riesgo",
        "organization": "Banco Prueba",
        "organization_type": "bank",
        "role": "Directora de crédito pyme",
        "portfolio_size": "1000_9999",
        "priority_problem": "Reconciliar evidencia fragmentada",
        "contact_consent": True,
        "source": "website_waitlist",
        "website": "",
    }


def api_request(base: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base}/api/v1/waitlist",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8001"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read()), exc.headers
        finally:
            exc.close()


class WaitlistStorageTests(unittest.TestCase):
    def test_email_is_encrypted_and_duplicate_does_not_inflate_count(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test"}):
                item = parse_submission(payload("ANA@BANCO.MX"))
                with WaitlistStore(tmp.name) as store:
                    first, first_count = store.submit(item)
                    second, second_count = store.submit(item)
                    raw = store.conn.execute(
                        "SELECT email_ciphertext, email_fingerprint FROM waitlist_entry"
                    ).fetchone()
                    entry_id = store.conn.execute(
                        "SELECT entry_id FROM waitlist_entry"
                    ).fetchone()[0]
                    decrypted = store.decrypt_email(entry_id)
                    leads = store.list_entries()
                    deleted = store.delete_by_email("ana@banco.mx")
                    final_count = store.public_count()
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual((1, 1), (first_count, second_count))
            self.assertNotIn("ana@banco.mx", raw)
            self.assertEqual("ana@banco.mx", decrypted)
            self.assertEqual("ana@banco.mx", leads[0]["email"])
            self.assertNotIn("email_ciphertext", leads[0])
            self.assertTrue(deleted)
            self.assertEqual(0, final_count)

    def test_rejects_unknown_fields_and_missing_contact_consent(self):
        invalid = payload()
        invalid["requested_credit_mxn"] = 100_000
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            parse_submission(invalid)
        invalid = payload()
        invalid["contact_consent"] = False
        with self.assertRaisesRegex(ValueError, "contact_consent"):
            parse_submission(invalid)


class WaitlistApiTests(unittest.TestCase):
    def test_public_count_submission_and_idempotency(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            env = {"OLIN_MODE": "test", "OLIN_WAITLIST_ENCRYPTION_KEY": generate_encryption_key()}
            with patch.dict(os.environ, env):
                with running_server(tmp.name) as base:
                    initial_status, initial, _ = api_request(base)
                    first_status, first, first_headers = api_request(base, "POST", payload())
                    duplicate_status, duplicate, _ = api_request(base, "POST", payload())
            self.assertEqual(200, initial_status)
            self.assertEqual(0, initial["data"]["applications_received"])
            self.assertEqual((202, 202), (first_status, duplicate_status))
            self.assertEqual(1, first["data"]["applications_received"])
            self.assertEqual(1, duplicate["data"]["applications_received"])
            self.assertEqual("http://127.0.0.1:8001", first_headers["Access-Control-Allow-Origin"])
            self.assertNotIn("ana@banco.mx", json.dumps(first))
            self.assertNotIn("contact_name", json.dumps(first))

    def test_referral_code_is_issued_and_attributed(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            env = {"OLIN_MODE": "test", "OLIN_WAITLIST_ENCRYPTION_KEY": generate_encryption_key()}
            with patch.dict(os.environ, env):
                with running_server(tmp.name) as base:
                    status, first, _ = api_request(base, "POST", payload("first@banco.mx"))
                    code = first["data"]["referral_code"]
                    referred = payload("second@sofom.mx")
                    referred["referral_code"] = code
                    second_status, _, _ = api_request(base, "POST", referred)
                with WaitlistStore(tmp.name) as store:
                    leads = store.list_entries()
            self.assertEqual(202, status)
            self.assertEqual(202, second_status)
            self.assertRegex(code, r"^OLIN-[A-Z0-9]{8}$")
            self.assertEqual(code, next(item["referred_by"] for item in leads if item["email"] == "second@sofom.mx"))

    def test_honeypot_is_silently_discarded(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test"}):
                spam = payload()
                spam["website"] = "https://spam.invalid"
                with running_server(tmp.name) as base:
                    status, response, _ = api_request(base, "POST", spam)
                    _, count, _ = api_request(base)
            self.assertEqual(202, status)
            self.assertEqual("received", response["data"]["status"])
            self.assertEqual(0, count["data"]["applications_received"])

    def test_invalid_email_returns_structured_validation_error(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "test"}):
                with running_server(tmp.name) as base:
                    status, response, _ = api_request(base, "POST", payload("not-an-email"))
            self.assertEqual(422, status)
            self.assertEqual("VALIDATION_ERROR", response["error"]["code"])


if __name__ == "__main__":
    unittest.main()
