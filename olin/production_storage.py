"""Fail-closed boundary between the local synthetic MVP and real bank data."""
from __future__ import annotations

import os
from typing import Any

from .config import real_data_enabled

POSTGRES_RUNTIME_ADAPTER_IMPLEMENTED = True


def _postgres_driver_available() -> bool:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return True


def production_storage_readiness() -> dict[str, Any]:
    url = os.getenv("OLIN_DATABASE_URL", "").strip()
    checks = {
        "postgres_configured": url.startswith(("postgres://", "postgresql://")),
        "kms_key_configured": bool(os.getenv("OLIN_KMS_KEY_ID", "").strip()),
        "encryption_at_rest_attested": os.getenv(
            "OLIN_DATABASE_ENCRYPTION_AT_REST", ""
        ).strip().lower() == "attested",
        "backup_restore_evidence": bool(os.getenv("OLIN_BACKUP_RESTORE_EVIDENCE", "").strip()),
        # Configuration strings alone never count as a runtime adapter.
        "postgres_runtime_adapter": (
            POSTGRES_RUNTIME_ADAPTER_IMPLEMENTED and _postgres_driver_available()
        ),
    }
    required = real_data_enabled()
    if required and checks["postgres_runtime_adapter"] and checks["postgres_configured"]:
        try:
            from .store import connect_database
            conn = connect_database(url)
            conn.execute("SELECT 1").fetchone()
            conn.close()
            checks["postgres_connectivity"] = True
        except Exception:
            checks["postgres_connectivity"] = False
    else:
        checks["postgres_connectivity"] = not required
    return {
        "real_data_enabled": required,
        "ready": (all(checks.values()) if required else True),
        "checks": checks,
        "note": (
            "Real-data mode requires managed PostgreSQL, KMS, encryption, restore evidence, and the runtime Postgres adapter."
            if required else "Local SQLite is restricted to synthetic/test data."
        ),
    }


def assert_real_data_storage_ready() -> None:
    result = production_storage_readiness()
    if result["real_data_enabled"] and not result["ready"]:
        failed = [key for key, passed in result["checks"].items() if not passed]
        raise RuntimeError("Real-data storage is not ready: " + ", ".join(failed))
