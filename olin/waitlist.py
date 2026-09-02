"""Privacy-conscious public waitlist storage for the Olin design-partner funnel.

This module is intentionally separate from credit applications.  A waitlist
entry is a marketing lead; it never creates a borrower, credit case, consent
for credit-data access, or underwriting decision.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from .config import is_production
from .store import connect_database


WAITLIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS waitlist_entry (
    entry_id          TEXT PRIMARY KEY,
    email_fingerprint TEXT NOT NULL UNIQUE,
    email_ciphertext  TEXT NOT NULL,
    contact_name      TEXT NOT NULL,
    organization      TEXT NOT NULL,
    organization_type TEXT NOT NULL,
    role              TEXT NOT NULL,
    portfolio_size    TEXT NOT NULL,
    priority_problem  TEXT NOT NULL,
    contact_consent   INTEGER NOT NULL CHECK(contact_consent = 1),
    status            TEXT NOT NULL CHECK(status IN ('received','selected','declined','deleted')),
    source            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    referral_code     TEXT NOT NULL UNIQUE,
    referred_by       TEXT
);
CREATE INDEX IF NOT EXISTS idx_waitlist_public_count
ON waitlist_entry(status, created_at);
"""

EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$")
ORGANIZATION_TYPES = {
    "bank", "sofom", "fintech", "acquirer", "merchant_network",
    "distributor", "other",
}
PORTFOLIO_SIZES = {"under_100", "100_999", "1000_9999", "10000_plus", "unknown"}
_DEVELOPMENT_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b"olin-waitlist-development-only").digest()
).decode()


@dataclass(frozen=True)
class WaitlistSubmission:
    email: str
    contact_name: str
    organization: str
    organization_type: str
    role: str
    portfolio_size: str
    priority_problem: str
    contact_consent: bool
    referral_code: str = ""
    source: str = "website"


