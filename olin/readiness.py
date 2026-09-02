"""Non-secret launch-readiness checks for the controlled bank pilot."""
from __future__ import annotations

from contextlib import closing
import json
import os
import sqlite3
from typing import Any

from .api.auth import configured_users
from .config import is_production, live_lending_enabled, live_lending_readiness, runtime_mode
from .production_storage import production_storage_readiness
from .production_preflight import production_preflight
from .source_trust import trust_registry_readiness
from .store import connect_database


def readiness(db_path: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        users = configured_users()
    except RuntimeError:
        users = {}
    roles = {item.get("role") for item in users.values()}
    checks["named_users"] = bool(users) if is_production() else True
    checks["separation_of_duties"] = (
        {"partner", "analyst", "admin"}.issubset(roles) if is_production() else True
    )
    bank_secret = os.getenv("OLIN_BANK_WEBHOOK_SECRET", "")
    bank_secret_map = os.getenv("OLIN_BANK_WEBHOOK_SECRETS", "").strip()
    valid_secret_map = False
    if bank_secret_map:
        try:
            parsed = json.loads(bank_secret_map)
            values = parsed.values() if isinstance(parsed, dict) else ()
            flattened = [
                item
                for value in values
                for item in (value if isinstance(value, list) else [value])
            ]
            valid_secret_map = bool(flattened) and all(
                len(str(item)) >= 32 for item in flattened
            )
        except (json.JSONDecodeError, AttributeError, TypeError):
            valid_secret_map = False
    checks["bank_webhook_secret"] = (
        valid_secret_map or len(bank_secret) >= 32
    ) if is_production() else True
    checks["money_movement_disabled"] = not live_lending_enabled()
    money = live_lending_readiness()
    checks["database"] = False
    try:
        with closing(connect_database(db_path)) as conn:
            table_query = (
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?"
                if str(db_path).startswith(("postgres://", "postgresql://"))
                else "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
            )
            exists = conn.execute(table_query, ("scoring_log",)).fetchone()
            checks["database"] = bool(exists)
    except (OSError, sqlite3.Error):
        pass
    storage = production_storage_readiness()
    checks["real_data_storage"] = bool(storage["ready"])
    trust = trust_registry_readiness()
    require_trust = os.getenv("OLIN_REQUIRE_TRUST_REGISTRY", "").strip().lower() in {"1", "true", "yes"}
    checks["source_trust_registry"] = trust["ready"] if require_trust else True
    preflight = production_preflight(db_path)
    checks["production_preflight"] = bool(preflight["ok"])
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "ok": not failed,
        "service": "olin",
        "mode": runtime_mode(),
        "checks": checks,
        "failed": failed,
        "production_storage": storage,
        "source_trust_registry": trust,
        "production_preflight": preflight,
        "live_lending": money,
    }
