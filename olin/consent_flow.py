"""Versioned, purpose-specific consent challenges for hosted shadow intakes.

This is an engineering evidence system, not approved Mexican legal wording.
Policies are immutable snapshots; real modes accept only policies carrying
recorded legal, privacy, and partner approvals. OTP delivery is replaceable and
the built-in synthetic dispatcher is unavailable in pilot/production.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from typing import Any, Protocol
from uuid import uuid4

from .config import is_production
from .source_trust import assess_source
from .store import ScoringLog


PURPOSES = frozenset({"credit_assessment", "provider_access", "credit_bureau"})
CHANNELS = frozenset({"sms", "whatsapp", "email"})
AUTHORITY_TYPES = frozenset({
    "individual_business_ownership_verified",
    "legal_representative_authority_verified",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _clean(value: Any, field: str, minimum: int, maximum: int) -> str:
    text = str(value or "").strip()
    if not minimum <= len(text) <= maximum:
        raise ValueError(f"{field} must contain {minimum} to {maximum} characters")
    return text


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _secret() -> bytes:
    value = os.getenv("OLIN_CONSENT_OTP_SECRET", "").strip()
    if is_production() and len(value) < 32:
        raise RuntimeError("OLIN_CONSENT_OTP_SECRET must contain at least 32 characters")
    return (value or "synthetic-uat-only-consent-secret").encode("utf-8")


def _fingerprint(label: str, value: str) -> str:
    return hmac.new(_secret(), f"{label}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _otp_digest(challenge_id: str, otp: str) -> str:
    return _fingerprint("otp", f"{challenge_id}:{otp}")


def _append(log: ScoringLog, intake_id: str, event_type: str, actor: str, payload: dict) -> None:
    log.conn.execute(
        "INSERT INTO intake_audit_event "
        "(event_id,intake_id,event_type,actor,occurred_at,payload) VALUES (?,?,?,?,?,?)",
        (uuid4().hex, intake_id, event_type, str(actor)[:120], _now().isoformat(),
         _canonical(payload)),
    )


class OtpDispatcher(Protocol):
    expose_test_code: bool

    def send(self, *, channel: str, destination: str, otp: str, challenge_id: str) -> str:
        """Deliver the code and return an opaque provider transaction reference."""


class SyntheticOtpDispatcher:
    expose_test_code = True

    def send(self, *, channel: str, destination: str, otp: str, challenge_id: str) -> str:
        if is_production():
            raise RuntimeError("Synthetic OTP is disabled in pilot and production modes")
        return f"synthetic-delivery:{challenge_id}"


class UnconfiguredOtpDispatcher:
    expose_test_code = False

    def send(self, *, channel: str, destination: str, otp: str, challenge_id: str) -> str:
        raise RuntimeError("No approved OTP or e-signature provider is configured")


def configured_otp_dispatcher() -> OtpDispatcher:
    if not is_production() and os.getenv("OLIN_CONSENT_OTP_MODE", "synthetic").lower() == "synthetic":
        return SyntheticOtpDispatcher()
    return UnconfiguredOtpDispatcher()


def register_policy(
    db_path: str,
    *,
    policy_id: str,
    owner_actor: str,
    purpose: str,
    provider: str,
    policy_version: str,
    notice_version: str,
    language: str,
    text: str,
    privacy_notice_url: str,
    retention_summary: str,
    status: str,
    created_by: str,
    legal_approval_ref: str = "",
    privacy_approval_ref: str = "",
    partner_approval_ref: str = "",
) -> dict[str, Any]:
    """Register one immutable policy snapshot through an internal admin process."""
    policy_id = _clean(policy_id, "policy_id", 3, 120)
    owner_actor = _clean(owner_actor, "owner_actor", 1, 120)
    purpose = str(purpose or "").strip().lower()
    if purpose not in PURPOSES:
        raise ValueError("purpose is not supported")
    provider = str(provider or "").strip().lower()
    if purpose in {"provider_access", "credit_bureau"} and not provider:
        raise ValueError("provider is required for provider_access and credit_bureau")
    if purpose == "credit_assessment" and provider:
        raise ValueError("credit_assessment policy cannot be provider-specific")
    if provider and not re.fullmatch(r"[a-z0-9_-]{2,64}", provider):
        raise ValueError("provider is invalid")
    policy_version = _clean(policy_version, "policy_version", 1, 80)
    notice_version = _clean(notice_version, "notice_version", 1, 80)
    language = _clean(language, "language", 2, 16)
    text = _clean(text, "text", 20, 20_000)
    privacy_notice_url = _clean(privacy_notice_url, "privacy_notice_url", 8, 500)
    retention_summary = _clean(retention_summary, "retention_summary", 10, 1000)
    status = str(status or "").strip().lower()
    if status not in {"synthetic_uat", "approved"}:
        raise ValueError("new policy status must be synthetic_uat or approved")
    approvals = [
        str(legal_approval_ref or "").strip(),
        str(privacy_approval_ref or "").strip(),
        str(partner_approval_ref or "").strip(),
    ]
    if status == "synthetic_uat" and is_production():
        raise PermissionError("Synthetic consent policies are disabled in real modes")
    if status == "approved":
        if not all(approvals):
            raise ValueError("approved policies require legal, privacy, and partner approval references")
        if not privacy_notice_url.startswith("https://"):
            raise ValueError("approved privacy_notice_url must use HTTPS")
        lowered = text.lower()
        if "[" in text or "borrador" in lowered or "placeholder" in lowered:
            raise ValueError("approved policy text cannot contain draft placeholders")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    when = _now().isoformat()
    created_by = _clean(created_by, "created_by", 1, 120)
    values = (
        policy_id, owner_actor, purpose, provider, policy_version, notice_version,
        language, text, digest, privacy_notice_url, retention_summary, status,
        approvals[0], approvals[1], approvals[2], when, created_by,
    )
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        existing = log.conn.execute(
            "SELECT * FROM consent_policy WHERE policy_id=?", (policy_id,),
        ).fetchone()
        if existing:
            fields = (
                "policy_id", "owner_actor", "purpose", "provider", "policy_version",
                "notice_version", "language", "text_snapshot", "text_sha256",
                "privacy_notice_url", "retention_summary", "status",
                "legal_approval_ref", "privacy_approval_ref", "partner_approval_ref",
            )
            if any(str(existing[field]) != str(value) for field, value in zip(fields, values[:15])):
                raise ValueError("policy_id conflicts with an immutable policy snapshot")
            return {"policy_id": policy_id, "text_sha256": digest, "duplicate": True}
        log.conn.execute(
            "INSERT INTO consent_policy "
            "(policy_id,owner_actor,purpose,provider,policy_version,notice_version,language,"
            "text_snapshot,text_sha256,privacy_notice_url,retention_summary,status,"
            "legal_approval_ref,privacy_approval_ref,partner_approval_ref,created_at,created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values,
        )
        log.conn.commit()
    return {"policy_id": policy_id, "text_sha256": digest, "duplicate": False}


def list_policies(db_path: str, *, owner_actor: str) -> list[dict[str, Any]]:
    """List non-retired snapshots for the authenticated institution actor."""
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        rows = log.conn.execute(
            "SELECT policy_id,purpose,provider,policy_version,notice_version,language,"
            "text_snapshot,text_sha256,privacy_notice_url,retention_summary,status "
            "FROM consent_policy WHERE owner_actor=? AND status!='retired' "
            "ORDER BY purpose,provider,policy_version",
            (owner_actor,),
        ).fetchall()
        return [dict(row) for row in rows]


def register_intake_binding(
    db_path: str,
    *,
    intake_id: str,
    owner_actor: str,
    evidence_type: str,
    source_id: str,
    source_reference: str,
    subject_hash: str,
    observed_at: str,
    expires_at: str,
    created_by: str,
    binding_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attach a bank/provider-attested identity or authority reference to an intake."""
    allowed = {"government_identity_verified", *AUTHORITY_TYPES}
    evidence_type = str(evidence_type or "").strip().lower()
    if evidence_type not in allowed:
        raise ValueError("binding evidence_type is not supported")
    source_id = _clean(source_id, "source_id", 2, 120).lower()
    trust = assess_source(source_id, evidence_type)
    if not trust.trusted:
        raise PermissionError(f"binding source is not trusted: {trust.reason}")
    subject_hash = str(subject_hash or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", subject_hash):
        raise ValueError("subject_hash must be a 64-character digest")
    observed = _parse(observed_at, "observed_at")
    expires = _parse(expires_at, "expires_at")
    current = (now or _now()).astimezone(timezone.utc)
    if observed > current or expires <= current or expires <= observed:
        raise ValueError("binding timestamps are not current")
    binding_id = _clean(binding_id or uuid4().hex, "binding_id", 3, 120)
    source_reference = _clean(source_reference, "source_reference", 3, 240)
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT 1 FROM intake WHERE intake_id=? AND owner_actor=?",
            (intake_id, owner_actor),
        ).fetchone()
        if not row:
            raise LookupError("Intake not found")
        log.conn.execute(
            "INSERT INTO intake_identity_binding "
            "(binding_id,intake_id,owner_actor,evidence_type,source_id,source_reference,"
            "subject_hash,attestation_id,status,observed_at,expires_at,created_at,created_by) "
            "VALUES (?,?,?,?,?,?,?,?,'verified',?,?,?,?)",
            (
                binding_id, intake_id, owner_actor, evidence_type, source_id,
                source_reference, subject_hash, trust.attestation_id,
                observed.isoformat(), expires.isoformat(), current.isoformat(), created_by,
            ),
        )
        _append(log, intake_id, "intake_identity_binding_registered", created_by, {
            "binding_id": binding_id, "evidence_type": evidence_type,
            "source_id": source_id, "source_reference": source_reference,
            "subject_hash": subject_hash, "attestation_id": trust.attestation_id,
            "expires_at": expires.isoformat(),
        })
        log.conn.commit()
    return {"binding_id": binding_id, "evidence_type": evidence_type, "status": "verified"}


