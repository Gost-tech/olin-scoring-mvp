from __future__ import annotations

import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from olin.geointelligence import analyze_neighborhood, save_snapshot
from olin.models import BusinessType
from test_shadow_mvp import request, running_server


def denue_record(identifier: str, name: str, activity: str, scian: str, lat: float, lon: float) -> dict:
    return {
        "Id": identifier,
        "Nombre": name,
        "Clase_actividad": activity,
        "Id_clase_actividad": scian,
        "Id_sector_actividad": scian[:2],
        "Estrato": "0 a 5 personas",
        "Calle": "Avenida Mercado",
        "Num_Exterior": identifier,
        "Colonia": "Centro",
        "CP": "06000",
        "Ubicacion": "Cuauhtemoc, Ciudad de Mexico",
        "Latitud": str(lat),
        "Longitud": str(lon),
        "Telefono": "must-not-be-returned",
        "Correo_e": "private@example.test",
    }


BASE_ROWS = [
    denue_record("1", "Abarrotes Uno", "Comercio al por menor de abarrotes", "461110", 19.4326, -99.1332),
    denue_record("2", "Abarrotes Dos", "Comercio al por menor de abarrotes", "461110", 19.4330, -99.1332),
    denue_record("3", "Farmacia Centro", "Farmacias sin minisuper", "464111", 19.4335, -99.1332),
    denue_record("4", "Taller Centro", "Reparacion de automoviles", "811111", 19.4350, -99.1332),
]


class GeointelligenceTests(unittest.TestCase):
    def test_all_sme_types_receive_a_market_profile(self):
        for business_type in BusinessType:
            with self.subTest(business_type=business_type.value):
                result = analyze_neighborhood(
                    19.4326, -99.1332, 1_000, business_type.value,
                    raw_records=copy.deepcopy(BASE_ROWS),
                )
                self.assertEqual(result["resultCount"], 4)
                self.assertEqual(result["catchment"]["method"], "radial_not_drive_time")
                self.assertIn("zone_commerce_density", result["signal_evidence"])

    def test_sector_classification_and_data_minimization(self):
        result = analyze_neighborhood(
            19.4326, -99.1332, 1_000, "abarrotes",
            target_scian="461110", raw_records=copy.deepcopy(BASE_ROWS),
        )
        self.assertEqual(result["metrics"]["competitorCount"], 2)
        self.assertEqual(result["metrics"]["complementaryBusinessCount"], 1)
        serialized = json.dumps(result)
        self.assertNotIn("must-not-be-returned", serialized)
        self.assertNotIn("private@example.test", serialized)

    def test_snapshots_create_verified_change_evidence(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file:
            first = analyze_neighborhood(
                19.4326, -99.1332, 1_000, "abarrotes",
                raw_records=copy.deepcopy(BASE_ROWS),
            )
            first = save_snapshot(db_file.name, "bank-a", first)
            self.assertEqual(first["snapshot"]["status"], "baseline_created")
            self.assertNotIn("establishmentIds", first)

            duplicate = analyze_neighborhood(
                19.4326, -99.1332, 1_000, "abarrotes",
                raw_records=copy.deepcopy(BASE_ROWS),
            )
            duplicate = save_snapshot(db_file.name, "bank-a", duplicate)
            self.assertEqual(duplicate["snapshot"]["status"], "unchanged")

            other_partner = analyze_neighborhood(
                19.4326, -99.1332, 1_000, "abarrotes",
                raw_records=copy.deepcopy(BASE_ROWS),
            )
            other_partner = save_snapshot(db_file.name, "bank-b", other_partner)
            self.assertEqual(other_partner["snapshot"]["status"], "baseline_created")
            with closing(sqlite3.connect(db_file.name)) as conn:
                conn.execute(
                    "UPDATE geointelligence_snapshots SET observed_at=? WHERE snapshot_id=?",
                    ("2025-08-20T12:00:00+00:00", first["snapshot"]["snapshotId"]),
                )
                conn.commit()

            changed_rows = copy.deepcopy(BASE_ROWS[1:])
            changed_rows.append(denue_record(
                "5", "Panaderia Nueva", "Panaderia", "311811", 19.4328, -99.1332,
            ))
            second = analyze_neighborhood(
                19.4326, -99.1332, 1_000, "abarrotes", raw_records=changed_rows,
            )
            second = save_snapshot(db_file.name, "bank-a", second)
            self.assertEqual(second["snapshot"]["status"], "compared")
            self.assertEqual(second["snapshot"]["missingEstablishmentCount"], 1)
            self.assertEqual(second["snapshot"]["newEstablishmentCount"], 1)
            self.assertTrue(second["snapshot"]["eligibleForTwelveMonthSignal"])
            self.assertIn("neighborhood_closure_rate", second["signal_evidence"])

    @patch("olin.geointelligence.fetch_nearby", return_value=copy.deepcopy(BASE_ROWS))
    def test_authenticated_http_analysis_returns_attachable_evidence(self, _fetch):
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file:
            with running_server(db_file.name) as base:
                invalid_status, _, _ = request(
                    base,
                    "/api/v1/evidence/geointelligence/analyses",
                    "POST",
                    {"latitude": 19.4326, "longitude": -99.1332},
                )
                self.assertEqual(invalid_status, 422)
                status, raw, headers = request(
                    base,
                    "/api/v1/evidence/geointelligence/analyses",
                    "POST",
                    {
                        "latitude": 19.4326,
                        "longitude": -99.1332,
                        "radiusM": 1_000,
                        "businessType": "healthcare",
                        "targetScian": "464111",
                    },
                )
            self.assertEqual(status, 201)
            self.assertEqual(headers.get("Cache-Control"), "no-store")
            data = json.loads(raw)["data"]
            self.assertIn("snapshotId", data["snapshot"])
            self.assertIn("commercial_neighbor_ecosystem", data["signal_evidence"])
            self.assertNotIn("establishmentIds", data)

    def test_rejects_invalid_scope(self):
        with self.assertRaisesRegex(ValueError, "radiusM"):
            analyze_neighborhood(19.4, -99.1, 10_000, "retail", raw_records=[])
        with self.assertRaisesRegex(ValueError, "businessType"):
            analyze_neighborhood(19.4, -99.1, 500, "spaceship", raw_records=[])


if __name__ == "__main__":
    unittest.main()
