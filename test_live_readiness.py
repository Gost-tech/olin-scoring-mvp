from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.synthetic import seed_synthetic_demo
from olin.bank_ingestion import (
    canonical_json,
    ingest_verified_metrics,
    normalize_payload,
    sign_payload,
)
from olin.store import ScoringLog
from olin.synthetic_portfolio import generate
from olin.readiness import readiness
from scripts.simulate_bank_callback import callback_payload, safe_endpoint
from test_shadow_mvp import request, running_server


class GovernanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.created = seed_synthetic_demo(self.tmp.name)
        self.app_id = self.created[0]["application_id"]

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_consent_is_hashed_versioned_and_withdrawable(self):
        with ScoringLog(self.tmp.name) as log:
            original = log.list_consents(self.app_id)
            self.assertEqual(1, len(original))
            self.assertEqual("active", original[0]["status"])
            self.assertNotIn("Autorizo", json.dumps(original))
            log.record_consent(
                self.app_id, "sms", "Autorizo una nueva consulta para el piloto.", "partner_a"
            )
            records = log.list_consents(self.app_id)
            self.assertEqual(["active", "superseded"], [row["status"] for row in records])
            withdrawn = log.withdraw_consent(
                self.app_id, records[0]["consent_id"], "Solicitud del titular", "partner_a"
            )
            self.assertEqual("withdrawn", withdrawn["status"])
            legacy = log.conn.execute(
                "SELECT consent_timestamp FROM scoring_log WHERE application_id=?", (self.app_id,)
            ).fetchone()
            self.assertIsNone(legacy[0])

    def test_correction_preserves_original_and_requires_rescore(self):
        with ScoringLog(self.tmp.name) as log:
            raw_before = log.conn.execute(
                "SELECT raw_application FROM scoring_log WHERE application_id=?", (self.app_id,)
            ).fetchone()[0]
            opened = log.create_correction_request(
                self.app_id, "bank.monthly_deposit_count", 31,
                "El banco confirmó el conteo correcto", "partner_a",
            )
            resolved = log.resolve_correction_request(
                self.app_id, opened["request_id"], "accepted",
                "Documento revisado y aceptado", "analyst_a",
            )
            self.assertTrue(resolved["requires_rescore"])
            raw_after = log.conn.execute(
                "SELECT raw_application FROM scoring_log WHERE application_id=?", (self.app_id,)
            ).fetchone()[0]
            self.assertEqual(raw_before, raw_after)


class BankIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        created = seed_synthetic_demo(self.tmp.name)
        self.app_id = created[0]["application_id"]
        with ScoringLog(self.tmp.name) as log:
            self.consent_id = log.list_consents(self.app_id)[0]["consent_id"]
        self.payload = {
            "event_id": "bank-event-001",
            "application_id": self.app_id,
            "provider": "partner-bank-sandbox",
            "connection_id": "connection-test-001",
            "consent_id": self.consent_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "months_connected": 6,
                "avg_daily_balance_mxn": 15000,
                "monthly_deposit_count": 21,
                "monthly_deposit_volume_mxn": 75000,
                "monthly_outflow_volume_mxn": 51000,
                "deposit_regularity": 0.82,
                "overdrafts_90d": 0,
                "balance_trend_90d": 0.04,
                "min_daily_balance_mxn": 3200,
            },
        }

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_signed_metrics_are_consent_bound_and_idempotent(self):
        raw = canonical_json(self.payload)
        signature = sign_payload(raw, "test-secret")
        first = ingest_verified_metrics(
            self.tmp.name, self.payload, raw, signature, "test-secret"
        )
        second = ingest_verified_metrics(
            self.tmp.name, self.payload, raw, signature, "test-secret"
        )
        self.assertTrue(first["bank"]["verified"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        with ScoringLog(self.tmp.name) as log:
            stored = log.list_bank_evidence(self.app_id)
        self.assertEqual(1, len(stored))
        self.assertEqual(75000, stored[0]["bank"]["monthly_deposit_volume_mxn"])
        self.assertNotIn("transactions", json.dumps(stored))

    def test_raw_transactions_and_credentials_are_rejected(self):
        for forbidden in ({"transactions": []}, {"credentials": {"password": "x"}}):
            payload = dict(self.payload)
            payload.update(forbidden)
            with self.assertRaises(ValueError):
                normalize_payload(payload)

    def test_withdrawn_consent_blocks_ingestion(self):
        with ScoringLog(self.tmp.name) as log:
            log.withdraw_consent(
                self.app_id, self.consent_id, "Solicitud del titular", "partner_a"
            )
        raw = canonical_json(self.payload)
        with self.assertRaises(PermissionError):
            ingest_verified_metrics(
                self.tmp.name, self.payload, raw, sign_payload(raw, "secret"), "secret"
            )


class SyntheticPortfolioTests(unittest.TestCase):
    def test_report_is_repeatable_and_clearly_non_predictive(self):
        first = generate(90, seed=7)
        second = generate(90, seed=7)
        self.assertEqual(first, second)
        self.assertTrue(first["passed"])
        self.assertEqual("synthetic_software_validation", first["kind"])
        self.assertIn("do not estimate default rates", first["limitations"][0])


class GovernanceApiTests(unittest.TestCase):
    def test_http_consent_and_correction_lifecycle(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            created = seed_synthetic_demo(tmp.name)
            app_id = created[0]["application_id"]
            users = json.dumps({
                "partner_test": {"token": "partner-secret", "role": "partner"},
                "analyst_test": {"token": "analyst-secret", "role": "analyst"},
                "admin_test": {"token": "admin-secret", "role": "admin"},
            })
            env = {
                "OLIN_MODE": "production",
                "OLIN_USERS": users,
                "OLIN_BANK_WEBHOOK_SECRET": "r" * 32,
                "OLIN_LIVE_LENDING_ENABLED": "0",
            }
            with patch.dict(os.environ, env):
                with running_server(tmp.name) as base:
                    ready_status, ready_raw, _ = request(base, "/readyz")
                    status, raw, _ = request(
                        base, f"/api/v1/cases/{app_id}/corrections", "POST",
                        {"field_path": "bank.monthly_deposit_count", "claimed_value": 31,
                         "reason": "Conteo confirmado por banco"}, "admin-secret",
                    )
                    opened = json.loads(raw)["data"]
                    resolve_status, resolved_raw, _ = request(
                        base,
                        f"/api/v1/cases/{app_id}/corrections/{opened['request_id']}/resolve",
                        "POST", {"status": "accepted", "note": "Validación documental completa"},
                        "admin-secret",
                    )
                    list_status, listed_raw, headers = request(
                        base, f"/api/v1/cases/{app_id}/corrections", token="admin-secret"
                    )
            self.assertEqual(201, status)
            self.assertEqual(200, ready_status)
            self.assertTrue(json.loads(ready_raw)["ok"])
            self.assertEqual(201, resolve_status)
            self.assertTrue(json.loads(resolved_raw)["data"]["requires_rescore"])
            self.assertEqual(200, list_status)
            self.assertEqual("accepted", json.loads(listed_raw)["data"][0]["status"])
            self.assertEqual("same-origin", headers["Cross-Origin-Resource-Policy"])


class DeploymentReadinessTests(unittest.TestCase):
    def test_production_readiness_requires_roles_secret_and_no_money(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            users = json.dumps({
                "bank": {"token": "partner-token", "role": "partner"},
                "reviewer": {"token": "analyst-token", "role": "analyst"},
                "operator": {"token": "admin-token", "role": "admin"},
            })
            env = {
                "OLIN_MODE": "production",
                "OLIN_USERS": users,
                "OLIN_BANK_WEBHOOK_SECRET": "x" * 32,
                "OLIN_LIVE_LENDING_ENABLED": "0",
            }
            with patch.dict(os.environ, env, clear=False):
                result = readiness(tmp.name)
        self.assertTrue(result["ok"])
        self.assertEqual([], result["failed"])

    def test_browser_tokens_are_memory_only(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "olin", "server.py"), encoding="utf-8") as handle:
            server_source = handle.read()
        with open(os.path.join(root, "olin", "shadow_intake.html"), encoding="utf-8") as handle:
            intake_source = handle.read()
        self.assertNotIn("sessionStorage", server_source)
        self.assertNotIn("sessionStorage", intake_source)
        self.assertNotIn("localStorage", server_source)
        self.assertNotIn("localStorage", intake_source)

    def test_bank_simulator_is_deterministic_and_tls_safe(self):
        payload = callback_payload("app-123", "consent-123", "event-123")
        self.assertEqual("event-123", payload["event_id"])
        self.assertNotIn("transactions", json.dumps(payload))
        self.assertEqual(
            "http://127.0.0.1:8080/api/v1/webhooks/bank-evidence",
            safe_endpoint("http://127.0.0.1:8080"),
        )
        with self.assertRaises(ValueError):
            safe_endpoint("http://bank.example.com")


if __name__ == "__main__":
    unittest.main()
