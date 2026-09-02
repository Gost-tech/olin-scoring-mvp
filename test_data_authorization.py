from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.cases import validate_submission_metadata
from olin.api.synthetic import seed_synthetic_demo
from olin.store import ScoringLog
from test_product_mvp import partner_payload


def authorization() -> dict[str, str]:
    return {
        "basis_label": "bank_documented_instruction",
        "approval_reference": "BANK-PRIVACY-TICKET-204",
        "approved_by": "bank_privacy_owner",
        "approved_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "scope_sha256": sha256(b"approved-pilot-scope-v1").hexdigest(),
    }


class DataAuthorizationTests(unittest.TestCase):
    def test_historical_case_records_authorization_without_fake_consent(self):
        body = partner_payload()
        body.pop("consent")
        body["data_authorization"] = authorization()
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            validate_submission_metadata(body)

    def test_hosted_verified_consent_does_not_require_duplicate_consent_body(self):
        body = partner_payload()
        body.pop("consent")
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            validate_submission_metadata(body, verified_consent=True)

    def test_invalid_or_future_authorization_is_rejected(self):
        body = partner_payload()
        body.pop("consent")
        body["data_authorization"] = authorization()
        body["data_authorization"]["approved_at"] = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            with self.assertRaisesRegex(ValueError, "past timezone-aware"):
                validate_submission_metadata(body)

    def test_authorization_has_its_own_audit_record(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            case = seed_synthetic_demo(tmp.name)[0]
            with ScoringLog(tmp.name) as log:
                recorded = log.record_data_authorization(
                    case["application_id"], authorization(), "bank_ingestion"
                )
                listed = log.list_data_authorizations(case["application_id"])
                audit = log.conn.execute(
                    "SELECT event_type FROM audit_event WHERE application_id=? "
                    "AND event_type='data_authorization_recorded'",
                    (case["application_id"],),
                ).fetchall()
        self.assertEqual(recorded["authorization_id"], listed[0]["authorization_id"])
        self.assertEqual(1, len(audit))


if __name__ == "__main__":
    unittest.main()
