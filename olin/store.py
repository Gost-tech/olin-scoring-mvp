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
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import Application, ScoreResult

_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DATABASES: set[tuple[str, int, int]] = set()


class _HybridRow(dict):
    """Mapping row that also preserves SQLite-style numeric indexing."""

    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._noop = False

    @staticmethod
    def _sql(sql: str) -> str:
        normalized = sql.strip()
        if normalized.upper().startswith("PRAGMA "):
            return ""
        ignore_insert = normalized.upper().startswith("INSERT OR IGNORE INTO")
        normalized = normalized.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if ignore_insert:
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        # All application SQL uses DB-API qmark placeholders.
        return normalized.replace("?", "%s")

    def execute(self, sql, params=()):
        translated = self._sql(sql)
        self._noop = not translated
        if self._noop:
            return self
        try:
            self._cursor.execute(translated, params)
        except Exception as exc:
            import psycopg
            if isinstance(exc, psycopg.errors.UniqueViolation):
                raise sqlite3.IntegrityError(str(exc)) from exc
            if isinstance(exc, psycopg.errors.DuplicateColumn):
                raise sqlite3.OperationalError(str(exc)) from exc
            raise
        return self

    def fetchone(self):
        if self._noop:
            return None
        return self._cursor.fetchone()

    def fetchall(self):
        if self._noop:
            return []
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return 0 if self._noop else self._cursor.rowcount


class _PostgresConnection:
    """Small DB-API compatibility layer for the existing SQLite query surface."""

    is_postgres = True

    def __init__(self, dsn: str):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised in production images
            raise RuntimeError("psycopg is required when OLIN_DATABASE_URL is PostgreSQL") from exc

        def row_factory(cursor):
            columns = [column.name for column in cursor.description]
            return lambda values: _HybridRow(columns, values)

        self._conn = psycopg.connect(dsn, row_factory=row_factory, connect_timeout=10)
        self._closed = False

    def execute(self, sql, params=()):
        translated = _PostgresCursor._sql(sql)
        if not translated:
            return _PostgresCursor(None)
        try:
            cursor = self._conn.execute(translated, params)
        except Exception as exc:
            import psycopg
            if isinstance(exc, psycopg.errors.UniqueViolation):
                raise sqlite3.IntegrityError(str(exc)) from exc
            if isinstance(exc, psycopg.errors.DuplicateColumn):
                raise sqlite3.OperationalError(str(exc)) from exc
            raise
        return _PostgresCursor(cursor)

    def executescript(self, script: str):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
        return self

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if not self._closed:
            self._conn.close()
            self._closed = True


