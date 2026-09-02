"""Pre-scoring intake state machine for hosted bank-linking adapters."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import sqlite3
from typing import Any
from uuid import uuid4

from .api.cases import create_case
from .models import BankData
from .store import ScoringLog
from .bank_ingestion import IdempotencyConflict, _assert_same_event
from .config import is_production


OPEN_STATES = frozenset({"created", "consented", "link_pending", "evidence_ready"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append(log: ScoringLog, intake_id: str, event_type: str, actor: str, payload: dict) -> None:
    log.conn.execute(
        "INSERT INTO intake_audit_event "
        "(event_id,intake_id,event_type,actor,occurred_at,payload) VALUES (?,?,?,?,?,?)",
        (uuid4().hex, intake_id, event_type, str(actor)[:120], _now().isoformat(),
         json.dumps(payload, ensure_ascii=False, default=str)),
    )


def _clean(value: Any, name: str, minimum: int, maximum: int) -> str:
    text = str(value or "").strip()
    if not minimum <= len(text) <= maximum:
        raise ValueError(f"{name} must contain {minimum} to {maximum} characters")
    return text


def create_intake(db_path: str, payload: dict[str, Any], actor: str) -> dict:
    partner_ref = _clean(payload.get("partner_case_reference"), "partner_case_reference", 3, 120)
    cohort_id = _clean(payload.get("cohort_id"), "cohort_id", 3, 120)
    merchant_name = _clean(payload.get("merchant_name"), "merchant_name", 2, 160)
    intake_id = uuid4().hex
    when = _now().isoformat()
    with ScoringLog(db_path) as log:
        try:
            log.conn.execute(
                "INSERT INTO intake "
                "(intake_id,owner_actor,partner_case_reference,cohort_id,merchant_name,status,"
                "created_at,updated_at) VALUES (?,?,?,?,?,'created',?,?)",
                (intake_id, str(actor)[:120], partner_ref, cohort_id, merchant_name, when, when),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("partner_case_reference already exists for this partner") from exc
        _append(log, intake_id, "intake_created", actor,
                {"partner_case_reference": partner_ref, "cohort_id": cohort_id})
        log.conn.commit()
    return {"intake_id": intake_id, "status": "created", "created_at": when}


def record_consent(
    db_path: str, intake_id: str, payload: dict[str, Any], actor: str,
) -> dict:
    if is_production() and os.getenv("OLIN_ALLOW_LEGACY_CONSENT", "").strip() != "1":
        raise PermissionError(
            "Direct consent capture is disabled; use a versioned consent challenge"
        )
    channel = str(payload.get("channel", "")).strip().lower()
    text = _clean(payload.get("text"), "text", 10, 20_000)
    policy_version = _clean(payload.get("policy_version"), "policy_version", 1, 40)
    if channel not in ("whatsapp", "sms", "in_person"):
        raise ValueError("channel must be whatsapp, sms, or in_person")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    consent_id = uuid4().hex
    when = _now().isoformat()
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT status FROM intake WHERE intake_id=? AND owner_actor=?",
            (intake_id, actor),
        ).fetchone()
        if not row:
            raise LookupError("Intake not found")
        if row[0] not in OPEN_STATES:
            raise ValueError("Consent cannot be changed after scoring or cancellation")
        log.conn.execute(
            "UPDATE intake_consent SET status='superseded' "
            "WHERE intake_id=? AND status='active'", (intake_id,),
        )
        log.conn.execute(
            "UPDATE intake_link_session SET status='cancelled' "
            "WHERE intake_id=? AND status='active'", (intake_id,),
        )
        log.conn.execute(
            "INSERT INTO intake_consent "
            "(consent_id,intake_id,purpose,policy_version,text_sha256,channel,status,"
            "captured_at,captured_by) VALUES (?,?,'credit_assessment',?,?,?,'active',?,?)",
            (consent_id, intake_id, policy_version, digest, channel, when, str(actor)[:120]),
        )
        log.conn.execute(
            "UPDATE intake SET status='consented',updated_at=? WHERE intake_id=?",
            (when, intake_id),
        )
        _append(log, intake_id, "intake_consent_recorded", actor,
                {"consent_id": consent_id, "policy_version": policy_version,
                 "text_sha256": digest, "channel": channel})
        log.conn.commit()
    return {"consent_id": consent_id, "status": "active", "text_sha256": digest,
            "policy_version": policy_version, "captured_at": when}


def create_link_session(
    db_path: str, intake_id: str, provider: str, actor: str, ttl_minutes: int = 15,
) -> dict:
    provider = str(provider).strip().lower()
    if not provider or len(provider) > 64 or not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider is invalid")
    if not 5 <= ttl_minutes <= 30:
        raise ValueError("ttl_minutes must be between 5 and 30")
    now = _now()
    expires = now + timedelta(minutes=ttl_minutes)
    link_session_id = uuid4().hex
    client_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(client_token.encode("utf-8")).hexdigest()
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT i.status,c.consent_id FROM intake i "
            "JOIN intake_consent c ON c.intake_id=i.intake_id AND c.status='active' "
            "AND c.purpose='provider_access' AND c.provider=? "
            "WHERE i.intake_id=? AND i.owner_actor=? AND EXISTS "
            "(SELECT 1 FROM intake_consent a WHERE a.intake_id=i.intake_id "
            "AND a.purpose='credit_assessment' AND a.status='active')",
            (provider, intake_id, actor),
        ).fetchone()
        if not row and os.getenv("OLIN_ALLOW_LEGACY_CONSENT", "").strip() == "1":
            row = log.conn.execute(
                "SELECT i.status,c.consent_id FROM intake i JOIN intake_consent c "
                "ON c.intake_id=i.intake_id AND c.status='active' "
                "WHERE i.intake_id=? AND i.owner_actor=?",
                (intake_id, actor),
            ).fetchone()
        if not row:
            raise LookupError(
                "Active credit_assessment and matching provider_access consents are required"
            )
        if row[0] not in ("consented", "link_pending"):
            raise ValueError("Intake is not ready to create a link session")
        log.conn.execute(
            "UPDATE intake_link_session SET status='cancelled' "
            "WHERE intake_id=? AND status='active'", (intake_id,),
        )
        log.conn.execute(
            "INSERT INTO intake_link_session "
            "(link_session_id,intake_id,consent_id,provider,token_sha256,status,created_at,expires_at) "
            "VALUES (?,?,?,?,?,'active',?,?)",
            (link_session_id, intake_id, row[1], provider, token_hash,
             now.isoformat(), expires.isoformat()),
        )
        log.conn.execute(
            "UPDATE intake SET status='link_pending',updated_at=? WHERE intake_id=?",
            (now.isoformat(), intake_id),
        )
        _append(log, intake_id, "link_session_created", actor,
                {"link_session_id": link_session_id, "provider": provider,
                 "expires_at": expires.isoformat()})
        log.conn.commit()
    return {"link_session_id": link_session_id, "client_token": client_token,
            "provider": provider, "status": "active", "expires_at": expires.isoformat()}


def withdraw_consent(
    db_path: str, intake_id: str, consent_id: str, reason: str, actor: str,
) -> dict:
    from .consent_flow import withdraw_consent as withdraw_purpose_consent
    return withdraw_purpose_consent(
        db_path, intake_id=intake_id, consent_id=consent_id,
        reason=reason, owner_actor=actor,
    )


def exchange_link_token(db_path: str, client_token: str) -> dict:
    """Consume the one-time browser bootstrap token for a provider adapter."""
    token = str(client_token).strip()
    if len(token) < 32:
        raise PermissionError("Link token is invalid")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _now()
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT link_session_id,intake_id,consent_id,provider,status,expires_at "
            "FROM intake_link_session WHERE token_sha256=?", (digest,),
        ).fetchone()
        if not row:
            raise PermissionError("Link token is invalid or already used")
        expires = datetime.fromisoformat(row[5].replace("Z", "+00:00"))
        if row[4] != "active" or expires <= now:
            if row[4] == "active":
                log.conn.execute(
                    "UPDATE intake_link_session SET status='expired' WHERE link_session_id=?",
                    (row[0],),
                )
                log.conn.commit()
            raise PermissionError("Link token is expired or inactive")
        consumed_hash = "used:" + secrets.token_hex(32)
        changed = log.conn.execute(
            "UPDATE intake_link_session SET token_sha256=?,launched_at=? "
            "WHERE link_session_id=? AND token_sha256=? AND status='active'",
            (consumed_hash, now.isoformat(), row[0], digest),
        )
        if changed.rowcount != 1:
            raise PermissionError("Link token is invalid or already used")
        _append(log, row[1], "link_session_launched", "link_adapter",
                {"link_session_id": row[0], "provider": row[3]})
        log.conn.commit()
    return {
        "link_session_id": row[0], "intake_id": row[1], "consent_id": row[2],
        "provider": row[3], "expires_at": row[5],
        "callback_path": "/api/v1/webhooks/bank-evidence",
    }


def ingest_bank_metrics(
    db_path: str, payload: dict[str, Any], bank: BankData, raw: bytes,
    actor: str = "bank_webhook",
) -> dict:
    intake_id = str(payload.get("intake_id", ""))
    link_session_id = str(payload.get("link_session_id", ""))
    consent_id = str(payload.get("consent_id", ""))
    if not link_session_id:
        raise ValueError("link_session_id is required for intake evidence")
    now = _now()
    digest = hashlib.sha256(raw).hexdigest()
    event_id = str(payload["event_id"])
    with ScoringLog(db_path) as log:
        duplicate = log.conn.execute(
            "SELECT intake_id,link_session_id,provider,connection_id,consent_id,payload_sha256 "
            "FROM intake_bank_event WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if duplicate:
            if duplicate[0] != intake_id:
                raise PermissionError("Event ID is already bound to another intake")
            _assert_same_event(
                duplicate,
                (intake_id, link_session_id, bank.source,
                 str(payload["connection_id"]), consent_id, digest),
                event_id,
            )
            return {"duplicate": True, "event_id": event_id,
                    "intake_id": intake_id}
        row = log.conn.execute(
            "SELECT s.status,s.expires_at,s.provider,s.consent_id,c.status,i.status "
            "FROM intake_link_session s "
            "JOIN intake_consent c ON c.consent_id=s.consent_id "
            "JOIN intake i ON i.intake_id=s.intake_id "
            "WHERE s.link_session_id=? AND s.intake_id=?",
            (link_session_id, intake_id),
        ).fetchone()
        if not row:
            raise PermissionError("Link session does not match this intake")
        expires = datetime.fromisoformat(row[1].replace("Z", "+00:00"))
        if row[0] != "active" or expires <= now:
            if row[0] == "active":
                log.conn.execute(
                    "UPDATE intake_link_session SET status='expired' WHERE link_session_id=?",
                    (link_session_id,),
                )
                log.conn.commit()
            raise PermissionError("Link session is expired or inactive")
        if row[2] != bank.source or row[3] != consent_id or row[4] != "active":
            raise PermissionError("Provider or active consent does not match link session")
        if row[5] != "link_pending":
            raise PermissionError("Intake is not waiting for bank evidence")
        received = now.isoformat()
        try:
            log.conn.execute(
                "INSERT INTO intake_bank_event "
                "(event_id,intake_id,link_session_id,provider,connection_id,consent_id,"
                "payload_sha256,derived_metrics,observed_at,received_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_id, intake_id, link_session_id, bank.source,
                 str(payload["connection_id"]), consent_id, digest,
                 json.dumps(bank.__dict__, ensure_ascii=False, sort_keys=True),
                 bank.observed_at, received),
            )
        except sqlite3.IntegrityError:
            log.conn.rollback()
            existing = log.conn.execute(
                "SELECT intake_id,link_session_id,provider,connection_id,consent_id,payload_sha256 "
                "FROM intake_bank_event WHERE event_id=?", (event_id,),
            ).fetchone()
            if not existing:
                raise
            _assert_same_event(
                existing,
                (intake_id, link_session_id, bank.source,
                 str(payload["connection_id"]), consent_id, digest),
                event_id,
            )
            return {"duplicate": True, "event_id": event_id,
                    "intake_id": intake_id}
        log.conn.execute(
            "UPDATE intake_link_session SET status='completed',completed_at=? "
            "WHERE link_session_id=?", (received, link_session_id),
        )
        log.conn.execute(
            "UPDATE intake SET status='evidence_ready',updated_at=? WHERE intake_id=?",
            (received, intake_id),
        )
        _append(log, intake_id, "intake_bank_evidence_ingested", actor,
                {"event_id": event_id, "provider": bank.source,
                 "consent_id": consent_id, "link_session_id": link_session_id})
        log.conn.commit()
    return {"duplicate": False, "event_id": event_id,
            "intake_id": intake_id, "bank": bank.__dict__}


def get_intake(db_path: str, intake_id: str, owner_actor: str | None = None) -> dict | None:
    with ScoringLog(db_path) as log:
        log.conn.row_factory = sqlite3.Row
        row = log.conn.execute(
            "SELECT * FROM intake WHERE intake_id=? AND (? IS NULL OR owner_actor=?)",
            (intake_id, owner_actor, owner_actor),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        consents = log.conn.execute(
            "SELECT consent_id,purpose,policy_version,text_sha256,channel,status,captured_at "
            "FROM intake_consent WHERE intake_id=? ORDER BY captured_at DESC",
            (intake_id,),
        ).fetchall()
        evidence = log.conn.execute(
            "SELECT event_id,provider,connection_id,consent_id,derived_metrics,observed_at,received_at "
            "FROM intake_bank_event WHERE intake_id=? ORDER BY received_at DESC LIMIT 1",
            (intake_id,),
        ).fetchone()
        result["consents"] = [dict(consent) for consent in consents]
        result["consent"] = result["consents"][0] if result["consents"] else None
        result["bank_evidence"] = None
        if evidence:
            item = dict(evidence)
            item["bank"] = json.loads(item.pop("derived_metrics"))
            result["bank_evidence"] = item
        result["audit"] = [
            dict(item) for item in log.conn.execute(
                "SELECT event_type,actor,occurred_at,payload FROM intake_audit_event "
                "WHERE intake_id=? ORDER BY occurred_at", (intake_id,),
            ).fetchall()
        ]
        log.conn.row_factory = None
        return result


def score_intake(
    db_path: str, intake_id: str, application_payload: dict[str, Any], actor: str,
) -> dict:
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT merchant_name,partner_case_reference,cohort_id,status FROM intake "
            "WHERE intake_id=? AND owner_actor=?", (intake_id, actor),
        ).fetchone()
        consent = log.conn.execute(
            "SELECT consent_id,policy_version,text_sha256,channel FROM intake_consent "
            "WHERE intake_id=? AND purpose='credit_assessment' AND status='active' "
            "ORDER BY captured_at DESC LIMIT 1",
            (intake_id,),
        ).fetchone()
        provider_consent = log.conn.execute(
            "SELECT 1 FROM intake_bank_event e JOIN intake_consent c "
            "ON c.consent_id=e.consent_id WHERE e.intake_id=? "
            "AND c.purpose='provider_access' AND c.status='active'",
            (intake_id,),
        ).fetchone()
        bureau_consent = log.conn.execute(
            "SELECT 1 FROM intake_consent WHERE intake_id=? AND purpose='credit_bureau' "
            "AND status='active'", (intake_id,),
        ).fetchone()
        evidence = log.conn.execute(
            "SELECT derived_metrics FROM intake_bank_event WHERE intake_id=? "
            "ORDER BY received_at DESC LIMIT 1", (intake_id,),
        ).fetchone()
        if not row:
            raise LookupError("Intake not found")
        legacy_allowed = os.getenv("OLIN_ALLOW_LEGACY_CONSENT", "").strip() == "1"
        if row[3] != "evidence_ready" or not consent or not evidence or (
            not provider_consent and not legacy_allowed
        ):
            raise ValueError(
                "Intake requires active assessment/provider consents and bank evidence before scoring"
            )
        if bool((application_payload.get("buro") or {}).get("checked")) and not (
            bureau_consent or legacy_allowed
        ):
            raise ValueError("A separate active credit_bureau consent is required")
        claimed = log.conn.execute(
            "UPDATE intake SET status='scoring',updated_at=? "
            "WHERE intake_id=? AND status='evidence_ready'",
            (_now().isoformat(), intake_id),
        )
        if claimed.rowcount != 1:
            raise ValueError("Intake is already being scored")
        log.conn.commit()
    body = dict(application_payload)
    body.update({
        "merchant_name": row[0],
        "partner_case_reference": row[1],
        "cohort_id": row[2],
        "case_mode": "shadow",
        "evidence_route": "bank_flow_led",
        "bank": json.loads(evidence[0]),
        "consent": {
            "channel": consent[3], "text_sha256": consent[2],
            "policy_version": consent[1], "purpose": "credit_assessment",
        },
    })
    try:
        created = create_case(body, db_path, actor=actor, verified_consent=True)
    except BaseException:
        with ScoringLog(db_path) as log:
            log.conn.execute(
                "UPDATE intake SET status='evidence_ready',updated_at=? "
                "WHERE intake_id=? AND status='scoring'", (_now().isoformat(), intake_id),
            )
            log.conn.commit()
        raise
    with ScoringLog(db_path) as log:
        when = _now().isoformat()
        log.conn.execute(
            "UPDATE intake SET status='scored',scored_application_id=?,updated_at=? "
            "WHERE intake_id=? AND status='scoring'",
            (created["application_id"], when, intake_id),
        )
        _append(log, intake_id, "intake_scored", actor,
                {"application_id": created["application_id"],
                 "recommendation": created["recommendation"]})
        log.conn.commit()
    created["intake_id"] = intake_id
    return created
