"""Fail-closed governance gate for Olin's bank-controlled pilot.

This module validates declared pilot evidence.  It does not authenticate an
approval or replace a bank's security, privacy, model-risk, or credit sign-off.
"""
from __future__ import annotations

from datetime import date
from typing import Any


OWNER_ROLES = (
    "credit_risk",
    "model_risk",
    "security",
    "privacy",
    "engineering",
    "operations",
    "procurement",
)

SHADOW_APPROVALS = (
    "shadow_pilot_agreement",
    "security_review",
    "privacy_review",
    "consent_workflow",
    "model_risk_scope",
    "outcome_data_access",
    "paid_conversion_path",
)

REQUIRED_ROUTES = {"inventory_led", "tpv_led", "bank_flow_led"}

REQUIRED_STOP_CONDITIONS = {
    "cross_tenant_exposure",
    "consent_bypass",
    "unverifiable_evidence",
    "corrupted_audit_history",
    "high_severity_security_event",
    "unauthorized_money_movement",
}

REQUIRED_SUCCESS_CRITERIA = {
    "consent_coverage_pct": 100,
    "provenance_coverage_pct": 100,
    "reconstructable_recommendations_pct": 100,
    "bank_outcome_coverage_pct": 100,
    "unauthorized_money_movement_events": 0,
}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "TODO" not in value.upper()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_pilot_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic verdict and actionable blockers.

    The manifest is intentionally stricter for a controlled shadow pilot than
    for synthetic UAT.  Real-data production is outside this gate's scope and
    always fails closed.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "verdict": "NO_GO",
            "stage": None,
            "blockers": ["Manifest must be a JSON object."],
            "warnings": [],
            "evidence_independently_verified": False,
        }

    stage = manifest.get("stage")
    if stage not in {"synthetic_uat", "controlled_shadow", "real_data_production"}:
        blockers.append(
            "stage must be synthetic_uat, controlled_shadow, or real_data_production."
        )

    for field in ("pilot_id", "institution"):
        if not _text(manifest.get(field)):
            blockers.append(f"{field} must be named and cannot be a placeholder.")

    if stage == "real_data_production":
        blockers.append(
            "Real-data production is outside the controlled-shadow gate; use the "
            "production control and model-validation program."
        )

    owners = _mapping(manifest.get("owners"))
    for role in OWNER_ROLES:
        if not _text(owners.get(role)):
            blockers.append(f"owners.{role} must name one accountable person.")

    cohort = _mapping(manifest.get("cohort"))
    case_ceiling = cohort.get("case_ceiling")
    if not isinstance(case_ceiling, int) or isinstance(case_ceiling, bool):
        blockers.append("cohort.case_ceiling must be an integer.")
    elif case_ceiling < 1 or case_ceiling > 10:
        blockers.append("cohort.case_ceiling must be between 1 and 10 for this pilot.")

    routes = cohort.get("evidence_routes", [])
    route_set = {item for item in routes if isinstance(item, str)} if isinstance(routes, list) else set()
    missing_routes = sorted(REQUIRED_ROUTES - route_set)
    if missing_routes:
        blockers.append(
            "cohort.evidence_routes is missing: " + ", ".join(missing_routes) + "."
        )
    if not _text(cohort.get("selection_rule")):
        blockers.append("cohort.selection_rule must state how cases enter the pilot.")

    safeguards = _mapping(manifest.get("safeguards"))
    for control in ("shadow_only", "money_movement_disabled", "bank_makes_decision"):
        if safeguards.get(control) is not True:
            blockers.append(f"safeguards.{control} must be true.")
    if not _text(safeguards.get("kill_switch_owner")):
        blockers.append("safeguards.kill_switch_owner must name the person who stops intake.")
    stop_conditions = safeguards.get("stop_conditions", [])
    stop_set = (
        {item for item in stop_conditions if isinstance(item, str)}
        if isinstance(stop_conditions, list)
        else set()
    )
    missing_stops = sorted(REQUIRED_STOP_CONDITIONS - stop_set)
    if missing_stops:
        blockers.append(
            "safeguards.stop_conditions is missing: " + ", ".join(missing_stops) + "."
        )

    success = _mapping(manifest.get("success_criteria"))
    for metric, required in REQUIRED_SUCCESS_CRITERIA.items():
        if success.get(metric) != required:
            blockers.append(f"success_criteria.{metric} must equal {required}.")
    if not _text(success.get("turnaround_baseline_method")):
        blockers.append("success_criteria.turnaround_baseline_method must be defined by the bank.")
    turnaround_target = success.get("turnaround_target_minutes")
    if not isinstance(turnaround_target, (int, float)) or isinstance(turnaround_target, bool) or turnaround_target <= 0:
        blockers.append("success_criteria.turnaround_target_minutes must be a positive number.")

    outcomes = _mapping(manifest.get("outcome_contract"))
    if outcomes.get("bank_committed_to_deliver") is not True:
        blockers.append("outcome_contract.bank_committed_to_deliver must be true.")
    for field in ("outcome_label", "delivery_owner", "delivery_method", "evidence_ref"):
        if not _text(outcomes.get(field)):
            blockers.append(f"outcome_contract.{field} must be defined.")
    window = outcomes.get("observation_window_days")
    if not isinstance(window, int) or isinstance(window, bool) or window < 30:
        blockers.append("outcome_contract.observation_window_days must be at least 30.")

    if stage == "controlled_shadow":
        approvals = _mapping(manifest.get("approvals"))
        for approval_name in SHADOW_APPROVALS:
            approval = _mapping(approvals.get(approval_name))
            prefix = f"approvals.{approval_name}"
            if approval.get("approved") is not True:
                blockers.append(f"{prefix}.approved must be true.")
            for field in ("approver", "approved_at", "evidence_ref"):
                if not _text(approval.get(field)):
                    blockers.append(f"{prefix}.{field} must be recorded.")
            approved_at = approval.get("approved_at")
            if _text(approved_at):
                try:
                    date.fromisoformat(approved_at)
                except ValueError:
                    blockers.append(f"{prefix}.approved_at must use YYYY-MM-DD.")

    warnings.extend(
        [
            "Ten cases validate workflow and controls, not default prediction or calibration.",
            "Manifest evidence is declared, not independently authenticated by this tool.",
            "All SME categories remain human-review decision support until segment outcomes are validated.",
        ]
    )
    ok = not blockers
    verdict = "NO_GO"
    if ok and stage == "synthetic_uat":
        verdict = "GO_SYNTHETIC_UAT"
    elif ok and stage == "controlled_shadow":
        verdict = "READY_FOR_CONTROLLED_SHADOW"

    return {
        "ok": ok,
        "verdict": verdict,
        "stage": stage,
        "blockers": blockers,
        "warnings": warnings,
        "evidence_independently_verified": False,
    }
