"""Runtime safety configuration for Olin.

Demo mode preserves the deterministic mocks used by the simulator. Pilot and
production modes are fail-closed: synthetic underwriting inputs are rejected
and sensitive HTTP actions require configured secrets. Pilot mode can never
move money.
"""
from __future__ import annotations

import os
from pathlib import Path


VALID_MODES = {"demo", "pilot", "production", "test"}
SYNTHETIC_SOURCES = {"mock", "mock_sandbox", "demo", "synthetic"}


def runtime_mode() -> str:
    mode = os.getenv("OLIN_MODE", "demo").strip().lower()
    if mode not in VALID_MODES:
        raise RuntimeError(
            f"Invalid OLIN_MODE={mode!r}; expected demo, pilot, production, or test"
        )
    return mode


def is_production() -> bool:
    """Return True for fail-closed environments handling real evidence."""
    return runtime_mode() in {"pilot", "production"}


def is_demo() -> bool:
    return runtime_mode() in {"demo", "test"}


def mocks_allowed() -> bool:
    return not is_production()


def live_lending_enabled() -> bool:
    """Require an explicit, independently approved production money gate."""
    value = os.getenv("OLIN_LIVE_LENDING_ENABLED", "").strip().lower()
    return runtime_mode() == "production" and value in {"1", "true", "yes"} and all(
        live_lending_readiness()["checks"].values()
    )


def live_lending_readiness() -> dict:
    """Non-secret checks for the separately approved real-money rail.

    The default kill switch is active. Credentials and approval references are
    intentionally environment-only and are never stored in the repository.
    """
    from pathlib import Path

    checks = {
        "production_mode": runtime_mode() == "production",
        "real_data_mode": real_data_enabled(),
        "explicit_enable": os.getenv("OLIN_LIVE_LENDING_ENABLED", "").strip().lower()
        in {"1", "true", "yes"},
        "kill_switch_clear": os.getenv("OLIN_LIVE_LENDING_KILL_SWITCH", "1").strip().lower()
        in {"0", "false", "no"},
        "approval_reference": bool(os.getenv("OLIN_LIVE_LENDING_APPROVAL_REF", "").strip()),
        "first_approver": bool(os.getenv("OLIN_LIVE_LENDING_APPROVED_BY", "").strip()),
        "second_approver": bool(os.getenv("OLIN_LIVE_LENDING_SECOND_APPROVER", "").strip()),
        "distinct_approvers": (
            os.getenv("OLIN_LIVE_LENDING_APPROVED_BY", "").strip()
            != os.getenv("OLIN_LIVE_LENDING_SECOND_APPROVER", "").strip()
        ),
        "stp_production": os.getenv("STP_SANDBOX", "1").strip() == "0",
        "stp_empresa": bool(os.getenv("STP_EMPRESA", "").strip()),
        "stp_source_account": bool(os.getenv("STP_CUENTA_ORDENANTE", "").strip()),
        "stp_private_key": Path(os.getenv("STP_PRIVATE_KEY_PATH", "")).is_file(),
        "stp_certificate": Path(os.getenv("STP_CERT_PATH", "")).is_file(),
        "webhook_secret": len(os.getenv("OLIN_STP_WEBHOOK_SECRET", "").strip()) >= 32,
    }
    try:
        from .production_storage import production_storage_readiness
        checks["real_data_storage"] = bool(production_storage_readiness()["ready"])
    except Exception:
        checks["real_data_storage"] = False
    return {"ready": all(checks.values()), "checks": checks}


def real_data_enabled() -> bool:
    """Real bank/customer evidence is opt-in and requires production storage."""
    return os.getenv("OLIN_REAL_DATA_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def validated_auto_approve_types() -> frozenset[str]:
    """Bank/model-risk approved business types; empty is the safe default."""
    return frozenset(
        item.strip().lower()
        for item in os.getenv("OLIN_VALIDATED_AUTO_APPROVE_TYPES", "").split(",")
        if item.strip()
    )


def is_synthetic_source(source: str | None) -> bool:
    normalized = (source or "unknown").strip().lower()
    return normalized in SYNTHETIC_SOURCES or normalized.startswith("mock")


def default_db_path(root: Path) -> Path:
    if runtime_mode() == "production":
        return root / "olin_production.db"
    if runtime_mode() == "pilot":
        return root / "olin_pilot.db"
    return root / "olin_scoring.db"


def default_database_target(root: Path) -> str:
    """Return the managed DSN when real-data mode is explicitly enabled."""
    if real_data_enabled():
        url = os.getenv("OLIN_DATABASE_URL", "").strip()
        if url.startswith(("postgres://", "postgresql://")):
            return url
    return str(default_db_path(root))


def analyst_token() -> str:
    return os.getenv("OLIN_ANALYST_TOKEN", "").strip()


def api_keys() -> dict[str, str]:
    """Return all valid API keys as {label: token}.

    Reads OLIN_API_KEYS (JSON object) first; falls back to OLIN_ANALYST_TOKEN
    so existing deployments keep working without changes.
    """
    import json
    raw = os.getenv("OLIN_API_KEYS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            return {str(k): str(v).strip() for k, v in parsed.items() if v}
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    token = analyst_token()
    if token:
        return {"default": token}
    return {}


def webhook_secret() -> str:
    return os.getenv("OLIN_STP_WEBHOOK_SECRET", "").strip()