def _validated_binding(
    log: ScoringLog, *, binding_id: str, intake_id: str, owner_actor: str,
    expected: set[str], now: datetime,
) -> sqlite3.Row | Any:
    row = log.conn.execute(
        "SELECT * FROM intake_identity_binding WHERE binding_id=? AND intake_id=? "
        "AND owner_actor=?", (binding_id, intake_id, owner_actor),
    ).fetchone()
    if not row or str(row["status"]) != "verified":
        raise PermissionError("Required identity or authority binding is unavailable")
    if str(row["evidence_type"]) not in expected:
        raise PermissionError("Identity or authority binding has the wrong evidence type")
    if _parse(str(row["expires_at"]), "expires_at") <= now:
        raise PermissionError("Identity or authority binding is expired")
    trust = assess_source(str(row["source_id"]), str(row["evidence_type"]))
    if not trust.trusted or trust.attestation_id != str(row["attestation_id"]):
        raise PermissionError("Identity or authority binding source is no longer trusted")
    return row


def issue_challenge(
    db_path: str,
    *,
    intake_id: str,
    owner_actor: str,
    policy_id: str,
    channel: str,
    destination: str,
    identity_binding_id: str,
    authority_binding_id: str,
    dispatcher: OtpDispatcher | None = None,
    ttl_minutes: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Issue one unbundled consent challenge and deliver a one-time code."""
    channel = str(channel or "").strip().lower()
    if channel not in CHANNELS:
        raise ValueError("channel must be sms, whatsapp, or email")
    destination = _clean(destination, "destination", 5, 320)
    if not 2 <= ttl_minutes <= 10:
        raise ValueError("ttl_minutes must be between 2 and 10")
    current = (now or _now()).astimezone(timezone.utc)
    expires = current + timedelta(minutes=ttl_minutes)
    challenge_id = uuid4().hex
    public_token = secrets.token_urlsafe(32)
    otp = f"{secrets.randbelow(1_000_000):06d}"
    dispatcher = dispatcher or configured_otp_dispatcher()

    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        intake = log.conn.execute(
            "SELECT status FROM intake WHERE intake_id=? AND owner_actor=?",
            (intake_id, owner_actor),
        ).fetchone()
        if not intake:
            raise LookupError("Intake not found")
        if str(intake["status"]) not in {"created", "consented", "link_pending", "evidence_ready"}:
            raise ValueError("Consent cannot be changed in this intake state")
        policy = log.conn.execute(
            "SELECT * FROM consent_policy WHERE policy_id=? AND owner_actor=?",
            (policy_id, owner_actor),
        ).fetchone()
        if not policy or str(policy["status"]) == "retired":
            raise LookupError("Active consent policy not found")
        if is_production() and str(policy["status"]) != "approved":
            raise PermissionError("Real modes require an approved consent policy")
        identity = _validated_binding(
            log, binding_id=identity_binding_id, intake_id=intake_id,
            owner_actor=owner_actor, expected={"government_identity_verified"}, now=current,
        )
        authority = _validated_binding(
            log, binding_id=authority_binding_id, intake_id=intake_id,
            owner_actor=owner_actor, expected=set(AUTHORITY_TYPES), now=current,
        )
        log.conn.execute(
            "UPDATE consent_challenge SET status='cancelled' WHERE intake_id=? "
            "AND purpose=? AND provider=? AND status='pending'",
            (intake_id, policy["purpose"], policy["provider"]),
        )
        log.conn.execute(
            "INSERT INTO consent_challenge "
            "(challenge_id,intake_id,owner_actor,policy_id,purpose,provider,channel,"
            "destination_hash,identity_reference_hash,authority_reference_hash,"
            "public_token_sha256,otp_hash,status,issued_at,expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
            (
                challenge_id, intake_id, owner_actor, policy_id, policy["purpose"],
                policy["provider"], channel, _fingerprint("destination", destination),
                str(identity["subject_hash"]), str(authority["subject_hash"]),
                hashlib.sha256(public_token.encode("utf-8")).hexdigest(),
                _otp_digest(challenge_id, otp), current.isoformat(), expires.isoformat(),
            ),
        )
        _append(log, intake_id, "consent_challenge_issued", owner_actor, {
            "challenge_id": challenge_id, "policy_id": policy_id,
            "purpose": policy["purpose"], "provider": policy["provider"],
            "channel": channel, "identity_binding_id": identity_binding_id,
            "authority_binding_id": authority_binding_id, "expires_at": expires.isoformat(),
        })
        log.conn.commit()

    try:
        dispatch_artifact = dispatcher.send(
            channel=channel, destination=destination, otp=otp, challenge_id=challenge_id,
        )
    except Exception:
        with ScoringLog(db_path) as log:
            log.conn.execute(
                "UPDATE consent_challenge SET status='dispatch_failed' WHERE challenge_id=?",
                (challenge_id,),
            )
            _append(log, intake_id, "consent_challenge_dispatch_failed", "consent_system", {
                "challenge_id": challenge_id, "policy_id": policy_id,
            })
            log.conn.commit()
        raise
    with ScoringLog(db_path) as log:
        log.conn.execute(
            "UPDATE consent_challenge SET dispatch_artifact=? WHERE challenge_id=?",
            (_clean(dispatch_artifact, "dispatch_artifact", 3, 240), challenge_id),
        )
        log.conn.commit()
    response = {
        "challenge_id": challenge_id, "status": "pending", "purpose": str(policy["purpose"]),
        "provider": str(policy["provider"]), "channel": channel,
        "expires_at": expires.isoformat(), "max_attempts": 5,
        "consent_path": f"/consentir#challenge={challenge_id}&token={public_token}",
    }
    if dispatcher.expose_test_code:
        response["test_otp"] = otp
    return response


def _public_challenge_row(
    db_path: str, *, challenge_id: str, access_token: str,
) -> tuple[str, str]:
    token = str(access_token or "").strip()
    if len(token) < 32:
        raise PermissionError("Consent link is invalid")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT intake_id,owner_actor,public_token_sha256 FROM consent_challenge "
            "WHERE challenge_id=?", (challenge_id,),
        ).fetchone()
    if not row or not hmac.compare_digest(str(row[2]), digest):
        raise PermissionError("Consent link is invalid")
    return str(row[0]), str(row[1])


def get_public_challenge(
    db_path: str, *, challenge_id: str, access_token: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the exact policy text for a token-bound applicant link."""
    intake_id, owner_actor = _public_challenge_row(
        db_path, challenge_id=challenge_id, access_token=access_token,
    )
    current = (now or _now()).astimezone(timezone.utc)
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        row = log.conn.execute(
            "SELECT c.status,c.expires_at,c.purpose,c.provider,c.channel,"
            "p.policy_version,p.notice_version,p.language,p.text_snapshot,"
            "p.text_sha256,p.privacy_notice_url,p.retention_summary "
            "FROM consent_challenge c JOIN consent_policy p ON p.policy_id=c.policy_id "
            "WHERE c.challenge_id=? AND c.intake_id=? AND c.owner_actor=?",
            (challenge_id, intake_id, owner_actor),
        ).fetchone()
        if not row:
            raise LookupError("Consent challenge not found")
        status = str(row["status"])
        if status == "pending" and _parse(str(row["expires_at"]), "expires_at") <= current:
            log.conn.execute(
                "UPDATE consent_challenge SET status='expired' WHERE challenge_id=?",
                (challenge_id,),
            )
            log.conn.commit()
            status = "expired"
        return {
            "challenge_id": challenge_id,
            "status": status,
            "expires_at": str(row["expires_at"]),
            "institution": owner_actor,
            "purpose": str(row["purpose"]),
            "provider": str(row["provider"]),
            "channel": str(row["channel"]),
            "policy_version": str(row["policy_version"]),
            "notice_version": str(row["notice_version"]),
            "language": str(row["language"]),
            "text": str(row["text_snapshot"]),
            "text_sha256": str(row["text_sha256"]),
            "privacy_notice_url": str(row["privacy_notice_url"]),
            "retention_summary": str(row["retention_summary"]),
            "credit_decision": "The institution decides; this authorization does not guarantee credit.",
        }


def verify_public_challenge(
    db_path: str, *, challenge_id: str, access_token: str, otp: str,
    accepted: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify an applicant code without exposing the institution credential."""
    if accepted is not True:
        raise PermissionError("Active acceptance is required")
    intake_id, owner_actor = _public_challenge_row(
        db_path, challenge_id=challenge_id, access_token=access_token,
    )
    return verify_challenge(
        db_path, intake_id=intake_id, challenge_id=challenge_id,
        otp=otp, owner_actor=owner_actor, now=now,
        affirmation="active_checkbox_and_one_time_code",
    )


def verify_challenge(
    db_path: str,
    *,
    intake_id: str,
    challenge_id: str,
    otp: str,
    owner_actor: str,
    now: datetime | None = None,
    affirmation: str = "one_time_code",
) -> dict[str, Any]:
    otp = str(otp or "").strip()
    if not re.fullmatch(r"\d{6}", otp):
        raise ValueError("otp must contain exactly 6 digits")
    current = (now or _now()).astimezone(timezone.utc)
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        row = log.conn.execute(
            "SELECT c.*,p.policy_version,p.notice_version,p.language,p.text_snapshot,"
            "p.text_sha256,p.privacy_notice_url,p.retention_summary,p.status AS policy_status "
            "FROM consent_challenge c JOIN consent_policy p ON p.policy_id=c.policy_id "
            "WHERE c.challenge_id=? AND c.intake_id=? AND c.owner_actor=?",
            (challenge_id, intake_id, owner_actor),
        ).fetchone()
        if not row:
            raise LookupError("Consent challenge not found")
        if str(row["status"]) != "pending":
            raise PermissionError("Consent challenge is not active")
        if not str(row["dispatch_artifact"]):
            raise PermissionError("Consent challenge delivery is incomplete")
        if _parse(str(row["expires_at"]), "expires_at") <= current:
            log.conn.execute(
                "UPDATE consent_challenge SET status='expired' WHERE challenge_id=?",
                (challenge_id,),
            )
            log.conn.commit()
            raise PermissionError("Consent challenge expired")
        if not hmac.compare_digest(str(row["otp_hash"]), _otp_digest(challenge_id, otp)):
            attempts = int(row["attempts"]) + 1
            status = "locked" if attempts >= int(row["max_attempts"]) else "pending"
            log.conn.execute(
                "UPDATE consent_challenge SET attempts=?,status=? WHERE challenge_id=?",
                (attempts, status, challenge_id),
            )
            _append(log, intake_id, "consent_challenge_failed", owner_actor, {
                "challenge_id": challenge_id, "attempts": attempts, "status": status,
            })
            log.conn.commit()
            raise PermissionError("Consent challenge verification failed")

        consent_id = uuid4().hex
        receipt = {
            "receipt_version": "olin-consent-receipt-1.0",
            "consent_id": consent_id,
            "intake_id": intake_id,
            "institution_actor": owner_actor,
            "purpose": str(row["purpose"]),
            "provider": str(row["provider"]),
            "policy_id": str(row["policy_id"]),
            "policy_version": str(row["policy_version"]),
            "notice_version": str(row["notice_version"]),
            "language": str(row["language"]),
            "text": str(row["text_snapshot"]),
            "text_sha256": str(row["text_sha256"]),
            "privacy_notice_url": str(row["privacy_notice_url"]),
            "retention_summary": str(row["retention_summary"]),
            "accepted_at": current.isoformat(),
            "channel": str(row["channel"]),
            "verification_method": affirmation,
            "verification_artifact": str(row["dispatch_artifact"]),
            "identity_reference_hash": str(row["identity_reference_hash"]),
            "authority_reference_hash": str(row["authority_reference_hash"]),
            "credit_decision": "none; the institution retains the decision",
        }
        receipt_json = _canonical(receipt)
        receipt_hash = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest()
        log.conn.execute(
            "UPDATE intake_consent SET status='superseded' WHERE intake_id=? "
            "AND purpose=? AND provider=? AND status='active'",
            (intake_id, row["purpose"], row["provider"]),
        )
        log.conn.execute(
            "UPDATE intake_link_session SET status='cancelled' WHERE intake_id=? "
            "AND consent_id IN (SELECT consent_id FROM intake_consent WHERE intake_id=? "
            "AND purpose=? AND provider=? AND status='superseded') AND status='active'",
            (intake_id, intake_id, row["purpose"], row["provider"]),
        )
        log.conn.execute(
            "INSERT INTO intake_consent "
            "(consent_id,intake_id,purpose,policy_version,text_sha256,channel,status,"
            "captured_at,captured_by,provider,notice_version,language,text_snapshot,"
            "privacy_notice_url,retention_summary,destination_hash,identity_reference_hash,"
            "authority_reference_hash,verification_method,verification_artifact,"
            "receipt_sha256,receipt_json) VALUES (?,?,?,?,?,?,'active',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                consent_id, intake_id, row["purpose"], row["policy_version"],
                row["text_sha256"], row["channel"], current.isoformat(), owner_actor,
                row["provider"], row["notice_version"], row["language"], row["text_snapshot"],
                row["privacy_notice_url"], row["retention_summary"], row["destination_hash"],
                row["identity_reference_hash"], row["authority_reference_hash"],
                affirmation, row["dispatch_artifact"], receipt_hash, receipt_json,
            ),
        )
        log.conn.execute(
            "UPDATE consent_challenge SET status='verified',verified_at=? WHERE challenge_id=?",
            (current.isoformat(), challenge_id),
        )
        if row["purpose"] == "credit_assessment":
            log.conn.execute(
                "UPDATE intake SET status='consented',updated_at=? WHERE intake_id=? "
                "AND status IN ('created','consented','link_pending','evidence_ready')",
                (current.isoformat(), intake_id),
            )
        _append(log, intake_id, "purpose_specific_consent_verified", owner_actor, {
            "consent_id": consent_id, "challenge_id": challenge_id,
            "purpose": row["purpose"], "provider": row["provider"],
            "policy_id": row["policy_id"], "policy_version": row["policy_version"],
            "notice_version": row["notice_version"], "text_sha256": row["text_sha256"],
            "receipt_sha256": receipt_hash, "verification_method": affirmation,
        })
        log.conn.commit()
    return {
        "consent_id": consent_id, "status": "active", "purpose": str(row["purpose"]),
        "provider": str(row["provider"]), "accepted_at": current.isoformat(),
        "receipt_sha256": receipt_hash,
        "receipt_path": f"/api/v1/intakes/{intake_id}/consents/{consent_id}/receipt",
    }


def get_receipt(
    db_path: str, *, intake_id: str, consent_id: str, owner_actor: str,
) -> dict[str, Any]:
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        row = log.conn.execute(
            "SELECT c.receipt_json,c.receipt_sha256,c.status,c.withdrawn_at,c.withdrawal_reason "
            "FROM intake_consent c JOIN intake i ON i.intake_id=c.intake_id "
            "WHERE c.intake_id=? AND c.consent_id=? AND i.owner_actor=?",
            (intake_id, consent_id, owner_actor),
        ).fetchone()
        if not row or not str(row["receipt_json"]):
            raise LookupError("Consent receipt not found")
        receipt_json = str(row["receipt_json"])
        if hashlib.sha256(receipt_json.encode("utf-8")).hexdigest() != str(row["receipt_sha256"]):
            raise RuntimeError("Consent receipt integrity check failed")
        receipt = json.loads(receipt_json)
        receipt["receipt_sha256"] = str(row["receipt_sha256"])
        receipt["current_status"] = str(row["status"])
        receipt["withdrawn_at"] = row["withdrawn_at"]
        receipt["withdrawal_reason"] = row["withdrawal_reason"]
        return receipt


def withdraw_consent(
    db_path: str, *, intake_id: str, consent_id: str,
    reason: str, owner_actor: str,
) -> dict[str, Any]:
    reason = _clean(reason, "reason", 5, 1000)
    when = _now().isoformat()
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        consent = log.conn.execute(
            "SELECT c.purpose,c.provider FROM intake_consent c JOIN intake i "
            "ON i.intake_id=c.intake_id WHERE c.intake_id=? AND c.consent_id=? "
            "AND c.status='active' AND i.owner_actor=?",
            (intake_id, consent_id, owner_actor),
        ).fetchone()
        if not consent:
            raise LookupError("Active intake consent not found")
        purpose = str(consent["purpose"])
        provider = str(consent["provider"])
        log.conn.execute(
            "UPDATE intake_consent SET status='withdrawn',withdrawn_at=?,withdrawal_reason=? "
            "WHERE intake_id=? AND consent_id=? AND status='active'",
            (when, reason, intake_id, consent_id),
        )
        dependent_ids = [consent_id]
        if purpose == "credit_assessment":
            dependent_ids.extend(str(row[0]) for row in log.conn.execute(
                "SELECT consent_id FROM intake_consent WHERE intake_id=? AND status='active'",
                (intake_id,),
            ).fetchall())
            log.conn.execute(
                "UPDATE intake_consent SET status='withdrawn',withdrawn_at=?,"
                "withdrawal_reason=? WHERE intake_id=? AND status='active'",
                (when, "Dependent on withdrawn credit_assessment consent", intake_id),
            )
        placeholders = ",".join("?" for _ in dependent_ids)
        log.conn.execute(
            f"UPDATE intake_link_session SET status='cancelled' WHERE consent_id IN ({placeholders}) "
            "AND status='active'", tuple(dependent_ids),
        )
        if purpose == "credit_assessment":
            next_state = "created"
        elif purpose == "provider_access":
            next_state = "consented"
        else:
            state = log.conn.execute(
                "SELECT status FROM intake WHERE intake_id=?", (intake_id,),
            ).fetchone()
            next_state = str(state[0])
        log.conn.execute(
            "UPDATE intake SET status=?,updated_at=? WHERE intake_id=?",
            (next_state, when, intake_id),
        )
        task_id = uuid4().hex
        log.conn.execute(
            "INSERT INTO consent_withdrawal_task "
            "(task_id,intake_id,consent_id,purpose,provider,status,created_at,created_by) "
            "VALUES (?,?,?,?,?,'open',?,?)",
            (task_id, intake_id, consent_id, purpose, provider, when, owner_actor),
        )
        _append(log, intake_id, "purpose_specific_consent_withdrawn", owner_actor, {
            "consent_id": consent_id, "purpose": purpose, "provider": provider,
            "reason": reason, "dependent_consent_ids": dependent_ids, "task_id": task_id,
        })
        log.conn.commit()
    return {
        "consent_id": consent_id, "status": "withdrawn", "purpose": purpose,
        "provider": provider, "withdrawn_at": when, "withdrawal_task_id": task_id,
        "intake_status": next_state,
    }
