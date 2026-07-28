"""End-to-end contracts for the case → evidence → recommendation → outcome MVP."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.cases import get_case, list_cases
from olin.api.synthetic import seed_synthetic_demo
from olin.store import ScoringLog
from test_shadow_mvp import request, running_server


def partner_payload() -> dict:
    return {
        "merchant_name": "Abarrotes Piloto Seguro",
        "business_type": "abarrotes",
        "business_description": "Tienda de barrio con venta diaria.",
        "funding_purpose": "inventory",
        "project_description": (
            "Comprar inventario de alta rotación para cuatro semanas."
        ),
        "evidence_route": "inventory_led",
        "requested_mxn": 20_000,
        "colonia": "Iztapalapa",
        "case_mode": "shadow",
        "cohort_id": "shadow_2026_07",
        "partner_case_reference": "SOCIO-001",
        "consent": {
            "channel": "in_person",
            "text": "Autorizo la evaluación para el piloto sombra.",
        },
        "bank": {
            "months_connected": 12,
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
            "source": "partner_api",
            "verified": True,
            "evidence_reference": "FMCG-001",
        },
        "tenure": {
            "years_on_google_maps": 8,
            "years_in_imss": 5,
            "address_consistent": True,
        },
        "maps": {
            "rating": 4.6,
            "review_count": 100,
            "review_velocity_6m": 8,
        },
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
            "address_stated": "Iztapalapa, CDMX",
        },
    }


class ProductMVPTests(unittest.TestCase):
    def test_three_synthetic_cases_use_real_engine_and_isolated_metadata(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "demo"}, clear=False):
                created = seed_synthetic_demo(tmp.name)
                queued = list_cases(tmp.name)
        self.assertEqual(len(created), 3)
        self.assertEqual(
            {item["decision"] for item in created},
            {"AUTO_APPROVE", "COMMITTEE", "DECLINE"},
        )
        self.assertTrue(all(item["case_mode"] == "shadow" for item in queued))
        self.assertTrue(all(item["is_demo"] == 1 for item in queued))
        self.assertTrue(
            all(item["data_sources"]["bank"] == "synthetic" for item in queued)
        )

    def test_canonical_case_shape_exposes_evidence_recommendation_and_outcome(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.dict(os.environ, {"OLIN_MODE": "demo"}, clear=False):
                created = seed_synthetic_demo(tmp.name)
                case = get_case(tmp.name, created[2]["application_id"])
        self.assertIsNotNone(case)
        assert case is not None
        self.assertIn("evidence", case)
        self.assertEqual(case["recommendation"], "DECLINE")
        self.assertEqual(case["partner_outcome"]["decision"], "declined")
        self.assertEqual(case["pilot"]["case_mode"], "shadow")

    def test_minimal_roles_complete_the_real_shadow_workflow(self):
        users = {
            "captura": {"token": "partner-token", "role": "partner"},
            "otro_socio": {"token": "other-partner-token", "role": "partner"},
            "analista": {"token": "analyst-token", "role": "analyst"},
            "admin": {"token": "admin-token", "role": "admin"},
        }
        env = {
            "OLIN_MODE": "production",
            "OLIN_USERS": json.dumps(users),
            "OLIN_STP_WEBHOOK_SECRET": "webhook-secret",
        }
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            with patch.dict(os.environ, env, clear=True):
                with running_server(tmp.name) as base:
                    create_status, raw, _ = request(
                        base,
                        "/api/applications",
                        "POST",
                        partner_payload(),
                        "partner-token",
                    )
                    application_id = json.loads(raw)["application_id"]
                    partner_export, _, _ = request(
                        base, "/api/export", token="partner-token"
                    )
                    analyst_create, _, _ = request(
                        base,
                        "/api/applications",
                        "POST",
                        partner_payload(),
                        "analyst-token",
                    )
                    analyst_list, _, _ = request(
                        base, "/api/apps", token="analyst-token"
                    )
                    other_payload = partner_payload()
                    other_payload["partner_case_reference"] = "OTRO-001"
                    other_status, other_raw, _ = request(
                        base,
                        "/api/applications",
                        "POST",
                        other_payload,
                        "other-partner-token",
                    )
                    other_id = json.loads(other_raw)["application_id"]
                    partner_list_status, partner_list_raw, _ = request(
                        base, "/api/apps", token="partner-token"
                    )
                    partner_case_ids = {
                        item["application_id"]
                        for item in json.loads(partner_list_raw)
                    }
                    hidden_status, _, _ = request(
                        base,
                        f"/api/applications/{other_id}",
                        token="partner-token",
                    )
                    outcome_status, _, _ = request(
                        base,
                        f"/api/apps/{application_id}/outcome",
                        "POST",
                        {
                            "partner_decision": "approved",
                            "partner_reason": "Capacidad confirmada por la institución",
                        },
                        "analyst-token",
                    )
                    shadow_disburse, _, _ = request(
                        base,
                        f"/api/apps/{application_id}/disburse",
                        "POST",
                        {},
                        "admin-token",
                    )
        self.assertEqual(create_status, 201)
        self.assertEqual(partner_export, 403)
        self.assertEqual(analyst_create, 403)
        self.assertEqual(analyst_list, 200)
        self.assertEqual(other_status, 201)
        self.assertEqual(partner_list_status, 200)
        self.assertNotIn(other_id, partner_case_ids)
        self.assertEqual(hidden_status, 404)
        self.assertEqual(outcome_status, 200)
        self.assertEqual(shadow_disburse, 403)


if __name__ == "__main__":
    unittest.main()
