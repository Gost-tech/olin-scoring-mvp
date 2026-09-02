import os
import tempfile
import unittest
from unittest.mock import patch

from olin.api.cases import create_case, evidence_layers, get_case
from olin.config import default_db_path, is_production, live_lending_enabled, runtime_mode
from olin.places import _address_consistent, lookup_place
from pathlib import Path


class GooglePlacesEvidenceTests(unittest.TestCase):
    def test_neighborhood_match_does_not_hide_street_number_conflict(self):
        self.assertFalse(_address_consistent(
            "Avenida Coyoacán 1535, Del Valle, CDMX",
            "Primera Cerrada Adolfo Prieto 28, Del Valle, CDMX",
        ))

    def test_lookup_preserves_provenance_without_inventing_tenure(self):
        search = {"id": "places/abc123"}
        details = {
            "displayName": {"text": "Café Real"},
            "formattedAddress": "Avenida Coyoacán 1535, Del Valle, CDMX",
            "rating": 4.7,
            "userRatingCount": 140,
            "reviews": [],
            "businessStatus": "OPERATIONAL",
            "primaryType": "cafe",
            "location": {"latitude": 19.38, "longitude": -99.17},
            "googleMapsUri": "https://maps.google.com/example",
        }
        with patch("olin.places._search_place", return_value=search), patch(
            "olin.places._get_place_details", return_value=details
        ):
            evidence = lookup_place("Café Real, Avenida Coyoacán 1535, CDMX")

        self.assertEqual(evidence["provider"], "google_places")
        self.assertEqual(evidence["maps"]["evidence_reference"], "places/abc123")
        self.assertTrue(evidence["maps"]["verified"])
        self.assertEqual(evidence["maps"]["business_status"], "OPERATIONAL")
        self.assertEqual(evidence["tenure"]["years_on_google_maps"], 0.0)
        self.assertEqual(
            evidence["persistable"],
            {
                "source": "google_places",
                "verified": True,
                "evidence_reference": "places/abc123",
                "observed_at": evidence["observed_at"],
            },
        )
        self.assertIn("lower bound", evidence["limitations"][0])


class PilotModeTests(unittest.TestCase):
    def test_pilot_is_fail_closed_and_cannot_move_money(self):
        with patch.dict(
            os.environ,
            {"OLIN_MODE": "pilot", "OLIN_LIVE_LENDING_ENABLED": "true"},
            clear=False,
        ):
            self.assertEqual(runtime_mode(), "pilot")
            self.assertTrue(is_production())
            self.assertFalse(live_lending_enabled())
            self.assertEqual(default_db_path(Path("/tmp")).name, "olin_pilot.db")


class SixLayerEvidenceTests(unittest.TestCase):
    def _body(self):
        return {
            "merchant_name": "Café Real",
            "business_type": "restaurant",
            "requested_mxn": 50_000,
            "colonia": "Del Valle",
            "case_mode": "shadow",
            "cohort_id": "piloto_real_2026_08",
            "partner_case_reference": "REAL-001",
            "funding_purpose": "equipment",
            "project_description": "Comprar una licuadora industrial.",
            "evidence_route": "tpv_led",
            "consent": {"channel": "in_person", "text": "Texto autorizado"},
            "fraud": {
                "phone_mx": "5580076286",
                "rfc": "RUZJ900101ABC",
                "ine_checked": True,
                "address_stated": "Avenida Coyoacán 1535",
            },
            "buro": {"checked": True, "score": 680, "source": "partner_bureau",
                     "verified": True, "evidence_reference": "BUREAU-REAL-001"},
            "pos": {
                "months_of_history": 12,
                "avg_monthly_volume_mxn": 125_000,
                "volume_consistency": 0.9,
                "trend_3m": 0.05,
                "source": "pos_settlement",
                "verified": True,
                "evidence_reference": "TPV-REAL-001",
            },
            "maps": {
                "rating": 4.7,
                "review_count": 140,
                "review_velocity_6m": 2,
                "source": "google_places",
                "verified": True,
                "evidence_reference": "places/abc123",
                "observed_at": "2026-08-07T12:00:00+00:00",
                "display_name": "Café Real",
                "business_status": "OPERATIONAL",
                "latitude": 19.38,
                "longitude": -99.17,
            },
            "tenure": {
                "years_on_google_maps": 2.0,
                "years_in_imss": 0,
                "address_consistent": True,
            },
        }

    def test_layers_are_separate_from_decision_score(self):
        layers = evidence_layers(self._body(), consent_recorded=True)
        by_key = {layer["key"]: layer for layer in layers}
        self.assertEqual(len(layers), 6)
        self.assertEqual(by_key["identity_consent"]["status"], "verified")
        self.assertEqual(by_key["pos_settlements"]["status"], "verified")
        self.assertEqual(by_key["geo_continuity"]["status"], "verified")
        self.assertEqual(by_key["bank_cash_flow"]["status"], "missing")

    def test_geo_layer_requires_address_match(self):
        body = self._body()
        body["tenure"]["address_consistent"] = False
        layers = evidence_layers(body, consent_recorded=True)
        geo = next(layer for layer in layers if layer["key"] == "geo_continuity")
        self.assertEqual(geo["status"], "available")

    def test_real_place_metadata_is_persisted_in_case(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db.close()
        try:
            with patch.dict(os.environ, {"OLIN_MODE": "demo"}, clear=False):
                created = create_case(self._body(), db.name, actor="partner_real")
                case = get_case(db.name, created["application_id"])
            self.assertEqual(
                case["evidence"]["maps"]["evidence_reference"],
                "places/abc123",
            )
            self.assertEqual(len(case["evidence_layers"]), 6)
        finally:
            os.unlink(db.name)


if __name__ == "__main__":
    unittest.main()
