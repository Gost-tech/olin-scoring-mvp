"""Minimal named-user authentication and role authorization for Olin."""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import os
from typing import Mapping

from ..config import api_keys, is_production


VALID_ROLES = frozenset({"partner", "analyst", "admin"})

PERMISSIONS = {
    "case:create": frozenset({"partner", "admin"}),
    "case:read": frozenset({"partner", "analyst", "admin"}),
    "case:partner_outcome": frozenset({"partner", "analyst", "admin"}),
    "case:analyst_action": frozenset({"analyst", "admin"}),
    "case:export": frozenset({"analyst", "admin"}),
    "portfolio:read": frozenset({"analyst", "admin"}),
    "money:disburse": frozenset({"admin"}),
}


@dataclass(frozen=True)
class AuthenticatedUser:
    name: str
    role: str


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


def authenticate(headers: Mapping[str, str]) -> AuthenticatedUser | None:
    """Authenticate one request without persisting the supplied token."""
    if not is_production():
        return AuthenticatedUser("analista_demo", "admin")
    supplied = str(headers.get("X-Olin-Analyst-Token", "")).strip()
    if not supplied:
        return None
    for name, config in configured_users().items():
        if hmac.compare_digest(supplied, config["token"]):
            return AuthenticatedUser(name=name, role=config["role"])
    return None


def is_allowed(user: AuthenticatedUser, permission: str) -> bool:
    return user.role in PERMISSIONS.get(permission, frozenset())
