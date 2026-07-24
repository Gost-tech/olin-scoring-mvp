"""
Olin Credit Scoring MVP - Audit log + Phase 1 training dataset

Every application and every decision is logged with full signal detail.
This table IS the future ML training set (loans 0-200 build the dataset,
XGBoost training starts at 200+). Repayment outcome is updated later via
record_outcome(), which is what turns logs into labels.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import Application, ScoreResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS scoring_log (
    application_id   TEXT PRIMARY KEY,
    merchant_name    TEXT NOT NULL,
    business_type    TEXT NOT NULL,
    colonia          TEXT,
    clabe            TEXT DEFAULT '',
    requested_mxn    REAL NOT NULL,
    approved_mxn     REAL NOT NULL,
    score            REAL NOT NULL,
    ci_low           REAL NOT NULL,
    ci_high          REAL NOT NULL,
    data_coverage    REAL NOT NULL,
    decision         TEXT NOT NULL,
    engine_version   TEXT NOT NULL,
    scored_at        TEXT NOT NULL,
    raw_application  TEXT NOT NULL,   -- full JSON, all signals, for ML later
    raw_result       TEXT NOT NULL,
    -- outcome labels, filled in after the loan term
    disbursed        INTEGER DEFAULT 0,
    repaid_on_time   INTEGER,          -- NULL until known
    days_to_repay    INTEGER,          -- survival analysis needs WHEN, not just IF
    defaulted        INTEGER,
    analyst_override TEXT              -- if analyst disagreed with engine
);
"""

PAYMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_ledger (
    event_id          TEXT PRIMARY KEY,
    application_id    TEXT NOT NULL,
    collection_reference TEXT NOT NULL,
    payment_number    INTEGER NOT NULL CHECK(payment_number IN (1,2)),
    amount_mxn        REAL NOT NULL CHECK(amount_mxn > 0),
    received_at       TEXT NOT NULL,
    raw_event         TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_ledger_application
ON payment_ledger(application_id, payment_number);
"""


class ScoringLog:
    def __init__(self, db_path: str | Path = "olin_scoring.db"):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(SCHEMA)
        self.conn.executescript(PAYMENT_SCHEMA)
        # Incremental migrations — safe to re-run
        for col_sql in [
            "ALTER TABLE scoring_log ADD COLUMN clabe TEXT DEFAULT ''",
            "ALTER TABLE scoring_log ADD COLUMN folio_stp TEXT",
            "ALTER TABLE scoring_log ADD COLUMN disbursed_at TEXT",
            "ALTER TABLE scoring_log ADD COLUMN collection_reference TEXT",
            "ALTER TABLE scoring_log ADD COLUMN payment_1_received INTEGER DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN payment_2_received INTEGER DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN payment_1_date TEXT",
            "ALTER TABLE scoring_log ADD COLUMN payment_2_date TEXT",
            "ALTER TABLE scoring_log ADD COLUMN graduation_tier INTEGER DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN tier INTEGER DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN analyst_note TEXT",
            "ALTER TABLE scoring_log ADD COLUMN buro_score INTEGER",  # Círculo de Crédito score
            "ALTER TABLE scoring_log ADD COLUMN pricing_fixed_cost_mxn REAL DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN is_demo INTEGER DEFAULT 1",
            "ALTER TABLE scoring_log ADD COLUMN analyst_reason TEXT",
            "ALTER TABLE scoring_log ADD COLUMN analyst_decision_at TEXT",
            "ALTER TABLE scoring_log ADD COLUMN payment_1_amount_mxn REAL DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN payment_2_amount_mxn REAL DEFAULT 0",
            "ALTER TABLE scoring_log ADD COLUMN outcome_status TEXT DEFAULT 'not_disbursed'",
            "ALTER TABLE scoring_log ADD COLUMN consent_timestamp TEXT",
            "ALTER TABLE scoring_log ADD COLUMN consent_channel TEXT",
            "ALTER TABLE scoring_log ADD COLUMN consent_text TEXT",
        ]:
            try:
                self.conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass
        # Safe backfills for databases created before the pilot-safety schema.
        for app_id, raw_result, pricing in self.conn.execute(
            "SELECT application_id,raw_result,pricing_fixed_cost_mxn FROM scoring_log"
        ).fetchall():
            if pricing:
                continue
            try:
                stored_pricing = float(json.loads(raw_result or "{}").get("pricing_fixed_cost_mxn", 0))
            except (TypeError, ValueError, json.JSONDecodeError):
                stored_pricing = 0.0
            if stored_pricing:
                self.conn.execute(
                    "UPDATE scoring_log SET pricing_fixed_cost_mxn=? WHERE application_id=?",
                    (stored_pricing, app_id),
                )
        self.conn.execute(
            "UPDATE scoring_log SET outcome_status=CASE "
            "WHEN defaulted=1 THEN 'defaulted' "
            "WHEN repaid_on_time=1 THEN 'paid_on_time' "
            "WHEN disbursed=1 THEN 'active' ELSE 'not_disbursed' END "
            "WHERE outcome_status IS NULL OR outcome_status='not_disbursed'"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def log(self, app: Application, result: ScoreResult) -> None:
        buro_score = app.buro.score if app.buro else None
        try:
            self.conn.execute(
                """INSERT INTO scoring_log
               (application_id, merchant_name, business_type, colonia, clabe,
                requested_mxn, approved_mxn, score, ci_low, ci_high,
                data_coverage, decision, engine_version, scored_at,
                raw_application, raw_result, tier, buro_score,
                pricing_fixed_cost_mxn, is_demo, outcome_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                result.application_id,
                app.merchant_name,
                app.business_type.value,
                app.colonia,
                app.clabe,
                app.requested_amount_mxn,
                result.approved_amount_mxn,
                result.score,
                result.ci_low,
                result.ci_high,
                result.data_coverage,
                result.decision.value,
                result.engine_version,
                result.scored_at,
                json.dumps(app.to_dict(), default=str),
                json.dumps(asdict(result), default=str),
                result.tier,
                buro_score,
                result.pricing_fixed_cost_mxn,
                int(result.environment != "production"),
                "not_disbursed",
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Application {result.application_id} is already logged; "
                "rescoring must create a new application ID"
            ) from exc
        self.conn.commit()

    def record_analyst_note(self, application_id: str, note: str) -> None:
        self.conn.execute(
            "UPDATE scoring_log SET analyst_note=? WHERE application_id=?",
            (note.strip(), application_id),
        )
        self.conn.commit()

    def record_consent(self, application_id: str, channel: str, text: str) -> None:
        """Record the merchant's Círculo consent evidence."""
        from datetime import datetime, timezone

        channel = channel.strip().lower()
        text = text.strip()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError("Consent channel must be whatsapp, sms, or in_person")
        if not text:
            raise ValueError("Consent text is required")
        cur = self.conn.execute(
            "UPDATE scoring_log SET consent_timestamp=?, consent_channel=?, consent_text=? "
            "WHERE application_id=?",
            (datetime.now(timezone.utc).isoformat(), channel, text, application_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise LookupError("Application not found")
        self.conn.commit()

    def record_outcome(
        self,
        application_id: str,
        repaid_on_time: bool,
        days_to_repay: Optional[int] = None,
        defaulted: bool = False,
        analyst_override: Optional[str] = None,
    ) -> None:
        """Day 75 late payment is not the same as Day 90+ default.
        days_to_repay feeds the future survival analysis layer."""
        if days_to_repay is not None and days_to_repay < 0:
            raise ValueError("days_to_repay cannot be negative")
        if defaulted and repaid_on_time:
            raise ValueError("A loan cannot be both defaulted and repaid on time")
        status = "defaulted" if defaulted else (
            "paid_on_time" if repaid_on_time else "paid_late"
        )
        self.conn.execute(
            """UPDATE scoring_log
               SET disbursed = 1, repaid_on_time = ?, days_to_repay = ?,
                   defaulted = ?, analyst_override = ?, outcome_status = ?
               WHERE application_id = ?""",
            (int(repaid_on_time), days_to_repay, int(defaulted),
             analyst_override, status, application_id),
        )
        self.conn.commit()

    def training_rows(self) -> list[dict]:
        """Rows with known outcomes = the Phase 1 training dataset."""
        cur = self.conn.execute(
            "SELECT raw_application, repaid_on_time, days_to_repay, defaulted, outcome_status "
            "FROM scoring_log WHERE is_demo=0 AND defaulted IS NOT NULL "
            "AND outcome_status IN ('paid_on_time','paid_late','defaulted','defaulted_recovered')"
        )
        rows = []
        for raw, repaid, days, defaulted, status in cur.fetchall():
            row = json.loads(raw)
            row["label_repaid_on_time"] = repaid
            row["label_days_to_repay"] = days
            row["label_defaulted"] = defaulted
            row["label_outcome_status"] = status
            rows.append(row)
        return rows

    def stats(self) -> dict:
        cur = self.conn.execute(
            "SELECT decision, COUNT(*), AVG(score) FROM scoring_log GROUP BY decision"
        )
        return {d: {"count": c, "avg_score": round(a, 1)} for d, c, a in cur.fetchall()}

    def claim_disbursement(self, application_id: str) -> bool:
        """
        Atomically claim the disbursement slot before calling STP.

        Sets disbursed=1 and outcome_status='disburse_pending' only if disbursed=0.
        Returns True if this call claimed it, False if already taken.
        Must be called BEFORE the STP network call to prevent double-disbursement
        on process crash between STP success and the subsequent DB write.
        """
        from datetime import datetime, timezone
        cur = self.conn.execute(
            """UPDATE scoring_log
               SET disbursed=1, disbursed_at=?, outcome_status='disburse_pending'
               WHERE application_id=? AND disbursed=0""",
            (datetime.now(timezone.utc).isoformat(), application_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def rollback_disbursement(self, application_id: str, error: str) -> None:
        """
        Called when STP fails after claim_disbursement() succeeded.
        Resets the row so the analyst can investigate and retry.
        Keeps an error note so the failure is visible in the UI.
        """
        self.conn.execute(
            """UPDATE scoring_log
               SET disbursed=0, disbursed_at=NULL, outcome_status='disburse_failed',
                   analyst_note=COALESCE(analyst_note||' | ','') || ?
               WHERE application_id=?""",
            (f"STP error: {error}", application_id),
        )
        self.conn.commit()

    def log_disbursement(self, application_id: str, folio_stp: str,
                         collection_reference: str) -> None:
        """
        Finalise a disbursement after STP confirms.

        Sets disbursed=1 (idempotent if claim_disbursement already set it),
        records the STP folio, and activates the collection reference.
        Safe to call directly in tests without a prior claim_disbursement call.
        """
        from datetime import datetime, timezone
        self.conn.execute(
            """UPDATE scoring_log
               SET disbursed=1,
                   disbursed_at=COALESCE(disbursed_at, ?),
                   folio_stp=?, collection_reference=?, outcome_status='active'
               WHERE application_id=?""",
            (datetime.now(timezone.utc).isoformat(), folio_stp, collection_reference, application_id),
        )
        self.conn.commit()

    def record_payment_event(
        self,
        collection_reference: str,
        payment_number: int,
        amount_mxn: float,
        event_id: str,
        raw_event: dict,
        received_at: Optional[str] = None,
        grace_days: int = 3,
    ) -> dict:
        """Record an idempotent payment and update installment/outcome state."""
        from datetime import datetime, timedelta, timezone

        if payment_number not in (1, 2):
            raise ValueError("payment_number must be 1 or 2")
        if amount_mxn <= 0:
            raise ValueError("amount_mxn must be positive")
        when = received_at or datetime.now(timezone.utc).isoformat()
        row = self.conn.execute(
            "SELECT application_id, approved_mxn, pricing_fixed_cost_mxn, "
            "disbursed, disbursed_at, defaulted FROM scoring_log WHERE collection_reference=?",
            (collection_reference,),
        ).fetchone()
        if not row:
            raise LookupError(f"No loan for reference {collection_reference}")
        if not row[3]:
            raise ValueError("Payment cannot be recorded before disbursement")

        cur = self.conn.execute(
            "INSERT OR IGNORE INTO payment_ledger "
            "(event_id,application_id,collection_reference,payment_number,amount_mxn,received_at,raw_event) "
            "VALUES (?,?,?,?,?,?,?)",
            (event_id, row[0], collection_reference, payment_number, amount_mxn,
             when, json.dumps(raw_event, default=str)),
        )
        if cur.rowcount == 0:
            self.conn.rollback()
            return {"duplicate": True, "application_id": row[0], "payment": payment_number}

        expected = round(((row[1] or 0) + (row[2] or 0)) / 2, 2)
        paid = self.conn.execute(
            "SELECT COALESCE(SUM(amount_mxn),0) FROM payment_ledger "
            "WHERE application_id=? AND payment_number=?",
            (row[0], payment_number),
        ).fetchone()[0]
        if paid > expected + 0.01:
            self.conn.rollback()
            raise ValueError(
                f"Payment exceeds installment balance by MXN {paid - expected:.2f}"
            )
        complete = paid + 0.01 >= expected
        amount_col = "payment_1_amount_mxn" if payment_number == 1 else "payment_2_amount_mxn"
        received_col = "payment_1_received" if payment_number == 1 else "payment_2_received"
        date_col = "payment_1_date" if payment_number == 1 else "payment_2_date"
        self.conn.execute(
            f"UPDATE scoring_log SET {amount_col}=?, {received_col}=?, "
            f"{date_col}=CASE WHEN ?=1 AND {date_col} IS NULL THEN ? ELSE {date_col} END "
            "WHERE application_id=?",
            (round(paid, 2), int(complete), int(complete), when, row[0]),
        )

        state = self.conn.execute(
            "SELECT payment_1_received,payment_2_received,disbursed_at "
            "FROM scoring_log WHERE application_id=?", (row[0],)
        ).fetchone()
        outcome = "defaulted" if row[5] else "active"
        days = None
        if state[0] and state[1]:
            try:
                d0 = datetime.fromisoformat((state[2] or "").replace("Z", "+00:00"))
                if d0.tzinfo is None:
                    d0 = d0.replace(tzinfo=timezone.utc)
                paid_at = datetime.fromisoformat(when.replace("Z", "+00:00"))
                if paid_at.tzinfo is None:
                    paid_at = paid_at.replace(tzinfo=timezone.utc)
                days = max(0, (paid_at - d0).days)
                on_time = paid_at <= d0 + timedelta(days=60 + grace_days)
            except (ValueError, TypeError):
                on_time = False
            if row[5]:
                outcome = "defaulted_recovered"
                self.conn.execute(
                    "UPDATE scoring_log SET repaid_on_time=0, days_to_repay=?, "
                    "outcome_status=? WHERE application_id=?",
                    (days, outcome, row[0]),
                )
            else:
                outcome = "paid_on_time" if on_time else "paid_late"
                self.conn.execute(
                    "UPDATE scoring_log SET repaid_on_time=?, days_to_repay=?, defaulted=0, "
                    "outcome_status=? WHERE application_id=?",
                    (int(on_time), days, outcome, row[0]),
                )
        self.conn.commit()
        return {
            "duplicate": False,
            "application_id": row[0],
            "payment": payment_number,
            "amount_applied": round(amount_mxn, 2),
            "installment_paid": round(paid, 2),
            "expected": expected,
            "remaining": round(max(0.0, expected - paid), 2),
            "complete": complete,
            "outcome_status": outcome,
        }

    def record_analyst_decision(self, application_id: str, decision: str, reason: str) -> None:
        from datetime import datetime, timezone

        decision = decision.upper().strip()
        reason = reason.strip()
        if decision not in ("APPROVE", "MANUAL_REVIEW", "DECLINE"):
            raise ValueError("Invalid analyst decision")
        if len(reason) < 5:
            raise ValueError("A decision reason of at least 5 characters is required")
        row = self.conn.execute(
            "SELECT decision,analyst_override FROM scoring_log WHERE application_id=?",
            (application_id,),
        ).fetchone()
        if not row:
            raise LookupError("Application not found")
        if row[1]:
            raise ValueError("Analyst decision is already recorded")
        if decision == "APPROVE" and row[0] == "DECLINE":
            raise ValueError("Engine declines are non-overridable during the pilot")
        self.conn.execute(
            "UPDATE scoring_log SET analyst_override=?,analyst_reason=?,analyst_decision_at=? "
            "WHERE application_id=?",
            (decision, reason, datetime.now(timezone.utc).isoformat(), application_id),
        )
        self.conn.commit()

    def active_loans(self) -> list[dict]:
        """Loans disbursed and not yet fully repaid."""
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            """SELECT application_id, merchant_name, business_type, colonia,
                      clabe, approved_mxn, disbursed_at, collection_reference,
                      payment_1_received, payment_2_received,
                      repaid_on_time, scored_at
               FROM scoring_log
               WHERE disbursed=1 AND outcome_status='active'
               ORDER BY disbursed_at DESC"""
        ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def merchant_history(self, clabe: str) -> list[dict]:
        """All loans for a given CLABE, ordered newest first."""
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            """SELECT application_id, approved_mxn, decision, analyst_override,
                      repaid_on_time, days_to_repay, defaulted, disbursed_at,
                      graduation_tier, scored_at
               FROM scoring_log
               WHERE clabe=? ORDER BY scored_at DESC""",
            (clabe,),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def portfolio_snapshot(self) -> dict:
        """Aggregated stats for the portfolio dashboard."""
        total = self.conn.execute("SELECT COUNT(*) FROM scoring_log").fetchone()[0]
        disbursed_count = self.conn.execute(
            "SELECT COUNT(*) FROM scoring_log WHERE disbursed=1").fetchone()[0]
        active_count = self.conn.execute(
            "SELECT COUNT(*) FROM scoring_log WHERE disbursed=1 "
            "AND outcome_status='active'").fetchone()[0]
        active_mxn = self.conn.execute(
            "SELECT COALESCE(SUM(approved_mxn),0) FROM scoring_log WHERE disbursed=1 "
            "AND outcome_status='active'").fetchone()[0]
        repaid = self.conn.execute(
            "SELECT COUNT(*) FROM scoring_log WHERE repaid_on_time=1").fetchone()[0]
        defaulted = self.conn.execute(
            "SELECT COUNT(*) FROM scoring_log WHERE defaulted=1").fetchone()[0]
        resolved = self.conn.execute(
            "SELECT COUNT(*) FROM scoring_log WHERE outcome_status IN "
            "('paid_on_time','paid_late','defaulted','defaulted_recovered')").fetchone()[0]

        by_colonia = self.conn.execute(
            "SELECT colonia, COUNT(*), SUM(approved_mxn) FROM scoring_log "
            "WHERE disbursed=1 AND outcome_status='active' "
            "GROUP BY colonia ORDER BY COUNT(*) DESC LIMIT 10"
        ).fetchall()
        by_type = self.conn.execute(
            "SELECT business_type, COUNT(*) FROM scoring_log "
            "WHERE disbursed=1 AND outcome_status='active' "
            "GROUP BY business_type"
        ).fetchall()

        by_tier = self.conn.execute(
            """SELECT tier, decision, COUNT(*) FROM scoring_log
               GROUP BY tier, decision ORDER BY tier"""
        ).fetchall()

        return {
            "total_applications": total,
            "total_disbursed": disbursed_count,
            "active_loans": active_count,
            "active_mxn": round(active_mxn, 0),
            "repaid": repaid,
            "defaulted": defaulted,
            "resolved_loans": resolved,
            "default_rate": round(defaulted / resolved, 3) if resolved else 0.0,
            "by_colonia": [{"colonia": r[0], "count": r[1], "mxn": r[2]} for r in by_colonia],
            "by_type": [{"type": r[0], "count": r[1]} for r in by_type],
            "by_tier": [{"tier": r[0], "decision": r[1], "count": r[2]} for r in by_tier],
        }
