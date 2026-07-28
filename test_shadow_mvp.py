"""Contract tests for the locked Olin B2B shadow MVP."""
from __future__ import annotations

import json
import csv
import io
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import replace
from http.server import HTTPServer
from unittest.mock import patch

from olin import server
from olin.scorecard import score_application
from olin.store import ScoringLog
from test_pilot_safety import healthy_app


@contextmanager
def running_server(db_path: str):
    previous_db = server.DB_PATH
    server.DB_PATH = db_path
    httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()
        server.DB_PATH = previous_db


def request(base_url: str, path: str, method: str = "GET", body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Olin-Analyst-Token"] = token
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read(), exc.headers
        finally:
            exc.close()


class ShadowMVPContractTests(unittest.TestCase):
    def test_partner_payload_preserves_real_negative_balances_but_rejects_bad_ratios(self):
        payload = {
            "merchant_name": "Abarrotes con sobregiro",
            "business_type": "abarrotes",
            "requested_mxn": 20_000,
            "bank": {
                "avg_daily_balance_mxn": -1_250,
                "min_daily_balance_mxn": -8_000,
                "deposit_regularity": 0.55,
                "balance_trend_90d": -0.8,
                "verified": False,
            },
        }
        app = server._build_application(payload)
        self.assertEqual(app.bank.avg_daily_balance_mxn, -1_250)
        self.assertEqual(app.bank.min_daily_balance_mxn, -8_000)

        invalid = json.loads(json.dumps(payload))
        invalid["bank"]["deposit_regularity"] = 1.2
        with self.assertRaisesRegex(ValueError, "deposit_regularity"):
            server._build_application(invalid)

    def test_production_rejects_unverified_real_evidence(self):
        app = healthy_app()
        app.bank = replace(
            app.bank, source="agent_stated", verified=False, evidence_reference=""
        )
        app.fmcg = replace(
            app.fmcg, source="receipts", verified=False, evidence_reference=""
        )
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            result = score_application(app)
        self.assertEqual(result.decision.value, "DECLINE")
        self.assertEqual(result.tier, 14)
        self.assertTrue(result.production_blocks)

    def test_production_requires_retrievable_evidence_references(self):
        app = healthy_app()
        app.bank = replace(app.bank, evidence_reference="")
        app.fmcg = replace(app.fmcg, evidence_reference="")
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            result = score_application(app)
        self.assertEqual(result.decision.value, "DECLINE")
        self.assertTrue(
            any("reference" in reason.lower() for reason in result.production_blocks)
        )

    def test_production_submission_requires_shadow_mode_and_consent(self):
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            with self.assertRaisesRegex(ValueError, "case_mode"):
                server._validate_submission_metadata({})
            with self.assertRaisesRegex(ValueError, "consent"):
                server._validate_submission_metadata({"case_mode": "shadow"})
            server._validate_submission_metadata(
                {
                    "case_mode": "shadow",
                    "consent": {
                        "channel": "in_person",
                        "text": "Autorizo la evaluación para el piloto sombra.",
                    },
                    "cohort_id": "shadow_2026_07",
                    "partner_case_reference": "PARTNER-001",
                    "funding_purpose": "inventory",
                    "project_description": "Comprar inventario para el negocio.",
                    "evidence_route": "inventory_led",
                }
            )

    def test_public_merchant_origination_is_disabled(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, {"OLIN_MODE": "demo"}):
                with running_server(tmp.name) as base:
                    get_status, _, _ = request(base, "/solicitar")
                    post_status, _, _ = request(
                        base,
                        "/solicitar",
                        method="POST",
                        body={
                            "merchant_name": "Comercio sintético",
                            "phone": "5512345678",
                            "business_type": "abarrotes",
                            "requested_mxn": 20_000,
                            "consent": "yes",
                        },
                    )
        self.assertEqual(get_status, 410)
        self.assertEqual(post_status, 410)

    def test_case_data_routes_require_authentication_in_production(self):
        token = "shadow-test-token"
        env = {
            "OLIN_MODE": "production",
            "OLIN_ANALYST_TOKEN": token,
            "OLIN_STP_WEBHOOK_SECRET": "shadow-test-webhook",
        }
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, env, clear=False):
                with running_server(tmp.name) as base:
                    root_status, _, _ = request(base, "/")
                    stats_status, _, _ = request(base, "/api/stats")
                    private_apps_status, _, _ = request(base, "/api/apps")
                    apps_status, _, _ = request(base, "/api/apps", token=token)
        self.assertEqual(root_status, 200)
        self.assertEqual(stats_status, 401)
        self.assertEqual(private_apps_status, 401)
        self.assertEqual(apps_status, 200)

    def test_shadow_case_cannot_disburse(self):
        token = "shadow-test-token"
        env = {
            "OLIN_MODE": "production",
            "OLIN_ANALYST_TOKEN": token,
            "OLIN_STP_WEBHOOK_SECRET": "shadow-test-webhook",
        }
        app = healthy_app()
        with patch.dict(os.environ, env, clear=False):
            result = score_application(app)
            with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
                with ScoringLog(tmp.name) as log:
                    log.log(app, result)
                    log.record_consent(
                        app.application_id,
                        "in_person",
                        "Autorizo la evaluación para el piloto sombra.",
                    )
                    log.conn.execute(
                        "UPDATE scoring_log SET case_mode='shadow' WHERE application_id=?",
                        (app.application_id,),
                    )
                    log.conn.commit()
                    log.record_analyst_decision(
                        app.application_id, "APPROVE", "Aprobación de prueba"
                    )
                with running_server(tmp.name) as base:
                    status, payload, _ = request(
                        base,
                        f"/api/apps/{app.application_id}/disburse",
                        method="POST",
                        body={},
                        token=token,
                    )
                with ScoringLog(tmp.name) as log:
                    disbursed = log.conn.execute(
                        "SELECT disbursed FROM scoring_log WHERE application_id=?",
                        (app.application_id,),
                    ).fetchone()[0]
        self.assertEqual(status, 403)
        self.assertIn("shadow", json.loads(payload)["error"].lower())
        self.assertEqual(disbursed, 0)

    def test_partner_agreement_is_only_binary_for_binary_engine_routes(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                outcome = log.record_partner_outcome(
                    app.application_id, "approved", "Partner approved the case"
                )
        self.assertEqual(result.decision.value, "AUTO_APPROVE")
        self.assertEqual(outcome["recommendation_agreement"], 1)

    def test_authenticated_partner_can_complete_shadow_case_loop(self):
        token = "partner-test-token"
        env = {
            "OLIN_MODE": "production",
            "OLIN_API_KEYS": json.dumps({"monex_test": token}),
            "OLIN_STP_WEBHOOK_SECRET": "shadow-test-webhook",
        }
        payload = {
            "merchant_name": "Abarrotes Piloto Uno",
            "business_type": "abarrotes",
            "business_description": "Tienda de barrio con venta diaria.",
            "funding_purpose": "inventory",
            "project_description": "Comprar inventario de alta rotación.",
            "evidence_route": "inventory_led",
            "requested_mxn": 20_000,
            "colonia": "Iztapalapa",
            "case_mode": "shadow",
            "cohort_id": "shadow_2026_07",
            "partner_case_reference": "PARTNER-001",
            "consent": {
                "channel": "in_person",
                "text": "Autorizo la evaluación para el piloto sombra.",
            },
            "bank": {
                "months_connected": 3,
                "avg_daily_balance_mxn": 22_000,
                "min_daily_balance_mxn": 9_000,
                "monthly_deposit_count": 24,
                "monthly_deposit_volume_mxn": 95_000,
                "monthly_outflow_volume_mxn": 52_000,
                "deposit_regularity": 0.88,
                "overdrafts_90d": 0,
                "balance_trend_90d": 0.10,
                "source": "partner_api",
                "verified": True,
                "evidence_reference": "BANK-001",
            },
            "fmcg": {
                "months_of_history": 18,
                "weekly_purchase_rate": 0.96,
                "missed_weeks_last_12": 0,
                "avg_weekly_purchase_mxn": 8_500,
                "distributor_confirmed": True,
                "trend_3m": 0.15,
                "source": "distributor_export",
                "verified": True,
                "evidence_reference": "FMCG-001",
            },
            "tenure": {
                "years_on_google_maps": 8,
                "years_in_imss": 5,
                "address_consistent": True,
            },
            "maps": {"rating": 4.6, "review_count": 100, "review_velocity_6m": 8},
            "buro": {
                "checked": True,
                "active_delinquencies": 0,
                "active_loans_count": 1,
                "worst_mob_status": "01",
                "score": 720,
            },
            "fraud": {
                "phone_mx": "5512345678",
                "rfc": "CHGU850101AB2",
                "curp": "",
                "ine_checked": True,
                "address_stated": "Iztapalapa Centro",
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, env, clear=False):
                with running_server(tmp.name) as base:
                    intake_status, intake_html, _ = request(base, "/nuevo", token=token)
                    create_status, created_raw, _ = request(
                        base, "/api/applications", "POST", payload, token
                    )
                    created = json.loads(created_raw)
                    app_id = created["application_id"]
                    list_status, listed_raw, _ = request(base, "/api/apps", token=token)
                    outcome_status, _, _ = request(
                        base,
                        f"/api/apps/{app_id}/outcome",
                        "POST",
                        {
                            "partner_decision": "approved",
                            "partner_reason": "Capacidad confirmada por el socio",
                        },
                        token,
                    )
                    export_status, export_raw, _ = request(
                        base, "/api/export", token=token
                    )
            listed = json.loads(listed_raw)
            exported = list(csv.DictReader(io.StringIO(export_raw.decode("utf-8-sig"))))
            with ScoringLog(tmp.name) as log:
                audit = log.conn.execute(
                    "SELECT event_type,actor FROM audit_event "
                    "WHERE application_id=? ORDER BY occurred_at",
                    (app_id,),
                ).fetchall()

        self.assertEqual(intake_status, 200)
        self.assertIn(b"Crear expediente sombra", intake_html)
        self.assertEqual(create_status, 201)
        self.assertEqual(list_status, 200)
        self.assertEqual(listed[0]["case_mode"], "shadow")
        self.assertEqual(listed[0]["cohort_id"], "shadow_2026_07")
        self.assertEqual(outcome_status, 200)
        self.assertEqual(export_status, 200)
        self.assertEqual(exported[0]["partner_case_reference"], "PARTNER-001")
        self.assertEqual(exported[0]["partner_decision"], "approved")
        self.assertEqual(
            audit,
            [
                ("case_scored", "olin_engine"),
                ("consent_recorded", "monex_test"),
                ("partner_decision_recorded", "monex_test"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
