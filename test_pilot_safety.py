"""Regression tests for controls required before Olin's first live pilot."""
from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from olin import alerts
from olin.collection import check_overdue, make_collection_ref, process_incoming_payment
from olin.models import (
    Application, BankData, BuroData, BusinessType, FMCGData, FraudData,
    MapsRatingData, RepaymentAssessment, TenureData,
)
from olin.scorecard import (
    _buro_dim, _dscr_dim, _score_dim, _tier_lookup, score_application,
)
from olin.server import HTML_PAGE
from olin.store import ScoringLog
from olin.stp import DisbursementError, validate_clabe, validate_runtime_environment


VALID_CLABE = "002180700001234569"


def healthy_app() -> Application:
    return Application(
        merchant_name="Pilot Safety Merchant",
        business_type=BusinessType.ABARROTES,
        requested_amount_mxn=20_000,
        colonia="Iztapalapa Centro",
        clabe=VALID_CLABE,
        fmcg=FMCGData(
            months_of_history=18, weekly_purchase_rate=0.95,
            missed_weeks_last_12=0, avg_weekly_purchase_mxn=8_000,
            distributor_confirmed=True, trend_3m=0.1,
            source="distributor", verified=True, evidence_reference="FMCG-001",
        ),
        bank=BankData(
            months_connected=3, avg_daily_balance_mxn=20_000,
            monthly_deposit_count=24, monthly_deposit_volume_mxn=90_000,
            monthly_outflow_volume_mxn=45_000, deposit_regularity=0.9,
            overdrafts_90d=0, balance_trend_90d=0.1,
            min_daily_balance_mxn=8_000, source="syncfy", verified=True,
            evidence_reference="SYNC-001",
        ),
        tenure=TenureData(8, 5, True),
        maps=MapsRatingData(4.6, 100, 8),
        buro=BuroData(True, 0, 1, "01", 720),
        fraud=FraudData(
            phone_mx="5512345678", rfc="CHGU850101AB2",
            ine_checked=True, address_stated="Iztapalapa Centro",
        ),
    )


