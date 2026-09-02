"""Fail-closed preflight for a bank real-data shadow environment.

This validates technical configuration and recorded operational approvals.  It
does not replace the bank's security/privacy review or Mexican legal advice.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import parse_qs, urlparse

from .api.auth import VALID_ROLES, configured_users
from .config import real_data_enabled, runtime_mode
from .production_storage import production_storage_readiness
from .source_trust import trust_registry_readiness


DATA_CLASSIFICATIONS = frozenset({
    "pseudonymized_historical",
    "identifiable_historical",
    "prospective",
})


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _secret_map_is_strong() -> bool:
    raw = os.getenv("OLIN_BANK_WEBHOOK_SECRETS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or not parsed:
                return False
            secrets = [
                str(secret)
                for value in parsed.values()
                for secret in (value if isinstance(value, list) else [value])
            ]
            return bool(secrets) and all(len(secret) >= 32 for secret in secrets)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return False
    return len(os.getenv("OLIN_BANK_WEBHOOK_SECRET", "").strip()) >= 32


def _postgres_tls_configured(database_url: str) -> bool:
    if not database_url.startswith(("postgres://", "postgresql://")):
        return False
    query = parse_qs(urlparse(database_url).query)
    sslmode = str(query.get("sslmode", [""])[0]).lower()
    url_requires_tls = sslmode in {"require", "verify-ca", "verify-full"}
    attested = os.getenv("OLIN_DATABASE_TLS_ATTESTED", "").strip().lower() in {
        "1", "true", "yes", "attested",
    }
    return url_requires_tls or attested


def _users_are_bank_ready() -> bool:
    try:
        users = configured_users()
    except RuntimeError:
        return False
    if not users:
        return False
    roles = {item.get("role") for item in users.values()}
    tokens = [str(item.get("token", "")) for item in users.values()]
    return (
        roles.issubset(VALID_ROLES)
        and {"partner", "analyst", "admin"}.issubset(roles)
        and all(len(token) >= 32 for token in tokens)
        and len(tokens) == len(set(tokens))
        and all(name.strip() and name.lower() not in {"default", "admin", "user"}
                for name in users)
    )


def _retention_is_bounded() -> bool:
    try:
        days = int(os.getenv("OLIN_RETENTION_DAYS", "0"))
    except ValueError:
        return False
    return 1 <= days <= 365


def production_preflight(database_target: str | None = None) -> dict[str, Any]:
    """Return non-secret evidence showing whether real-data startup is allowed."""
    required = real_data_enabled()
    if not required:
        return {
            "required": False,
            "ok": True,
            "mode": runtime_mode(),
            "checks": {},
            "failed": [],
            "note": "Real-data mode is disabled.",
        }

    database_url = (database_target or os.getenv("OLIN_DATABASE_URL", "")).strip()
    classification = os.getenv("OLIN_DATA_CLASSIFICATION", "").strip().lower()
    prospective = classification == "prospective"
    storage = production_storage_readiness()
    trust = trust_registry_readiness()
    checks = {
        "production_mode": runtime_mode() == "production",
        "managed_postgres": database_url.startswith(("postgres://", "postgresql://")),
        "postgres_tls": _postgres_tls_configured(database_url),
        "production_storage": bool(storage["ready"]),
        "named_users_and_roles": _users_are_bank_ready(),
        "short_lived_sessions": (
            os.getenv("OLIN_REQUIRE_SHORT_LIVED_SESSIONS", "").strip().lower()
            in {"1", "true", "yes"}
            and len(os.getenv("OLIN_SESSION_SECRET", "").strip()) >= 32
        ),
        "signed_bank_webhook": _secret_map_is_strong(),
        "https_public_base_url": os.getenv("OLIN_PUBLIC_BASE_URL", "").strip().startswith("https://"),
        "data_classification": classification in DATA_CLASSIFICATIONS,
        "data_scope_reference": _present("OLIN_REAL_DATA_SCOPE_REF"),
        "processing_approval_reference": _present("OLIN_DATA_PROCESSING_APPROVAL_REF"),
        "bounded_retention": _retention_is_bounded(),
        "incident_owner": _present("OLIN_INCIDENT_OWNER"),
        "incident_contact": _present("OLIN_INCIDENT_CONTACT"),
        "trusted_source_registry": bool(trust["ready"]),
        "live_lending_disabled": os.getenv(
            "OLIN_LIVE_LENDING_ENABLED", "0"
        ).strip().lower() not in {"1", "true", "yes"},
        "prospective_consent_secret": (
            len(os.getenv("OLIN_CONSENT_OTP_SECRET", "").strip()) >= 32
            if prospective else True
        ),
        "prospective_delivery_adapter": (
            os.getenv("OLIN_CONSENT_OTP_MODE", "synthetic").strip().lower()
            not in {"", "synthetic", "test", "demo"}
            if prospective else True
        ),
    }
    failed = sorted(name for name, value in checks.items() if not value)
    return {
        "required": True,
        "ok": not failed,
        "mode": runtime_mode(),
        "data_classification": classification or None,
        "checks": checks,
        "failed": failed,
        "storage": storage,
        "source_trust_registry": trust,
        "note": (
            "Technical and recorded operational gates passed; institutional approvals remain external."
            if not failed else "Real-data startup is blocked until every failed gate is resolved."
        ),
    }


def assert_production_preflight(database_target: str | None = None) -> None:
    result = production_preflight(database_target)
    if not result["ok"]:
        raise RuntimeError(
            "Real-data production preflight failed: " + ", ".join(result["failed"])
        )
