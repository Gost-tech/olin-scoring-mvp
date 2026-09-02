"""Minimal named-user authentication and role authorization for Olin."""
from __future__ import annotations

from dataclasses import dataclass
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Mapping

from ..config import api_keys, is_production


VALID_ROLES = frozenset({"partner", "analyst", "admin"})

PERMISSIONS = {
    "case:create": frozenset({"partner", "admin"}),
    "case:read": frozenset({"partner", "analyst", "admin"}),
    "case:partner_outcome": frozenset({"partner", "analyst", "admin"}),
    "case:performance": frozenset({"partner", "analyst", "admin"}),
    "case:consent": frozenset({"partner", "admin"}),
    "case:correction:create": frozenset({"partner", "analyst", "admin"}),
    "case:correction:resolve": frozenset({"analyst", "admin"}),
    "intake:create": frozenset({"partner", "admin"}),
    "intake:read": frozenset({"partner", "analyst", "admin"}),
    "intake:consent": frozenset({"partner", "admin"}),
    "intake:link": frozenset({"partner", "admin"}),
    "intake:score": frozenset({"partner", "admin"}),
    "case:analyst_action": frozenset({"analyst", "admin"}),
    "case:export": frozenset({"analyst", "admin"}),
    "portfolio:read": frozenset({"analyst", "admin"}),
    "evidence:guide": frozenset({"partner", "analyst", "admin"}),
    "operations:read": frozenset({"analyst", "admin"}),
    "waitlist:manage": frozenset({"admin"}),
    "money:disburse": frozenset({"admin"}),
}


@dataclass(frozen=True)
class AuthenticatedUser:
    name: str
    role: str
    credential_kind: str = "api_key"


def configured_users() -> dict[str, dict[str, str]]:
    """Return named credentials as ``{name: {token, role}}``.

    ``OLIN_USERS`` is the preferred configuration:

    ``{"fumi":{"token":"...","role":"partner"}}``

    Legacy ``OLIN_API_KEYS`` and ``OLIN_ANALYST_TOKEN`` values remain accepted
    as administrators so existing deployments do not silently lose access.
    """
    raw = os.getenv("OLIN_USERS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OLIN_USERS must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OLIN_USERS must be a JSON object")
        users: dict[str, dict[str, str]] = {}
        for name, value in parsed.items():
            if not isinstance(value, dict):
                raise RuntimeError(f"OLIN_USERS.{name} must be an object")
            token = str(value.get("token", "")).strip()
            role = str(value.get("role", "")).strip().lower()
            if not token:
                raise RuntimeError(f"OLIN_USERS.{name}.token is required")
            if role not in VALID_ROLES:
                raise RuntimeError(
                    f"OLIN_USERS.{name}.role must be partner, analyst, or admin"
                )
            users[str(name)] = {"token": token, "role": role}
        return users
    return {
        name: {"token": token, "role": "admin"}
        for name, token in api_keys().items()
    }


def _supplied_token(headers: Mapping[str, str]) -> str:
    authorization = str(headers.get("Authorization", "")).strip()
    supplied = ""
    if authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    # Compatibility window for original pilot clients. New bank integrations
    # use the standard Authorization: Bearer header.
    if not supplied:
        supplied = str(headers.get("X-Olin-Analyst-Token", "")).strip()
    return supplied


def authenticate_api_key(headers: Mapping[str, str]) -> AuthenticatedUser | None:
    """Authenticate a named bootstrap/service credential."""
    if not is_production():
        return AuthenticatedUser("analista_demo", "admin", "demo")
    supplied = _supplied_token(headers)
    if not supplied:
        return None
    for name, config in configured_users().items():
        if hmac.compare_digest(supplied, config["token"]):
            return AuthenticatedUser(name=name, role=config["role"], credential_kind="api_key")
    return None


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _session_secret() -> str:
    secret = os.getenv("OLIN_SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise RuntimeError("OLIN_SESSION_SECRET must contain at least 32 characters")
    return secret


def issue_session(headers: Mapping[str, str], now: int | None = None) -> dict[str, object]:
    """Exchange a named credential for a short-lived, signed bearer token."""
    user = authenticate_api_key(headers)
    if user is None:
        raise PermissionError("Invalid named credential")
    try:
        ttl_minutes = int(os.getenv("OLIN_SESSION_TTL_MINUTES", "15"))
    except ValueError as exc:
        raise RuntimeError("OLIN_SESSION_TTL_MINUTES must be an integer") from exc
    if not 5 <= ttl_minutes <= 60:
        raise RuntimeError("OLIN_SESSION_TTL_MINUTES must be between 5 and 60")
    issued_at = int(now if now is not None else time.time())
    expires_at = issued_at + ttl_minutes * 60
    payload = {
        "iss": "olin",
        "aud": "olin-bank-shadow",
        "sub": user.name,
        "role": user.role,
        "iat": issued_at,
        "exp": expires_at,
        "jti": secrets.token_hex(12),
    }
    encoded = _b64_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"olin1.{encoded}".encode()
    signature = _b64_encode(
        hmac.new(_session_secret().encode(), signing_input, hashlib.sha256).digest()
    )
    return {
        "access_token": f"olin1.{encoded}.{signature}",
        "token_type": "Bearer",
        "expires_in": ttl_minutes * 60,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        "user": {"name": user.name, "role": user.role},
    }


def authenticate_session(token: str, now: int | None = None) -> AuthenticatedUser | None:
    """Verify a signed session without storing it server-side."""
    try:
        version, encoded, supplied_signature = token.split(".")
        if version != "olin1":
            return None
        expected = _b64_encode(hmac.new(
            _session_secret().encode(), f"{version}.{encoded}".encode(), hashlib.sha256
        ).digest())
        if not hmac.compare_digest(supplied_signature, expected):
            return None
        payload = json.loads(_b64_decode(encoded))
        current = int(now if now is not None else time.time())
        if payload.get("iss") != "olin" or payload.get("aud") != "olin-bank-shadow":
            return None
        if not isinstance(payload.get("iat"), int) or not isinstance(payload.get("exp"), int):
            return None
        if payload["iat"] > current + 30 or payload["exp"] <= current:
            return None
        if payload["exp"] - payload["iat"] > 3600:
            return None
        name = str(payload.get("sub", ""))
        role = str(payload.get("role", ""))
        configured = configured_users().get(name)
        if not configured or configured.get("role") != role:
            return None
        return AuthenticatedUser(name=name, role=role, credential_kind="session")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, RuntimeError):
        return None


def authenticate(headers: Mapping[str, str]) -> AuthenticatedUser | None:
    """Authenticate a session, or an API key when the deployment permits it."""
    if not is_production():
        return AuthenticatedUser("analista_demo", "admin", "demo")
    supplied = _supplied_token(headers)
    if supplied.startswith("olin1."):
        return authenticate_session(supplied)
    require_sessions = os.getenv(
        "OLIN_REQUIRE_SHORT_LIVED_SESSIONS", "0"
    ).strip().lower() in {"1", "true", "yes"}
    if require_sessions:
        return None
    return authenticate_api_key(headers)


def is_allowed(user: AuthenticatedUser, permission: str) -> bool:
    return user.role in PERMISSIONS.get(permission, frozenset())