class PilotSafetyTests(unittest.TestCase):
    def test_analyst_ui_reserves_approved_label_for_analyst_approval(self):
        self.assertIn("const analystApproved = app.analyst_override === 'APPROVE'", HTML_PAGE)
        self.assertIn("'Monto evaluado'", HTML_PAGE)
        self.assertIn("'No aprobado'", HTML_PAGE)
        self.assertNotIn(
            "Aprobado&nbsp;&nbsp; <strong>MXN ${fmt(app.approved_mxn)}</strong>",
            HTML_PAGE,
        )

    def test_circulo_consent_is_migrated_and_recorded(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                columns = {
                    row[1] for row in log.conn.execute("PRAGMA table_info(scoring_log)").fetchall()
                }
                self.assertTrue(
                    {"consent_timestamp", "consent_channel", "consent_text"}.issubset(columns)
                )
                with self.assertRaisesRegex(ValueError, "Consent channel"):
                    log.record_consent(app.application_id, "email", "I consent")
                log.record_consent(app.application_id, "whatsapp", "Acepto consulta Círculo")
                consent = log.conn.execute(
                    "SELECT consent_timestamp,consent_channel,consent_text "
                    "FROM scoring_log WHERE application_id=?",
                    (app.application_id,),
                ).fetchone()
            self.assertTrue(consent[0])
            self.assertEqual(consent[1:], ("whatsapp", "Acepto consulta Círculo"))

    def test_alert_without_email_is_written_to_durable_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "alerts.log"
            with patch.object(alerts, "ENV_PATH", Path(tmpdir) / "missing.env"), \
                 patch.object(alerts, "LOG_PATH", log_path), \
                 patch.dict(os.environ, {"OLIN_ALERT_EMAIL": ""}):
                destination = alerts.send_alert("Pilot alert", "Durable body")
            self.assertEqual(destination, "log")
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("Pilot alert", contents)
            self.assertIn("Durable body", contents)

    def test_clabe_checksum(self):
        self.assertTrue(validate_clabe(VALID_CLABE))
        self.assertFalse(validate_clabe("002180700001234567"))

    def test_demo_and_production_money_rails_cannot_cross(self):
        with patch.dict(os.environ, {"OLIN_MODE": "production", "STP_SANDBOX": "1"}):
            with self.assertRaisesRegex(DisbursementError, "STP_SANDBOX=0"):
                validate_runtime_environment()
        with patch.dict(os.environ, {"OLIN_MODE": "demo", "STP_SANDBOX": "0"}):
            with self.assertRaisesRegex(DisbursementError, "disabled outside"):
                validate_runtime_environment()

    def test_bureau_boundaries_and_missing_score(self):
        cases = [
            (BuroData(False), "C3"),
            (BuroData(True, score=None), "C3"),
            (BuroData(True, score=599), "C4"),
            (BuroData(True, score=600), "C2"),
            (BuroData(True, score=669), "C2"),
            (BuroData(True, score=670), "C1"),
            (BuroData(True, active_delinquencies=1, score=720), "C4"),
        ]
        for bureau, expected in cases:
            with self.subTest(expected=expected, bureau=bureau):
                self.assertEqual(_buro_dim(bureau), expected)

    def test_all_matrix_combinations_resolve(self):
        rows = []
        for bureau in ("C1", "C2", "C3", "C4"):
            for dscr in ("D1", "D2", "D3"):
                for score in ("S1", "S2", "S3"):
                    tier, decision = _tier_lookup(bureau, dscr, score)
                    rows.append((bureau, dscr, score, tier, decision.value))
                    self.assertIn(tier, range(1, 14))
        self.assertEqual(len(rows), 36)

    def test_dimension_boundaries(self):
        def repayment(dscr, hard=None, soft=None):
            return RepaymentAssessment(
                dscr, None, None, None, None, None,
                hard_declines=hard or [], downgrades=soft or [],
            )
        self.assertEqual(_dscr_dim(repayment(1.49)), "D3")
        self.assertEqual(_dscr_dim(repayment(1.50)), "D2")
        self.assertEqual(_dscr_dim(repayment(2.50)), "D1")
        self.assertEqual(_dscr_dim(repayment(2.50, soft=["flag"])), "D2")
        self.assertEqual(_score_dim(49.99), "S3")
        self.assertEqual(_score_dim(50), "S2")
        self.assertEqual(_score_dim(75), "S1")

    def test_production_rejects_mock_underwriting(self):
        app = healthy_app()
        app.bank = replace(app.bank, source="mock_sandbox", verified=False)
        with patch.dict(os.environ, {"OLIN_MODE": "production"}):
            result = score_application(app)
        self.assertEqual(result.decision.value, "DECLINE")
        self.assertEqual(result.tier, 14)
        self.assertEqual(result.approved_amount_mxn, 0)
        self.assertTrue(result.production_blocks)

    def test_engine_decline_has_zero_amount_and_cannot_be_overridden(self):
        app = healthy_app()
        app.buro = BuroData(True, 0, 1, "01", 599)
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        self.assertEqual(result.decision.value, "DECLINE")
        self.assertEqual(result.approved_amount_mxn, 0)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                with self.assertRaisesRegex(ValueError, "non-overridable"):
                    log.record_analyst_decision(app.application_id, "APPROVE", "Override decline")

    def test_duplicate_log_cannot_erase_existing_loan_state(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                ref = make_collection_ref(app.application_id)
                log.log_disbursement(app.application_id, "SIM-IMMUTABLE", ref)
                with self.assertRaisesRegex(ValueError, "already logged"):
                    log.log(app, result)
                state = log.conn.execute(
                    "SELECT disbursed,collection_reference FROM scoring_log WHERE application_id=?",
                    (app.application_id,),
                ).fetchone()
            self.assertEqual(state, (1, ref))

    def test_partial_and_duplicate_payments_do_not_create_false_outcome(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                ref = make_collection_ref(app.application_id)
                log.log_disbursement(app.application_id, "SIM-001", ref)
                expected = (result.approved_amount_mxn + result.pricing_fixed_cost_mxn) / 2

                partial = process_incoming_payment(
                    {"id": "evt-1", "claveRastreo": f"{ref}-P1", "monto": 1}, tmp.name
                )
                self.assertTrue(partial["matched"])
                self.assertFalse(partial["complete"])

                duplicate = process_incoming_payment(
                    {"id": "evt-1", "claveRastreo": f"{ref}-P1", "monto": 1}, tmp.name
                )
                self.assertTrue(duplicate["duplicate"])

                process_incoming_payment(
                    {"id": "evt-2", "claveRastreo": f"{ref}-P1", "monto": expected - 1}, tmp.name
                )
                row = log.conn.execute(
                    "SELECT payment_1_received,repaid_on_time FROM scoring_log WHERE application_id=?",
                    (app.application_id,),
                ).fetchone()
                self.assertEqual(row, (1, None))

                process_incoming_payment(
                    {"id": "evt-3", "claveRastreo": f"{ref}-P2", "monto": expected}, tmp.name
                )
                row = log.conn.execute(
                    "SELECT repaid_on_time,defaulted,outcome_status FROM scoring_log WHERE application_id=?",
                    (app.application_id,),
                ).fetchone()
            self.assertEqual(row, (1, 0, "paid_on_time"))

    def test_overpayment_is_rejected_without_polluting_ledger(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                ref = make_collection_ref(app.application_id)
                log.log_disbursement(app.application_id, "SIM-OVER", ref)
                expected = (result.approved_amount_mxn + result.pricing_fixed_cost_mxn) / 2
                rejected = process_incoming_payment(
                    {"id": "evt-over", "claveRastreo": f"{ref}-P1", "monto": expected + 100},
                    tmp.name,
                )
                self.assertFalse(rejected["matched"])
                count = log.conn.execute("SELECT COUNT(*) FROM payment_ledger").fetchone()[0]
            self.assertEqual(count, 0)

    def test_overdue_query_returns_real_overdue_loan(self):
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name) as log:
                log.log(app, result)
                ref = make_collection_ref(app.application_id)
                log.log_disbursement(app.application_id, "SIM-002", ref)
                old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
                log.conn.execute(
                    "UPDATE scoring_log SET disbursed_at=? WHERE application_id=?",
                    (old, app.application_id),
                )
                log.conn.commit()
            overdue = check_overdue(tmp.name, grace_days=3)
            self.assertEqual(len(overdue), 1)
            self.assertEqual(overdue[0]["payment_number"], 1)


    def test_no_resource_warnings_from_scoring_log(self):
        """ScoringLog must not leak SQLite connections under normal payment flow."""
        import gc, warnings
        app = healthy_app()
        with patch.dict(os.environ, {"OLIN_MODE": "test"}):
            result = score_application(app)
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                ref = make_collection_ref(app.application_id)
                with ScoringLog(tmp.name) as log:
                    log.log(app, result)
                    log.log_disbursement(app.application_id, "SIM-RW", ref)
                process_incoming_payment(
                    {"id": "rw-p1", "claveRastreo": f"{ref}-P1",
                     "monto": result.approved_amount_mxn / 2},
                    tmp.name,
                )
                check_overdue(tmp.name, grace_days=3)
                gc.collect()
            db_warnings = [
                w for w in caught
                if issubclass(w.category, ResourceWarning)
                and "database" in str(w.message).lower()
            ]
            self.assertEqual(
                db_warnings, [],
                f"Leaked SQLite connections: {[str(w.message) for w in db_warnings]}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