def _clean(value: object, field: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    cleaned = " ".join(value.strip().split())
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def parse_submission(body: dict) -> WaitlistSubmission:
    """Validate and normalize the small, allowlisted marketing payload."""
    allowed = {
        "email", "contact_name", "organization", "organization_type", "role",
        "portfolio_size", "priority_problem", "contact_consent", "source", "website",
        "referral_code",
    }
    unexpected = sorted(set(body) - allowed)
    if unexpected:
        raise ValueError(f"unexpected fields: {', '.join(unexpected)}")

    email = _clean(body.get("email"), "email", 254).lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("email must be a valid address")
    organization_type = _clean(body.get("organization_type"), "organization_type", 40).lower()
    if organization_type not in ORGANIZATION_TYPES:
        raise ValueError("organization_type is not supported")
    portfolio_size = _clean(body.get("portfolio_size"), "portfolio_size", 30).lower()
    if portfolio_size not in PORTFOLIO_SIZES:
        raise ValueError("portfolio_size is not supported")
    if body.get("contact_consent") is not True:
        raise ValueError("contact_consent must be accepted")
    referral_code = _clean(body.get("referral_code", ""), "referral_code", 24, required=False).upper()
    if referral_code and not re.fullmatch(r"OLIN-[A-Z0-9]{8}", referral_code):
        raise ValueError("referral_code is invalid")

    return WaitlistSubmission(
        email=email,
        contact_name=_clean(body.get("contact_name"), "contact_name", 100),
        organization=_clean(body.get("organization"), "organization", 160),
        organization_type=organization_type,
        role=_clean(body.get("role"), "role", 100),
        portfolio_size=portfolio_size,
        priority_problem=_clean(
            body.get("priority_problem", ""), "priority_problem", 500, required=False
        ),
        contact_consent=True,
        referral_code=referral_code,
        source=_clean(body.get("source", "website"), "source", 80),
    )


def is_honeypot_submission(body: dict) -> bool:
    return bool(str(body.get("website", "")).strip())


def _fernet() -> tuple[Fernet, bytes]:
    key = os.getenv("OLIN_WAITLIST_ENCRYPTION_KEY", "").strip()
    if not key and not is_production():
        key = _DEVELOPMENT_KEY
    if not key:
        raise RuntimeError("OLIN_WAITLIST_ENCRYPTION_KEY is not configured")
    try:
        key_material = base64.urlsafe_b64decode(key.encode())
        return Fernet(key.encode()), key_material
    except (TypeError, ValueError, binascii.Error) as exc:
        raise RuntimeError("OLIN_WAITLIST_ENCRYPTION_KEY must be a Fernet key") from exc


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode()


def _fingerprint(email: str, key: bytes) -> str:
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()


class WaitlistStore:
    def __init__(self, db_path: str | Path):
        self.target = str(db_path)
        self.cipher, self.fingerprint_key = _fernet()
        self.last_referral_code: str | None = None
        self.conn = connect_database(self.target)
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(WAITLIST_SCHEMA)
        for migration in (
            "ALTER TABLE waitlist_entry ADD COLUMN referral_code TEXT",
            "ALTER TABLE waitlist_entry ADD COLUMN referred_by TEXT",
        ):
            try:
                self.conn.execute(migration)
            except sqlite3.OperationalError:
                pass
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_waitlist_referral_code "
            "ON waitlist_entry(referral_code) WHERE referral_code IS NOT NULL"
        )
        self.conn.commit()

    def submit(self, item: WaitlistSubmission) -> tuple[bool, int]:
        now = datetime.now(timezone.utc).isoformat()
        email_bytes = item.email.encode()
        fingerprint = _fingerprint(item.email, self.fingerprint_key)
        ciphertext = self.cipher.encrypt(email_bytes).decode()
        referred_by = item.referral_code or None
        if referred_by:
            valid_referral = self.conn.execute(
                "SELECT 1 FROM waitlist_entry WHERE referral_code=? AND status != 'deleted'",
                (referred_by,),
            ).fetchone()
            if not valid_referral:
                referred_by = None
        referral_code = "OLIN-" + secrets.token_hex(4).upper()
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO waitlist_entry
               (entry_id, email_fingerprint, email_ciphertext, contact_name,
                organization, organization_type, role, portfolio_size,
                priority_problem, contact_consent, status, source, created_at, updated_at,
                referral_code, referred_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'received', ?, ?, ?, ?, ?)""",
            (
                f"wl_{uuid4().hex}", fingerprint, ciphertext, item.contact_name,
                item.organization, item.organization_type, item.role,
                item.portfolio_size, item.priority_problem, item.source, now, now,
                referral_code, referred_by,
            ),
        )
        created = cursor.rowcount == 1
        if not created:
            referral_code = self.conn.execute(
                "SELECT referral_code FROM waitlist_entry WHERE email_fingerprint=?",
                (fingerprint,),
            ).fetchone()[0]
        self.last_referral_code = str(referral_code) if referral_code else None
        self.conn.commit()
        return created, self.public_count()

    def referral_code_for_email(self, email: str) -> str | None:
        normalized = _clean(email, "email", 254).lower()
        fingerprint = _fingerprint(normalized, self.fingerprint_key)
        row = self.conn.execute(
            "SELECT referral_code FROM waitlist_entry WHERE email_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return str(row[0]) if row and row[0] else None

    def public_count(self) -> int:
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM waitlist_entry WHERE status IN ('received','selected')"
        ).fetchone()[0])

    def list_entries(self, limit: int = 200) -> list[dict]:
        """Return decrypted leads for an authenticated admin workflow only."""
        rows = self.conn.execute(
            """SELECT entry_id, email_ciphertext, contact_name, organization,
                      organization_type, role, portfolio_size, priority_problem,
                      status, source, created_at, referral_code, referred_by
               FROM waitlist_entry
               WHERE status != 'deleted'
               ORDER BY created_at DESC LIMIT ?""",
            (max(1, min(500, int(limit))),),
        ).fetchall()
        fields = (
            "entry_id", "email_ciphertext", "contact_name", "organization",
            "organization_type", "role", "portfolio_size", "priority_problem",
            "status", "source", "created_at", "referral_code", "referred_by",
        )
        result = []
        for row in rows:
            item = dict(zip(fields, row))
            item["email"] = self.cipher.decrypt(item.pop("email_ciphertext").encode()).decode()
            result.append(item)
        return result

    def decrypt_email(self, entry_id: str) -> str:
        row = self.conn.execute(
            "SELECT email_ciphertext FROM waitlist_entry WHERE entry_id=?", (entry_id,)
        ).fetchone()
        if row is None:
            raise KeyError(entry_id)
        try:
            return self.cipher.decrypt(row[0].encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("waitlist email cannot be decrypted with the configured key") from exc

    def delete_by_email(self, email: str) -> bool:
        """Hard-delete a marketing lead after an authenticated operator request."""
        normalized = _clean(email, "email", 254).lower()
        fingerprint = _fingerprint(normalized, self.fingerprint_key)
        cursor = self.conn.execute(
            "DELETE FROM waitlist_entry WHERE email_fingerprint=?", (fingerprint,)
        )
        deleted = cursor.rowcount == 1
        self.conn.commit()
        return deleted

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
