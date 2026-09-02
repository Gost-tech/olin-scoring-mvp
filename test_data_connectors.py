from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from olin.bank_statement import analyze_csv
from olin.denue import lookup_business
from olin.places import _search_place
from test_shadow_mvp import request, running_server


CSV = """fecha,monto,saldo,descripcion
2026-05-01,10000,10000,venta
2026-05-03,-2500,7500,renta
2026-05-10,9000,16500,venta
2026-05-15,-3000,13500,proveedor
2026-06-01,11000,24500,venta
2026-06-04,-4000,20500,insumos
2026-06-15,12000,32500,venta
2026-06-20,-5000,27500,nomina
"""


class BankStatementTests(unittest.TestCase):
    def test_csv_returns_metrics_and_hash_without_raw_rows(self):
        result = analyze_csv(CSV)
        self.assertEqual(result["provider"], "bank_statement_csv")
        self.assertFalse(result["bank"]["verified"])
        self.assertFalse(result["summary"]["eligibleForDecision"])
        self.assertTrue(result["bank"]["evidence_reference"].startswith("sha256:"))
        self.assertFalse(result["summary"]["statementStored"])
        self.assertNotIn("venta", json.dumps(result))

    def test_csv_rejects_missing_required_columns(self):
        with self.assertRaisesRegex(ValueError, "requires a date"):
            analyze_csv("foo,bar\n1,2\n")


class DenueTests(unittest.TestCase):
    @patch("olin.denue.requests.get")
    def test_denue_match_preserves_public_reference(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{
            "Id": "12345",
            "CLEE": "09ABC123",
            "Nombre": "Cafe Real",
            "Razon_social": "Cafe Real SA",
            "Clase_actividad": "Cafeterías",
            "Estrato": "0 a 5 personas",
            "Calle": "Avenida Coyoacan",
            "Num_Exterior": "1535",
            "Colonia": "Del Valle",
            "CP": "03100",
            "Ubicacion": "Benito Juarez, Ciudad de Mexico",
            "Latitud": "19.38",
            "Longitud": "-99.17",
        }]
        get.return_value = response
        with patch.dict(os.environ, {"INEGI_DENUE_TOKEN": "test-token"}):
            result = lookup_business(
                "Cafe Real", "Avenida Coyoacan 1535, Del Valle",
                19.38, -99.17,
            )
        self.assertEqual(result["persistable"]["denue_id"], "12345")
        self.assertTrue(result["persistable"]["denue_verified"])
        self.assertEqual(result["bestMatch"]["distanceM"], 0.0)
        self.assertNotIn("test-token", json.dumps(result))


class GoogleRequestTests(unittest.TestCase):
    @patch("olin.places.requests.post")
    def test_google_search_is_mexico_wide_not_hardcoded_to_cdmx(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"places": [{"id": "places/abc"}]}
        post.return_value = response
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"}):
            _search_place("Ferreteria Centro, Merida, Yucatan")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["regionCode"], "MX")
        self.assertNotIn("locationBias", payload)


class ConnectorApiTests(unittest.TestCase):
    def test_provider_status_and_bank_analysis_endpoints(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file, patch.dict(
            os.environ,
            {"OLIN_MODE": "demo", "SYNCFY_API_KEY": "configured"},
            clear=False,
        ):
            with running_server(db_file.name) as base:
                status, raw, headers = request(
                    base,
                    "/api/v1/providers?filter=syncfy&limit=1&offset=0",
                )
                self.assertEqual(status, 200)
                providers = json.loads(raw)["data"]
                self.assertEqual(len(providers), 1)
                self.assertEqual(headers.get("Cache-Control"), "no-store")
                syncfy = next(item for item in providers if item["id"] == "syncfy")
                self.assertTrue(syncfy["configured"])
                self.assertFalse(syncfy["interactiveLinkingReady"])

                status, raw, _ = request(
                    base,
                    "/api/v1/signals/catalog?filter=weather&limit=5&offset=0",
                )
                self.assertEqual(status, 200)
                catalog = json.loads(raw)["data"]
                self.assertEqual(catalog["total_signal_count"], 28)
                self.assertEqual(catalog["signal_count"], 1)
                self.assertEqual(catalog["signals"][0]["signal_id"], "weather_risk")

                status, raw, _ = request(
                    base,
                    "/api/v1/evidence/bank-statements/analyses",
                    "POST",
                    {"csvText": CSV},
                )
                self.assertEqual(status, 201)
                self.assertEqual(
                    json.loads(raw)["data"]["provider"],
                    "bank_statement_csv",
                )

                weather_response = Mock()
                weather_response.raise_for_status.return_value = None
                weather_response.json.return_value = {
                    "daily": {
                        "temperature_2m_max": [30.0] * 30,
                        "temperature_2m_min": [18.0] * 30,
                        "precipitation_sum": [2.0] * 30,
                    }
                }
                with patch("olin.weather.requests.get", return_value=weather_response):
                    status, raw, _ = request(
                        base,
                        "/api/v1/evidence/weather/analyses",
                        "POST",
                        {"latitude": 19.4326, "longitude": -99.1332, "asOfDate": "2026-08-14"},
                    )
                self.assertEqual(status, 201)
                weather = json.loads(raw)["data"]
                self.assertIn("weather_risk", weather["signal_evidence"])

    def test_intake_contains_real_connector_controls(self):
        with open("olin/shadow_intake.html", encoding="utf-8") as intake_file:
            html = intake_file.read()
        self.assertIn('id="analyze-bank-csv"', html)
        self.assertIn('id="lookup-denue"', html)
        self.assertIn("/api/v1/evidence/google-places/lookups", html)
        self.assertEqual(html.count("const statusBox ="), 1)


if __name__ == "__main__":
    unittest.main()
