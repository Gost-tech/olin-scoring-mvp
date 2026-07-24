"""Runtime safety configuration for Olin.

Demo mode preserves the deterministic mocks used by the simulator. Production
mode is fail-closed: synthetic underwriting inputs are rejected and sensitive
HTTP actions require configured secrets.
"""
from __future__ import annotations

import os
from pathlib import Path


VALID_MODES = {"demo", "production", "test"}
SYNTHETIC_SOURCES = {"mock", "mock_sandbox", "demo", "synthetic"}


def runtime_mode() -> str:
    mode = os.getenv("OLIN_MODE", "demo").strip().lower()
    if mode not in VALID_MODES:
        raise RuntimeError(
            f"Invalid OLIN_MODE={mode!r}; expected demo, production, or test"
        )
    return mode


def is_production() -> bool:
    return runtime_mode() == "production"


def is_demo() -> bool:
    return runtime_mode() != "production"


def mocks_allowed() -> bool:
    return not is_production()


def is_synthetic_source(source: str | None) -> bool:
    normalized = (source or "unknown").strip().lower()
    return normalized in SYNTHETIC_SOURCES or normalized.startswith("mock")


def default_db_path(root: Path) -> Path:
    if is_production():
        return root / "olin_production.db"
    return root / "olin_scoring.db"


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

