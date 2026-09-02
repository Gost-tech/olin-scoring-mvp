from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from olin.production_preflight import production_preflight


class ProductionPreflightTests(unittest.TestCase):
    def test_real_data_fails_closed_when_operational_evidence_is_missing(self):
        env = {
            "OLIN_MODE": "production",
            "OLIN_REAL_DATA_ENABLED": "1",
            "OLIN_DATABASE_URL": "postgresql://db.example/olin",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "olin.production_preflight.production_storage_readiness",
            return_value={"ready": False, "checks": {}},
        ), patch(
            "olin.production_preflight.trust_registry_readiness",
            return_value={"ready": False, "checks": {}},
        ):
            result = production_preflight(env["OLIN_DATABASE_URL"])
        self.assertFalse(result["ok"])
        self.assertIn("postgres_tls", result["failed"])
        self.assertIn("processing_approval_reference", result["failed"])
        self.assertIn("production_storage", result["failed"])

    def test_historical_real_data_passes_when_every_technical_gate_is_recorded(self):
        users = {
            "bank_ingestion": {"token": "p" * 40, "role": "partner"},
            "risk_reviewer": {"token": "r" * 40, "role": "analyst"},
            "olin_operator": {"token": "a" * 40, "role": "admin"},
        }
        env = {
            "OLIN_MODE": "production",
            "OLIN_REAL_DATA_ENABLED": "1",
            "OLIN_DATABASE_URL": "postgresql://db.example/olin?sslmode=verify-full",
            "OLIN_USERS": json.dumps(users),
            "OLIN_BANK_WEBHOOK_SECRET": "w" * 40,
            "OLIN_REQUIRE_SHORT_LIVED_SESSIONS": "1",
            "OLIN_SESSION_SECRET": "s" * 40,
            "OLIN_PUBLIC_BASE_URL": "https://uat.olin.example",
            "OLIN_DATA_CLASSIFICATION": "pseudonymized_historical",
            "OLIN_REAL_DATA_SCOPE_REF": "BANK-TICKET-101",
            "OLIN_DATA_PROCESSING_APPROVAL_REF": "PRIVACY-APPROVAL-202",
            "OLIN_RETENTION_DAYS": "45",
            "OLIN_INCIDENT_OWNER": "olin_on_call",
            "OLIN_INCIDENT_CONTACT": "security@example.invalid",
            "OLIN_LIVE_LENDING_ENABLED": "0",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "olin.production_preflight.production_storage_readiness",
            return_value={"ready": True, "checks": {"postgres_connectivity": True}},
        ), patch(
            "olin.production_preflight.trust_registry_readiness",
            return_value={"ready": True, "checks": {"registry": True}},
        ):
            result = production_preflight(env["OLIN_DATABASE_URL"])
        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed"])

    def test_prospective_data_requires_real_otp_delivery(self):
        users = {
            "bank_ingestion": {"token": "p" * 40, "role": "partner"},
            "risk_reviewer": {"token": "r" * 40, "role": "analyst"},
            "olin_operator": {"token": "a" * 40, "role": "admin"},
        }
        env = {
            "OLIN_MODE": "production",
            "OLIN_REAL_DATA_ENABLED": "1",
            "OLIN_DATABASE_URL": "postgresql://db.example/olin?sslmode=require",
            "OLIN_USERS": json.dumps(users),
            "OLIN_BANK_WEBHOOK_SECRET": "w" * 40,
            "OLIN_REQUIRE_SHORT_LIVED_SESSIONS": "1",
            "OLIN_SESSION_SECRET": "s" * 40,
            "OLIN_PUBLIC_BASE_URL": "https://uat.olin.example",
            "OLIN_DATA_CLASSIFICATION": "prospective",
            "OLIN_REAL_DATA_SCOPE_REF": "BANK-TICKET-101",
            "OLIN_DATA_PROCESSING_APPROVAL_REF": "PRIVACY-APPROVAL-202",
            "OLIN_RETENTION_DAYS": "45",
            "OLIN_INCIDENT_OWNER": "olin_on_call",
            "OLIN_INCIDENT_CONTACT": "security@example.invalid",
            "OLIN_LIVE_LENDING_ENABLED": "0",
            "OLIN_CONSENT_OTP_MODE": "synthetic",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "olin.production_preflight.production_storage_readiness",
            return_value={"ready": True, "checks": {}},
        ), patch(
            "olin.production_preflight.trust_registry_readiness",
            return_value={"ready": True, "checks": {}},
        ):
            result = production_preflight(env["OLIN_DATABASE_URL"])
        self.assertIn("prospective_consent_secret", result["failed"])
        self.assertIn("prospective_delivery_adapter", result["failed"])

    def test_container_does_not_force_real_data_into_sqlite(self):
        source = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn('"--db", "/data/olin_scoring.db"', source)
        self.assertIn("/readyz", source)


if __name__ == "__main__":
    unittest.main()
