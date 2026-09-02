"""Operational control-room projection for the controlled shadow pilot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from .config import live_lending_readiness
from .store import ScoringLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _item(kind: str, severity: str, reference: str, owner: str, action: str,
          occurred_at: object = None) -> dict:
    return {
        "kind": kind,
        "severity": severity,
        "reference": str(reference),
        "owner": owner,
        "action": action,
        "occurred_at": str(occurred_at or ""),
    }


def control_room(db_path: str, *, now: datetime | None = None) -> dict:
    """Return a deterministic, read-only exception queue.

    This projection does not acknowledge or resolve work. Existing consent,
    correction, outcome and kill-switch actions remain the systems of record.
    """
    observed = now or _now()
    operations_owner = os.getenv("OLIN_OPERATIONS_OWNER", "UNASSIGNED").strip() or "UNASSIGNED"
    kill_owner = os.getenv("OLIN_KILL_SWITCH_OWNER", "UNASSIGNED").strip() or "UNASSIGNED"
    items: list[dict] = []

    with ScoringLog(db_path) as log:
        withdrawals = log.conn.execute(
            "SELECT task_id,intake_id,purpose,provider,created_at "
            "FROM consent_withdrawal_task WHERE status='open' ORDER BY created_at"
        ).fetchall()
        for task_id, intake_id, purpose, provider, created_at in withdrawals:
            items.append(_item(
                "consent_withdrawal", "critical", intake_id, operations_owner,
                f"Complete withdrawal task {task_id}: stop {purpose} processing"
                + (f" for {provider}" if provider else "")
                + ", notify affected providers, and record completion.",
                created_at,
            ))

        corrections = log.conn.execute(
            "SELECT request_id,application_id,created_at FROM correction_request "
            "WHERE status='open' ORDER BY created_at"
        ).fetchall()
        for request_id, application_id, created_at in corrections:
            items.append(_item(
                "open_correction", "high", application_id, operations_owner,
                f"Route correction {request_id} to an analyst and preserve the original value.",
                created_at,
            ))

        missing_consents = log.conn.execute(
            "SELECT application_id,scored_at FROM scoring_log "
            "WHERE COALESCE(is_demo,0)=0 AND COALESCE(case_mode,'shadow')='shadow' "
            "AND consent_timestamp IS NULL ORDER BY scored_at"
        ).fetchall()
        for application_id, scored_at in missing_consents:
            items.append(_item(
                "missing_or_withdrawn_consent", "critical", application_id,
                operations_owner,
                "Hold provider access and scoring progression; verify the consent record.",
                scored_at,
            ))

        pending_outcomes = log.conn.execute(
            "SELECT application_id,scored_at FROM scoring_log "
            "WHERE COALESCE(is_demo,0)=0 AND COALESCE(case_mode,'shadow')='shadow' "
            "AND (partner_decision IS NULL OR partner_decision='pending') ORDER BY scored_at"
        ).fetchall()
        for application_id, scored_at in pending_outcomes:
            age = observed - (_parse(scored_at) or observed)
            severity = "high" if age >= timedelta(days=2) else "medium"
            items.append(_item(
                "partner_decision_due", severity, application_id, operations_owner,
                "Request the independent partner decision and reason code.", scored_at,
            ))

        payment_anomalies = log.conn.execute(
            "SELECT application_id,outcome_status,disbursed_at FROM scoring_log "
            "WHERE outcome_status IN ('disburse_pending','disburse_failed')"
        ).fetchall()
        for application_id, status, occurred_at in payment_anomalies:
            items.append(_item(
                "ambiguous_or_failed_payment", "critical", application_id, kill_owner,
                f"Keep money movement stopped; reconcile authoritative provider state ({status}).",
                occurred_at,
            ))

        stale_cutoff = observed - timedelta(hours=24)
        intakes = log.conn.execute(
            "SELECT intake_id,status,updated_at FROM intake "
            "WHERE status IN ('created','consented','link_pending','evidence_ready','scoring')"
        ).fetchall()
        for intake_id, status, updated_at in intakes:
            timestamp = _parse(updated_at)
            if timestamp and timestamp < stale_cutoff:
                items.append(_item(
                    "stale_intake", "medium", intake_id, operations_owner,
                    f"Review intake stalled in {status}; contact applicant or close safely.",
                    updated_at,
                ))

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda item: (severity_order[item["severity"]], item["occurred_at"], item["reference"]))
    counts = {
        severity: sum(item["severity"] == severity for item in items)
        for severity in ("critical", "high", "medium", "low")
    }
    return {
        "generated_at": observed.isoformat(),
        "mode": "read_only_exception_projection",
        "owners": {
            "operations": operations_owner,
            "kill_switch": kill_owner,
            "ownership_ready": "UNASSIGNED" not in {operations_owner, kill_owner},
        },
        "counts": {**counts, "total": len(items)},
        "items": items,
        "live_lending": live_lending_readiness(),
        "daily_rule": (
            "Operations reviews every item daily; any critical consent, tenant, audit, "
            "security or payment anomaly stops the affected flow."
        ),
    }
