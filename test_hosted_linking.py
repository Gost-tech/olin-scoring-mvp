"""Black-box tests for the pre-scoring hosted bank-linking state machine."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.bank_ingestion import canonical_json, sign_payload
from olin.store import ScoringLog
from scripts.bank_acceptance_test import _request
from test_shadow_mvp import running_server


USERS = {
    "bank_a": {"token": "partner-a-token", "role": "partner"},
    "bank_b": {"token": "partner-b-token", "role": "partner"},
    "analyst": {"token": "analyst-token", "role": "analyst"},
    "admin": {"token": "admin-token", "role": "admin"},
}
SECRET = "hosted-linking-secret-32-characters-minimum"


def intake_body(reference: str) -> dict:
    return {
        "partner_case_reference": reference,
        "cohort_id": "hosted_linking_uat",
        "merchant_name": "Comercio Linking Sandbox",
    }


def scoring_body() -> dict:
    return {
        "business_type": "abarrotes",
        "business_description": "Tienda de barrio con ventas diarias.",
        "funding_purpose": "inventory",
        "project_description": "Compra de inventario de alta rotación.",
        "requested_mxn": 20_000,
        "colonia": "Iztapalapa",
        "tenure": {"years_on_google_maps": 5, "years_in_imss": 2,
                   "address_consistent": True},
        "buro": {"checked": True, "active_delinquencies": 0,
                 "active_loans_count": 1, "worst_mob_status": "01", "score": 700,
                 "source": "partner_bureau", "verified": True,
                 "evidence_reference": "BUREAU-UAT-001"},
        "fraud": {"phone_mx": "5500000000", "rfc": "UAT850101AB1", "curp": "",
                  "ine_checked": True, "address_stated": "Iztapalapa, CDMX"},
    }


def callback(intake_id: str, consent_id: str, session_id: str, event_id: str) -> dict:
    return {
        "event_id": event_id,
        "intake_id": intake_id,
        "link_session_id": session_id,
        "provider": "partner-bank-sandbox",
        "connection_id": "hosted-link-connection-001",
        "consent_id": consent_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "months_connected": 8, "avg_daily_balance_mxn": 17_000,
            "monthly_deposit_count": 23, "monthly_deposit_volume_mxn": 82_000,
            "monthly_outflow_volume_mxn": 56_000, "deposit_regularity": 0.84,
            "overdrafts_90d": 0, "balance_trend_90d": 0.05,
            "min_daily_balance_mxn": 3_900,
        },
    }


class HostedLinkingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        with ScoringLog(self.tmp.name):
            pass
        self.env = {
            "OLIN_MODE": "production", "OLIN_USERS": json.dumps(USERS),
            "OLIN_BANK_WEBHOOK_SECRET": SECRET, "OLIN_LIVE_LENDING_ENABLED": "0",
            "OLIN_RATE_LIMIT_PER_MINUTE": "500",
            # This legacy suite isolates bank-linking behavior. Consent Flow v1 has
            # separate production-default tests in test_consent_flow.py.
            "OLIN_ALLOW_LEGACY_CONSENT": "1",
        }

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_hosted_linking_converts_one_intake_into_one_scored_case(self):
        with patch.dict(os.environ, self.env), running_server(self.tmp.name) as base:
            status, created = _request(
                base, "/api/v1/intakes", "POST", intake_body("LINK-UAT-001"),
                token="partner-a-token",
            )
            self.assertEqual(201, status)
            intake_id = created["data"]["intake_id"]

            status, _ = _request(
                base, f"/api/v1/intakes/{intake_id}", token="partner-b-token"
            )
            self.assertEqual(404, status)
            status, _ = _request(
                base, f"/api/v1/intakes/{intake_id}/score", "POST", scoring_body(),
                token="partner-a-token",
            )
            self.assertEqual(422, status)

            status, consent = _request(
                base, f"/api/v1/intakes/{intake_id}/consents", "POST",
                {"channel": "in_person", "policy_version": "hosted-v1",
                 "text": "Autorizo el enlace bancario y la evaluación crediticia del piloto sombra."},
                token="partner-a-token",
            )
            self.assertEqual(201, status)
            consent_id = consent["data"]["consent_id"]

            status, session = _request(
                base, f"/api/v1/intakes/{intake_id}/link-sessions", "POST",
                {"provider": "partner-bank-sandbox", "ttl_minutes": 15},
                token="partner-a-token",
            )
            self.assertEqual(201, status)
            session_data = session["data"]
            client_token = session_data["client_token"]
            with ScoringLog(self.tmp.name) as log:
                stored_hash = log.conn.execute(
                    "SELECT token_sha256 FROM intake_link_session WHERE link_session_id=?",
                    (session_data["link_session_id"],),
                ).fetchone()[0]
            self.assertEqual(hashlib.sha256(client_token.encode()).hexdigest(), stored_hash)
            self.assertNotEqual(client_token, stored_hash)

            status, launched = _request(
                base, "/api/v1/link-sessions/exchange", "POST",
                {"client_token": client_token},
            )
            self.assertEqual(200, status)
            self.assertEqual(session_data["link_session_id"], launched["data"]["link_session_id"])
            status, _ = _request(
                base, "/api/v1/link-sessions/exchange", "POST",
                {"client_token": client_token},
            )
            self.assertEqual(401, status)

            event = callback(
                intake_id, consent_id, session_data["link_session_id"], "hosted-event-001"
            )
            signature = sign_payload(canonical_json(event), SECRET)
            status, accepted = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", event,
                signature=signature,
            )
            self.assertEqual(201, status)
            self.assertFalse(accepted["data"]["duplicate"])
            status, replay = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", event,
                signature=signature,
            )
            self.assertEqual(200, status)
            self.assertTrue(replay["data"]["duplicate"])

            conflicting_event = dict(event)
            conflicting_event["connection_id"] = "different-connection"
            status, conflict = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", conflicting_event,
                signature=sign_payload(canonical_json(conflicting_event), SECRET),
            )
            self.assertEqual(409, status)
            self.assertEqual("IDEMPOTENCY_CONFLICT", conflict["error"]["code"])

            status, view = _request(
                base, f"/api/v1/intakes/{intake_id}", token="partner-a-token"
            )
            self.assertEqual(200, status)
            self.assertEqual("evidence_ready", view["data"]["status"])
            self.assertNotIn(client_token, json.dumps(view))

            status, scored = _request(
                base, f"/api/v1/intakes/{intake_id}/score", "POST", scoring_body(),
                token="partner-a-token",
            )
            self.assertEqual(201, status)
            application_id = scored["data"]["application_id"]
            self.assertEqual(intake_id, scored["data"]["intake_id"])
            status, _ = _request(
                base, f"/api/v1/intakes/{intake_id}/score", "POST", scoring_body(),
                token="partner-a-token",
            )
            self.assertEqual(422, status)
            status, case = _request(
                base, f"/api/applications/{application_id}", token="partner-a-token"
            )
            self.assertEqual(200, status)
            self.assertEqual("partner-bank-sandbox", case["evidence"]["bank"]["source"])

        with ScoringLog(self.tmp.name) as log:
            state = log.conn.execute(
                "SELECT status,scored_application_id FROM intake WHERE intake_id=?",
                (intake_id,),
            ).fetchone()
            consent_text = log.conn.execute(
                "SELECT consent_text FROM scoring_log WHERE application_id=?",
                (application_id,),
            ).fetchone()[0]
        self.assertEqual(("scored", application_id), state)
        self.assertTrue(consent_text.startswith("sha256:"))

    def test_withdrawal_cancels_link_and_blocks_callback(self):
        with patch.dict(os.environ, self.env), running_server(self.tmp.name) as base:
            _, created = _request(
                base, "/api/v1/intakes", "POST", intake_body("LINK-UAT-002"),
                token="partner-a-token",
            )
            intake_id = created["data"]["intake_id"]
            _, consent = _request(
                base, f"/api/v1/intakes/{intake_id}/consents", "POST",
                {"channel": "sms", "policy_version": "hosted-v1",
                 "text": "Autorizo el enlace bancario para esta evaluación controlada."},
                token="partner-a-token",
            )
            consent_id = consent["data"]["consent_id"]
            _, session = _request(
                base, f"/api/v1/intakes/{intake_id}/link-sessions", "POST",
                {"provider": "partner-bank-sandbox"}, token="partner-a-token",
            )
            session_id = session["data"]["link_session_id"]
            status, _ = _request(
                base, f"/api/v1/intakes/{intake_id}/consents/{consent_id}/withdraw",
                "POST", {"reason": "Merchant withdrew authorization"},
                token="partner-a-token",
            )
            self.assertEqual(201, status)
            event = callback(intake_id, consent_id, session_id, "hosted-event-002")
            status, _ = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", event,
                signature=sign_payload(canonical_json(event), SECRET),
            )
            self.assertEqual(401, status)
            _, view = _request(
                base, f"/api/v1/intakes/{intake_id}", token="partner-a-token"
            )
            self.assertEqual("created", view["data"]["status"])
            self.assertEqual("withdrawn", view["data"]["consent"]["status"])


if __name__ == "__main__":
    unittest.main()
