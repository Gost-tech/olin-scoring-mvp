"""Provider-neutral, consent-bound bank evidence ingestion.

Bank adapters should translate their callback into this small contract. Olin
stores only derived metrics and callback fingerprints, never credentials or
raw transaction rows.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import sqlite3
from typing import Any, Iterable

from .models import BankData
from .store import ScoringLog


REQUIRED_FIELDS = frozenset(
    {"event_id", "provider", "connection_id", "consent_id",
     "observed_at", "metrics"}
)
FORBIDDEN_KEYS = frozenset(
    {"password", "passcode", "pin", "access_token", "refresh_token", "credential",
     "credentials", "account_number", "clabe", "transactions"}
)
METRIC_FIELDS = frozenset(
    {"months_connected", "avg_daily_balance_mxn", "monthly_deposit_count",
     "monthly_deposit_volume_mxn", "monthly_outflow_volume_mxn",
     "deposit_regularity", "overdrafts_90d", "balance_trend_90d",
     "min_daily_balance_mxn"}
)


class IdempotencyConflict(ValueError):
    """An event identifier was reused for a different signed payload."""


def provider_webhook_secrets(provider: str, fallback: str = "") -> tuple[str, ...]:
    """Return active and retiring signing secrets for one provider.

    ``OLIN_BANK_WEBHOOK_SECRETS`` is a JSON object whose values may be one
    secret or a list ordered current-first. This supports per-bank isolation
    and overlap during rotation. The legacy single secret remains available
    only as a one-bank compatibility fallback.
    """
    normalized = str(provider or "").strip().lower()
    raw = os.getenv("OLIN_BANK_WEBHOOK_SECRETS", "").strip()
    if raw:
        try:
            configured = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OLIN_BANK_WEBHOOK_SECRETS must be valid JSON") from exc
        if not isinstance(configured, dict):
            raise RuntimeError("OLIN_BANK_WEBHOOK_SECRETS must be a JSON object")
        value = configured.get(normalized)
        candidates = value if isinstance(value, list) else [value]
        secrets = tuple(str(item).strip() for item in candidates if item)
        if secrets:
            return secrets
        return ()
    secret = str(fallback or "").strip()
    return (secret,) if secret else ()


def sign_payload(raw: bytes, secret: str) -> str:
    if not secret:
        raise ValueError("Bank webhook secret is required")
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def verify_signature(raw: bytes, supplied: str, secret: str | Iterable[str]) -> bool:
    secrets = (secret,) if isinstance(secret, str) else tuple(secret)
    if not supplied or not secrets:
        return False
    candidate = supplied if supplied.startswith("sha256=") else "sha256=" + supplied
    # Evaluate every configured key so the match position is not revealed.
    matches = [
        hmac.compare_digest(candidate, sign_payload(raw, item))
        for item in secrets if item
    ]
    return bool(sum(matches))


def _assert_same_event(
    existing: tuple[Any, ...], expected: tuple[Any, ...], event_id: str,
) -> None:
    if tuple(existing) != tuple(expected):
        raise IdempotencyConflict(
            f"event_id {event_id!r} is already bound to a different payload"
        )


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in FORBIDDEN_KEYS or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def normalize_payload(payload: dict[str, Any], *, max_age_hours: int = 48) -> BankData:
    missing = sorted(REQUIRED_FIELDS - payload.keys())
    if missing:
        raise ValueError("Missing bank fields: " + ", ".join(missing))
    targets = [name for name in ("application_id", "intake_id") if payload.get(name)]
    if len(targets) != 1:
        raise ValueError("Exactly one of application_id or intake_id is required")
    if _contains_forbidden_key(payload):
        raise ValueError("Raw credentials, account identifiers and transactions are forbidden")
    provider = str(payload["provider"]).strip().lower()
    if not provider or len(provider) > 64 or not provider.replace("-", "").replace("_", "").isalnum():
        raise ValueError("provider is invalid")
    for name in ("event_id", targets[0], "connection_id", "consent_id"):
        value = str(payload[name]).strip()
        if not value or len(value) > 160:
            raise ValueError(f"{name} is invalid")
    try:
        observed = datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    if age_seconds < -300 or age_seconds > max_age_hours * 3600:
        raise ValueError("Bank evidence timestamp is outside the accepted freshness window")
    metrics = payload["metrics"]
    if not isinstance(metrics, dict) or set(metrics) - METRIC_FIELDS:
        raise ValueError("metrics contains unsupported fields")
    bank = BankData(**metrics)
    if bank.months_connected < 0 or bank.monthly_deposit_count < 0:
        raise ValueError("Bank history and counts cannot be negative")
    if not 0 <= bank.deposit_regularity <= 1:
        raise ValueError("deposit_regularity must be between 0 and 1")
    if not -1 <= bank.balance_trend_90d <= 1:
        raise ValueError("balance_trend_90d must be between -1 and 1")
    if bank.overdrafts_90d < 0:
        raise ValueError("overdrafts_90d cannot be negative")
    bank.source = provider
    bank.verified = True
    bank.evidence_reference = f"{provider}:{payload['connection_id']}:{payload['event_id']}"
    bank.observed_at = observed.astimezone(timezone.utc).isoformat()
    return bank


def ingest_verified_metrics(
    db_path: str, payload: dict[str, Any], raw: bytes, signature: str,
    secret: str | Iterable[str],
    *, actor: str = "bank_webhook",
) -> dict[str, Any]:
    """Verify, consent-check and idempotently register derived bank metrics."""
    if not verify_signature(raw, signature, secret):
        raise PermissionError("Invalid bank webhook signature")
    try:
        if json.loads(raw) != payload:
            raise ValueError("Signed bank body does not match the parsed payload")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Signed bank body must be valid JSON") from exc
    bank = normalize_payload(payload)
    if payload.get("intake_id"):
        from .intakes import ingest_bank_metrics

        return ingest_bank_metrics(db_path, payload, bank, raw, actor=actor)
    application_id = str(payload["application_id"])
    consent_id = str(payload["consent_id"])
    digest = hashlib.sha256(raw).hexdigest()
    event_id = str(payload["event_id"])
    with ScoringLog(db_path) as log:
        active = log.conn.execute(
            "SELECT 1 FROM consent_record WHERE consent_id=? AND application_id=? "
            "AND status='active' AND purpose='credit_assessment'",
            (consent_id, application_id),
        ).fetchone()
        if active is None:
            raise PermissionError("Active consent does not match this application")
        expected_event = (
            application_id, bank.source, str(payload["connection_id"]),
            consent_id, digest,
        )
        existing = log.conn.execute(
            "SELECT application_id,provider,connection_id,consent_id,payload_sha256 "
            "FROM bank_ingestion_event WHERE event_id=?", (event_id,),
        ).fetchone()
        if existing:
            _assert_same_event(existing, expected_event, event_id)
            return {"duplicate": True, "event_id": event_id}
        received_at = datetime.now(timezone.utc).isoformat()
        try:
            log.conn.execute(
                "INSERT INTO bank_ingestion_event "
                "(event_id,application_id,provider,connection_id,consent_id,payload_sha256,"
                "derived_metrics,observed_at,received_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (event_id, application_id, bank.source,
                 str(payload["connection_id"]), consent_id, digest,
                 json.dumps(bank.__dict__, ensure_ascii=False, sort_keys=True),
                 bank.observed_at, received_at),
            )
        except sqlite3.IntegrityError:
            log.conn.rollback()
            existing = log.conn.execute(
                "SELECT application_id,provider,connection_id,consent_id,payload_sha256 "
                "FROM bank_ingestion_event WHERE event_id=?", (event_id,),
            ).fetchone()
            if not existing:
                raise
            _assert_same_event(existing, expected_event, event_id)
            return {"duplicate": True, "event_id": event_id}
        log._append_audit(
            application_id, "bank_evidence_ingested", actor,
            {"event_id": str(payload["event_id"]), "provider": bank.source,
             "consent_id": consent_id, "evidence_reference": bank.evidence_reference},
        )
        log.conn.commit()
    return {"duplicate": False, "event_id": event_id, "bank": bank.__dict__}


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Serialize a test/adapter payload exactly as the signed webhook body."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