def connect_database(target: str | Path):
    """Open the configured runtime database; SQLite is retained for synthetic mode."""
    target_text = str(target)
    if target_text.startswith(("postgres://", "postgresql://")):
        return _PostgresConnection(target_text)
    return sqlite3.connect(target_text, timeout=10)

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

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_event (
    event_id       TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    actor          TEXT NOT NULL,
    occurred_at    TEXT NOT NULL,
    payload        TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_audit_event_application
ON audit_event(application_id, occurred_at);
"""

GOVERNANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_record (
    consent_id       TEXT PRIMARY KEY,
    application_id   TEXT NOT NULL,
    purpose          TEXT NOT NULL,
    policy_version   TEXT NOT NULL,
    text_sha256      TEXT NOT NULL,
    channel          TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('active','withdrawn','superseded')),
    captured_at      TEXT NOT NULL,
    captured_by      TEXT NOT NULL,
    withdrawn_at     TEXT,
    withdrawal_reason TEXT,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_consent_record_application
ON consent_record(application_id, captured_at);

CREATE TABLE IF NOT EXISTS data_authorization_record (
    authorization_id   TEXT PRIMARY KEY,
    application_id     TEXT NOT NULL,
    owner_actor        TEXT NOT NULL,
    basis_label        TEXT NOT NULL,
    approval_reference TEXT NOT NULL,
    approved_by        TEXT NOT NULL,
    approved_at        TEXT NOT NULL,
    scope_sha256       TEXT NOT NULL,
    status             TEXT NOT NULL CHECK(status IN ('active','withdrawn')),
    recorded_at        TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_data_authorization_application
ON data_authorization_record(application_id, recorded_at);

CREATE TABLE IF NOT EXISTS correction_request (
    request_id       TEXT PRIMARY KEY,
    application_id   TEXT NOT NULL,
    field_path       TEXT NOT NULL,
    claimed_value    TEXT NOT NULL,
    reason           TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('open','accepted','rejected')),
    created_at       TEXT NOT NULL,
    created_by       TEXT NOT NULL,
    resolved_at      TEXT,
    resolved_by      TEXT,
    resolution_note  TEXT,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_correction_request_application
ON correction_request(application_id, created_at);

CREATE TABLE IF NOT EXISTS bank_ingestion_event (
    event_id         TEXT PRIMARY KEY,
    application_id   TEXT NOT NULL,
    provider         TEXT NOT NULL,
    connection_id    TEXT NOT NULL,
    consent_id       TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    derived_metrics  TEXT,
    observed_at      TEXT NOT NULL,
    received_at      TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id),
    FOREIGN KEY(consent_id) REFERENCES consent_record(consent_id)
);
CREATE INDEX IF NOT EXISTS idx_bank_ingestion_application
ON bank_ingestion_event(application_id, received_at);

CREATE TABLE IF NOT EXISTS intake (
    intake_id        TEXT PRIMARY KEY,
    owner_actor      TEXT NOT NULL,
    partner_case_reference TEXT NOT NULL,
    cohort_id        TEXT NOT NULL,
    merchant_name    TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN
                     ('created','consented','link_pending','evidence_ready',
                      'scoring','scored','cancelled')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    scored_application_id TEXT,
    UNIQUE(owner_actor, partner_case_reference)
);
CREATE INDEX IF NOT EXISTS idx_intake_owner ON intake(owner_actor, created_at);

CREATE TABLE IF NOT EXISTS intake_consent (
    consent_id       TEXT PRIMARY KEY,
    intake_id        TEXT NOT NULL,
    purpose          TEXT NOT NULL,
    policy_version   TEXT NOT NULL,
    text_sha256      TEXT NOT NULL,
    channel          TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('active','withdrawn','superseded')),
    captured_at      TEXT NOT NULL,
    captured_by      TEXT NOT NULL,
    withdrawn_at     TEXT,
    withdrawal_reason TEXT,
    provider          TEXT NOT NULL DEFAULT '',
    notice_version    TEXT NOT NULL DEFAULT '',
    language          TEXT NOT NULL DEFAULT 'es-MX',
    text_snapshot     TEXT NOT NULL DEFAULT '',
    privacy_notice_url TEXT NOT NULL DEFAULT '',
    retention_summary TEXT NOT NULL DEFAULT '',
    destination_hash  TEXT NOT NULL DEFAULT '',
    identity_reference_hash TEXT NOT NULL DEFAULT '',
    authority_reference_hash TEXT NOT NULL DEFAULT '',
    verification_method TEXT NOT NULL DEFAULT '',
    verification_artifact TEXT NOT NULL DEFAULT '',
    receipt_sha256    TEXT NOT NULL DEFAULT '',
    receipt_json      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_consent ON intake_consent(intake_id, captured_at);

CREATE TABLE IF NOT EXISTS consent_policy (
    policy_id         TEXT PRIMARY KEY,
    owner_actor       TEXT NOT NULL,
    purpose           TEXT NOT NULL CHECK(purpose IN
                      ('credit_assessment','provider_access','credit_bureau')),
    provider          TEXT NOT NULL DEFAULT '',
    policy_version    TEXT NOT NULL,
    notice_version    TEXT NOT NULL,
    language          TEXT NOT NULL,
    text_snapshot     TEXT NOT NULL,
    text_sha256       TEXT NOT NULL,
    privacy_notice_url TEXT NOT NULL,
    retention_summary TEXT NOT NULL,
    status            TEXT NOT NULL CHECK(status IN ('synthetic_uat','approved','retired')),
    legal_approval_ref TEXT NOT NULL DEFAULT '',
    privacy_approval_ref TEXT NOT NULL DEFAULT '',
    partner_approval_ref TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    UNIQUE(owner_actor,purpose,provider,policy_version)
);

CREATE TABLE IF NOT EXISTS intake_identity_binding (
    binding_id        TEXT PRIMARY KEY,
    intake_id         TEXT NOT NULL,
    owner_actor       TEXT NOT NULL,
    evidence_type     TEXT NOT NULL CHECK(evidence_type IN
                      ('government_identity_verified',
                       'individual_business_ownership_verified',
                       'legal_representative_authority_verified')),
    source_id         TEXT NOT NULL,
    source_reference  TEXT NOT NULL,
    subject_hash      TEXT NOT NULL,
    attestation_id    TEXT NOT NULL,
    status            TEXT NOT NULL CHECK(status IN ('verified','revoked')),
    observed_at       TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    revoked_at        TEXT,
    revocation_reason TEXT,
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id),
    UNIQUE(source_id,source_reference,evidence_type)
);
CREATE INDEX IF NOT EXISTS idx_intake_identity_binding
ON intake_identity_binding(intake_id,owner_actor,evidence_type,status);

CREATE TABLE IF NOT EXISTS consent_challenge (
    challenge_id      TEXT PRIMARY KEY,
    intake_id         TEXT NOT NULL,
    owner_actor       TEXT NOT NULL,
    policy_id         TEXT NOT NULL,
    purpose           TEXT NOT NULL,
    provider          TEXT NOT NULL DEFAULT '',
    channel           TEXT NOT NULL,
    destination_hash  TEXT NOT NULL,
    identity_reference_hash TEXT NOT NULL,
    authority_reference_hash TEXT NOT NULL DEFAULT '',
    public_token_sha256 TEXT NOT NULL DEFAULT '',
    otp_hash          TEXT NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 5,
    status            TEXT NOT NULL CHECK(status IN
                      ('pending','verified','expired','locked','cancelled','dispatch_failed')),
    issued_at         TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    verified_at       TEXT,
    dispatch_artifact TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id),
    FOREIGN KEY(policy_id) REFERENCES consent_policy(policy_id)
);
CREATE INDEX IF NOT EXISTS idx_consent_challenge_intake
ON consent_challenge(intake_id,purpose,provider,issued_at);

CREATE TABLE IF NOT EXISTS consent_withdrawal_task (
    task_id           TEXT PRIMARY KEY,
    intake_id         TEXT NOT NULL,
    consent_id        TEXT NOT NULL,
    purpose           TEXT NOT NULL,
    provider          TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL CHECK(status IN ('open','resolved')),
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    resolution_note   TEXT,
    resolved_at       TEXT,
    resolved_by       TEXT,
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id),
    FOREIGN KEY(consent_id) REFERENCES intake_consent(consent_id)
);

CREATE TABLE IF NOT EXISTS intake_link_session (
    link_session_id  TEXT PRIMARY KEY,
    intake_id        TEXT NOT NULL,
    consent_id       TEXT NOT NULL,
    provider         TEXT NOT NULL,
    token_sha256     TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('active','completed','expired','cancelled')),
    created_at       TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    launched_at      TEXT,
    completed_at     TEXT,
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id),
    FOREIGN KEY(consent_id) REFERENCES intake_consent(consent_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_link ON intake_link_session(intake_id, created_at);

CREATE TABLE IF NOT EXISTS intake_bank_event (
    event_id         TEXT PRIMARY KEY,
    intake_id        TEXT NOT NULL,
    link_session_id  TEXT NOT NULL,
    provider         TEXT NOT NULL,
    connection_id    TEXT NOT NULL,
    consent_id       TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    derived_metrics  TEXT NOT NULL,
    observed_at      TEXT NOT NULL,
    received_at      TEXT NOT NULL,
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_bank_event ON intake_bank_event(intake_id, received_at);

CREATE TABLE IF NOT EXISTS intake_audit_event (
    event_id         TEXT PRIMARY KEY,
    intake_id        TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    actor            TEXT NOT NULL,
    occurred_at      TEXT NOT NULL,
    payload          TEXT NOT NULL,
    FOREIGN KEY(intake_id) REFERENCES intake(intake_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_audit ON intake_audit_event(intake_id, occurred_at);

CREATE TABLE IF NOT EXISTS shadow_performance_event (
    event_id          TEXT PRIMARY KEY,
    application_id    TEXT NOT NULL,
    owner_actor       TEXT NOT NULL,
    observed_at       TEXT NOT NULL,
    period_end        TEXT NOT NULL,
    days_past_due     INTEGER NOT NULL CHECK(days_past_due >= 0),
    status            TEXT NOT NULL,
    outstanding_balance_mxn REAL NOT NULL CHECK(outstanding_balance_mxn >= 0),
    scheduled_payment_mxn REAL NOT NULL CHECK(scheduled_payment_mxn >= 0),
    amount_paid_mxn   REAL NOT NULL CHECK(amount_paid_mxn >= 0),
    source            TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    outcome_definition_version TEXT NOT NULL,
    received_at       TEXT NOT NULL,
    raw_event         TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id)
);
CREATE INDEX IF NOT EXISTS idx_shadow_performance_case
ON shadow_performance_event(application_id, period_end);

CREATE TABLE IF NOT EXISTS evidence_record (
    evidence_id       TEXT PRIMARY KEY,
    application_id    TEXT NOT NULL,
    owner_actor       TEXT NOT NULL,
    evidence_type     TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    origin_id         TEXT NOT NULL,
    subject_key       TEXT NOT NULL,
    subject_hash      TEXT NOT NULL,
    verification_method TEXT NOT NULL,
    source_reference  TEXT NOT NULL,
    attestation_id    TEXT NOT NULL,
    consent_id        TEXT NOT NULL,
    status            TEXT NOT NULL CHECK(status IN ('verified','revoked')),
    observed_at       TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    metadata_sha256   TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    revoked_at        TEXT,
    revocation_reason TEXT,
    FOREIGN KEY(application_id) REFERENCES scoring_log(application_id),
    FOREIGN KEY(consent_id) REFERENCES consent_record(consent_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_record_case
ON evidence_record(application_id, owner_actor, evidence_type, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_source_reference
ON evidence_record(source_id, source_reference);
"""


class ScoringLog:
    def __init__(self, db_path: str | Path = "olin_scoring.db"):
        target = str(db_path)
        is_postgres = target.startswith(("postgres://", "postgresql://"))
        path = Path(db_path).expanduser().resolve() if not is_postgres else None
        self.conn = connect_database(target)
        try:
            self.conn.execute("PRAGMA busy_timeout=10000")
            self.conn.execute("PRAGMA foreign_keys=ON")
            if is_postgres:
                database_key = (target, 0, 0)
            else:
                stat = path.stat()
                database_key = (str(path), stat.st_dev, stat.st_ino)
            with _SCHEMA_LOCK:
                if database_key not in _INITIALIZED_DATABASES:
                    self.conn.execute("PRAGMA journal_mode=WAL")
                    self.conn.execute("PRAGMA synchronous=NORMAL")
                    self._initialize()
                    _INITIALIZED_DATABASES.add(database_key)
        except BaseException:
            self.conn.close()
            raise

    def _initialize(self) -> None:
        """Create and migrate the schema without leaking on partial failure."""
        self.conn.execute(SCHEMA)
        self.conn.executescript(PAYMENT_SCHEMA)
        self.conn.executescript(AUDIT_SCHEMA)
        self.conn.executescript(GOVERNANCE_SCHEMA)
        try:
            self.conn.execute("ALTER TABLE bank_ingestion_event ADD COLUMN derived_metrics TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute("ALTER TABLE intake_link_session ADD COLUMN launched_at TEXT")
        except sqlite3.OperationalError:
            pass
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
            "ALTER TABLE scoring_log ADD COLUMN cohort_id TEXT",
            "ALTER TABLE scoring_log ADD COLUMN case_mode TEXT",
            "ALTER TABLE scoring_log ADD COLUMN partner_case_reference TEXT",
            "ALTER TABLE scoring_log ADD COLUMN partner_decision TEXT",
            "ALTER TABLE scoring_log ADD COLUMN partner_reason TEXT",
            "ALTER TABLE scoring_log ADD COLUMN partner_decision_at TEXT",
            "ALTER TABLE scoring_log ADD COLUMN recommendation_agreement INTEGER",
            "ALTER TABLE scoring_log ADD COLUMN owner_actor TEXT",
            "ALTER TABLE intake_consent ADD COLUMN provider TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN notice_version TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN language TEXT NOT NULL DEFAULT 'es-MX'",
            "ALTER TABLE intake_consent ADD COLUMN text_snapshot TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN privacy_notice_url TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN retention_summary TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN destination_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN identity_reference_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN authority_reference_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN verification_method TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN verification_artifact TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN receipt_sha256 TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE intake_consent ADD COLUMN receipt_json TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE consent_challenge ADD COLUMN public_token_sha256 TEXT NOT NULL DEFAULT ''",
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

    def _append_audit(
        self,
        application_id: str,
        event_type: str,
        actor: str,
        payload: dict,
    ) -> None:
        """Append one immutable workflow event to the case audit trail."""
        from datetime import datetime, timezone
        from uuid import uuid4

        self.conn.execute(
            "INSERT INTO audit_event "
            "(event_id,application_id,event_type,actor,occurred_at,payload) "
            "VALUES (?,?,?,?,?,?)",
            (
                uuid4().hex,
                application_id,
                event_type,
                str(actor or "system")[:120],
                datetime.now(timezone.utc).isoformat(),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _performance_status(days_past_due: int, outstanding: float, event_type: str) -> str:
        if event_type in {"defaulted", "restructured", "charged_off"}:
            return event_type
        if outstanding == 0:
            return "paid_off"
        if days_past_due == 0:
            return "current"
        if days_past_due < 30:
            return "dpd_1_29"
        if days_past_due < 60:
            return "dpd_30_59"
        if days_past_due < 90:
            return "dpd_60_89"
        return "dpd_90_plus"

    def record_shadow_performance(
        self, application_id: str, payload: dict, actor: str
    ) -> dict:
        """Append a bank-observed performance label without mutating disbursement."""
        from datetime import datetime, timezone
        from .source_trust import assess_source

        event_id = str(payload.get("event_id", "")).strip()
        observed_at = str(payload.get("observed_at", "")).strip()
        period_end = str(payload.get("period_end", "")).strip()
        source = str(payload.get("source", "")).strip().lower()
        reference = str(payload.get("evidence_reference", "")).strip()
        event_type = str(payload.get("event_type", "scheduled_observation")).strip().lower()
        if not all((event_id, observed_at, period_end, source, reference)):
            raise ValueError("event_id, observed_at, period_end, source and evidence_reference are required")
        try:
            datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            datetime.fromisoformat(period_end.replace("Z", "+00:00"))
            days_past_due = int(payload.get("days_past_due", 0))
            outstanding = float(payload.get("outstanding_balance_mxn", 0))
            scheduled = float(payload.get("scheduled_payment_mxn", 0))
            paid = float(payload.get("amount_paid_mxn", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("performance dates and numeric fields are invalid") from exc
        if days_past_due < 0 or min(outstanding, scheduled, paid) < 0:
            raise ValueError("performance numeric fields cannot be negative")
        if event_type not in {"scheduled_observation", "defaulted", "restructured", "charged_off"}:
            raise ValueError("event_type must be scheduled_observation, defaulted, restructured, or charged_off")
        if event_type == "scheduled_observation" and outstanding == 0 and days_past_due != 0:
            raise ValueError("a paid-off observation cannot have days_past_due")
        row = self.conn.execute(
            "SELECT owner_actor FROM scoring_log WHERE application_id=?", (application_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Application not found")
        owner = str(row[0] or "")
        status = self._performance_status(days_past_due, outstanding, event_type)
        source_trust = assess_source(source, "repayment_outcome")
        if not source_trust.trusted:
            raise ValueError(f"repayment outcome source is not trusted: {source_trust.reason}")
        normalized = {
            "event_id": event_id, "application_id": application_id,
            "observed_at": observed_at, "period_end": period_end,
            "days_past_due": days_past_due, "status": status,
            "event_type": event_type,
            "outstanding_balance_mxn": outstanding,
            "scheduled_payment_mxn": scheduled, "amount_paid_mxn": paid,
            "source": source, "evidence_reference": reference,
            "outcome_definition_version": "shadow-performance-1.0",
            "source_trust": source_trust.to_dict(),
        }
        existing = self.conn.execute(
            "SELECT raw_event FROM shadow_performance_event WHERE event_id=?", (event_id,)
        ).fetchone()
        encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        if existing:
            stored = json.loads(existing[0])
            stored.pop("source_trust", None)
            compared = dict(normalized)
            compared.pop("source_trust", None)
            if stored != compared:
                raise ValueError("event_id already exists with different content")
            return json.loads(existing[0])
        received = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO shadow_performance_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, application_id, owner, observed_at, period_end, days_past_due,
             status, outstanding, scheduled, paid, source, reference,
             "shadow-performance-1.0", received, encoded),
        )
        self._append_audit(application_id, "shadow_performance_recorded", actor, normalized)
        self.conn.commit()
        return normalized

    def list_shadow_performance(self, application_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT raw_event FROM shadow_performance_event WHERE application_id=? ORDER BY period_end, received_at",
            (application_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

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
            self._append_audit(
                result.application_id,
                "case_scored",
                "olin_engine",
                {
                    "engine_version": result.engine_version,
                    "decision": result.decision.value,
                    "tier": result.tier,
                    "score": result.score,
                },
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

    def record_consent(
        self,
        application_id: str,
        channel: str,
        text: str,
        actor: str = "system",
        purpose: str = "credit_assessment",
        policy_version: str = "v1",
    ) -> None:
        """Record the merchant's Círculo consent evidence."""
        from datetime import datetime, timezone
        from hashlib import sha256
        from uuid import uuid4

        channel = channel.strip().lower()
        text = text.strip()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError("Consent channel must be whatsapp, sms, or in_person")
        if not text:
            raise ValueError("Consent text is required")
        purpose = str(purpose).strip().lower()
        policy_version = str(policy_version).strip()
        if purpose != "credit_assessment":
            raise ValueError("Consent purpose must be credit_assessment")
        if not policy_version or len(policy_version) > 40:
            raise ValueError("Consent policy_version is required")
        when = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "UPDATE scoring_log SET consent_timestamp=?, consent_channel=?, consent_text=? "
            "WHERE application_id=?",
            (when, channel, text, application_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise LookupError("Application not found")
        self.conn.execute(
            "UPDATE consent_record SET status='superseded' "
            "WHERE application_id=? AND purpose=? AND status='active'",
            (application_id, purpose),
        )
        consent_id = uuid4().hex
        self.conn.execute(
            "INSERT INTO consent_record "
            "(consent_id,application_id,purpose,policy_version,text_sha256,channel,"
            "status,captured_at,captured_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                consent_id, application_id, purpose, policy_version,
                sha256(text.encode("utf-8")).hexdigest(), channel, "active",
                when, str(actor or "system")[:120],
            ),
        )
        self._append_audit(
            application_id,
            "consent_recorded",
            actor,
            {
                "consent_id": consent_id,
                "channel": channel,
                "purpose": purpose,
                "policy_version": policy_version,
                "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
            },
        )
        self.conn.commit()

    def record_consent_hash(
        self, application_id: str, channel: str, text_sha256: str,
        actor: str = "system", purpose: str = "credit_assessment",
        policy_version: str = "v1",
    ) -> None:
        """Carry a pre-scoring consent into a case without duplicating its text."""
        from datetime import datetime, timezone
        import re
        from uuid import uuid4

        channel = str(channel).strip().lower()
        digest = str(text_sha256).strip().lower()
        purpose = str(purpose).strip().lower()
        policy_version = str(policy_version).strip()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError("Consent channel must be whatsapp, sms, or in_person")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Consent text_sha256 must be a 64-character hex digest")
        if purpose != "credit_assessment" or not policy_version or len(policy_version) > 40:
            raise ValueError("Consent purpose or policy_version is invalid")
        when = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "UPDATE scoring_log SET consent_timestamp=?,consent_channel=?,consent_text=? "
            "WHERE application_id=?",
            (when, channel, f"sha256:{digest}", application_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise LookupError("Application not found")
        self.conn.execute(
            "UPDATE consent_record SET status='superseded' "
            "WHERE application_id=? AND purpose=? AND status='active'",
            (application_id, purpose),
        )
        consent_id = uuid4().hex
        self.conn.execute(
            "INSERT INTO consent_record "
            "(consent_id,application_id,purpose,policy_version,text_sha256,channel,"
            "status,captured_at,captured_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (consent_id, application_id, purpose, policy_version, digest, channel,
             "active", when, str(actor or "system")[:120]),
        )
        self._append_audit(
            application_id, "consent_recorded", actor,
            {"consent_id": consent_id, "channel": channel, "purpose": purpose,
             "policy_version": policy_version, "text_sha256": digest,
             "carried_from_intake": True},
        )
        self.conn.commit()

    def list_consents(self, application_id: str) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM consent_record WHERE application_id=? ORDER BY captured_at DESC",
            (application_id,),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def record_data_authorization(
        self, application_id: str, authorization: dict, actor: str,
    ) -> dict:
        """Record a bank/counsel-approved data-use artifact without calling it consent."""
        from datetime import datetime, timezone
        from uuid import uuid4

        authorization_id = uuid4().hex
        recorded_at = datetime.now(timezone.utc).isoformat()
        row = {
            "authorization_id": authorization_id,
            "application_id": application_id,
            "owner_actor": str(actor)[:120],
            "basis_label": str(authorization["basis_label"]),
            "approval_reference": str(authorization["approval_reference"]),
            "approved_by": str(authorization["approved_by"]),
            "approved_at": str(authorization["approved_at"]),
            "scope_sha256": str(authorization["scope_sha256"]),
            "status": "active",
            "recorded_at": recorded_at,
        }
        self.conn.execute(
            "INSERT INTO data_authorization_record VALUES (?,?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
        self._append_audit(
            application_id, "data_authorization_recorded", actor,
            {key: value for key, value in row.items() if key != "owner_actor"},
        )
        self.conn.commit()
        return row

    def list_data_authorizations(self, application_id: str) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM data_authorization_record WHERE application_id=? "
            "ORDER BY recorded_at DESC",
            (application_id,),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def withdraw_consent(
        self, application_id: str, consent_id: str, reason: str, actor: str
    ) -> dict:
        from datetime import datetime, timezone

        reason = str(reason).strip()
        if len(reason) < 5:
            raise ValueError("A withdrawal reason of at least 5 characters is required")
        when = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "UPDATE consent_record SET status='withdrawn',withdrawn_at=?,withdrawal_reason=? "
            "WHERE consent_id=? AND application_id=? AND status='active'",
            (when, reason[:1000], consent_id, application_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise LookupError("Active consent not found")
        self.conn.execute(
            "UPDATE scoring_log SET consent_timestamp=NULL,consent_channel=NULL,consent_text=NULL "
            "WHERE application_id=?",
            (application_id,),
        )
        self._append_audit(
            application_id, "consent_withdrawn", actor,
            {"consent_id": consent_id, "reason": reason[:1000]},
        )
        self.conn.commit()
        return {"consent_id": consent_id, "status": "withdrawn", "withdrawn_at": when}

    def create_correction_request(
        self, application_id: str, field_path: str, claimed_value, reason: str, actor: str
    ) -> dict:
        from datetime import datetime, timezone
        from uuid import uuid4

        field_path = str(field_path).strip()
        reason = str(reason).strip()
        if not field_path or len(field_path) > 160 or not field_path.replace("_", "").replace(".", "").isalnum():
            raise ValueError("field_path must be a dotted field name")
        if len(reason) < 5:
            raise ValueError("A correction reason of at least 5 characters is required")
        if self.conn.execute(
            "SELECT 1 FROM scoring_log WHERE application_id=?", (application_id,)
        ).fetchone() is None:
            raise LookupError("Application not found")
        serialized = json.dumps(claimed_value, ensure_ascii=False, default=str)
        if len(serialized.encode("utf-8")) > 8_192:
            raise ValueError("claimed_value is too large")
        request_id = uuid4().hex
        when = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO correction_request "
            "(request_id,application_id,field_path,claimed_value,reason,status,created_at,created_by) "
            "VALUES (?,?,?,?,?,'open',?,?)",
            (request_id, application_id, field_path, serialized, reason[:2000], when, str(actor)[:120]),
        )
        self._append_audit(
            application_id, "correction_requested", actor,
            {"request_id": request_id, "field_path": field_path, "reason": reason[:2000]},
        )
        self.conn.commit()
        return {"request_id": request_id, "status": "open", "created_at": when}

    def list_corrections(self, application_id: str) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM correction_request WHERE application_id=? ORDER BY created_at DESC",
            (application_id,),
        ).fetchall()
        self.conn.row_factory = None
        result = []
        for row in rows:
            item = dict(row)
            item["claimed_value"] = json.loads(item["claimed_value"])
            result.append(item)
        return result

    def list_bank_evidence(self, application_id: str) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT event_id,application_id,provider,connection_id,consent_id,"
            "payload_sha256,derived_metrics,observed_at,received_at "
            "FROM bank_ingestion_event WHERE application_id=? ORDER BY received_at DESC",
            (application_id,),
        ).fetchall()
        self.conn.row_factory = None
        result = []
        for row in rows:
            item = dict(row)
            item["bank"] = json.loads(item.pop("derived_metrics") or "{}")
            result.append(item)
        return result

    def resolve_correction_request(
        self, application_id: str, request_id: str, status: str, note: str, actor: str
    ) -> dict:
        from datetime import datetime, timezone

        status = str(status).strip().lower()
        note = str(note).strip()
        if status not in ("accepted", "rejected"):
            raise ValueError("status must be accepted or rejected")
        if len(note) < 5:
            raise ValueError("A resolution note of at least 5 characters is required")
        when = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "UPDATE correction_request SET status=?,resolved_at=?,resolved_by=?,resolution_note=? "
            "WHERE request_id=? AND application_id=? AND status='open'",
            (status, when, str(actor)[:120], note[:2000], request_id, application_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise LookupError("Open correction request not found")
        self._append_audit(
            application_id, "correction_resolved", actor,
            {"request_id": request_id, "status": status, "resolution_note": note[:2000],
             "requires_rescore": status == "accepted"},
        )
        self.conn.commit()
        return {"request_id": request_id, "status": status, "resolved_at": when,
                "requires_rescore": status == "accepted"}

    def record_partner_outcome(
        self,
        application_id: str,
        decision: str,
        reason: str,
        decision_at: Optional[str] = None,
        actor: str = "partner",
    ) -> dict:
        """Persist a partner's independent shadow-pilot outcome.

        This is deliberately separate from the analyst decision: the partner
        supplies the ground-truth comparison after seeing the expediente.
        No money movement is triggered by this method.
        """
        from datetime import datetime, timezone

        decision = str(decision).strip().lower()
        reason = str(reason).strip()
        if decision not in ("approved", "declined", "pending"):
            raise ValueError("partner_decision must be approved, declined, or pending")
        if decision != "pending" and len(reason) < 5:
            raise ValueError("A partner reason of at least 5 characters is required")
        row = self.conn.execute(
            "SELECT decision, partner_decision FROM scoring_log WHERE application_id=?",
            (application_id,),
        ).fetchone()
        if not row:
            raise LookupError("Application not found")
        if row[1] and row[1] != "pending":
            raise ValueError("Partner outcome is already recorded")
        agreement = None
        if decision != "pending":
            engine = str(row[0]).upper()
            if engine == "AUTO_APPROVE":
                agreement = int(decision == "approved")
            elif engine == "DECLINE":
                agreement = int(decision == "declined")
        when = decision_at or datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE scoring_log SET partner_decision=?, partner_reason=?, "
            "partner_decision_at=?, recommendation_agreement=? WHERE application_id=?",
            (decision, reason[:2000], when, agreement, application_id),
        )
        self._append_audit(
            application_id,
            "partner_decision_recorded",
            actor,
            {
                "partner_decision": decision,
                "partner_reason": reason[:2000],
                "partner_decision_at": when,
                "recommendation_agreement": agreement,
            },
        )
        self.conn.commit()
        return {
            "application_id": application_id,
            "partner_decision": decision,
            "partner_reason": reason[:2000],
            "partner_decision_at": when,
            "recommendation_agreement": agreement,
        }

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
