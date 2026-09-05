"""Fail-closed, data-driven authority boundary for Investigator V1."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any


class AuthorityDenied(PermissionError):
    """Raised when a principal requests authority not explicitly granted."""


_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "investigator-authority-v1.json"
)
_ALLOWED_EFFECTS = frozenset(
    {
        "INVESTIGATION_RECORD",
        "READ_INVESTIGATION_RECORD",
        "SNAPSHOT_RECORD",
        "READ_SNAPSHOT_RECORD",
    }
)
_PHASE0_PRINCIPALS = ["investigator_runtime"]
_PHASE1_EVENT_TYPES = [
    "CASE_CREATED",
    "INVESTIGATION_EVENT_RECORDED",
    "CASE_SNAPSHOT_INVALIDATED",
]
_PHASE0_OBJECTS = {
    "investigator.investigation_case",
    "investigator.investigation_event",
    "investigator.create_case",
    "investigator.append_event",
    "investigator.session_tenant_id",
    "investigator.context_tenant_id",
    "investigator.tenant_access_allowed",
}
_PHASE1_OBJECTS = _PHASE0_OBJECTS | {
    "investigator.case_snapshot",
    "investigator.case_snapshot_invalidation",
    "investigator.case_snapshot_request",
    "investigator.create_snapshot",
    "investigator.invalidate_snapshot",
    "investigator.is_snapshot_current",
}
_PHASE0_ENVIRONMENT = {
    "HOME",
    "HOSTNAME",
    "LANG",
    "LC_ALL",
    "LOG_LEVEL",
    "OLIN_INVESTIGATOR_AUTH_AUDIENCE",
    "OLIN_INVESTIGATOR_AUTH_ISSUER",
    "OLIN_INVESTIGATOR_DATABASE_URL",
    "PATH",
    "PORT",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "TMPDIR",
    "TZ",
}
_PHASE0_ALLOWS = {
    "case.create": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "INVESTIGATION_RECORD",
        "reads": [],
        "writes": [
            "investigator.investigation_case",
            "investigator.investigation_event",
        ],
    },
    "case.read": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "READ_INVESTIGATION_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
        ],
        "writes": [],
    },
    "event.append": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "INVESTIGATION_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
        ],
        "writes": [
            "investigator.investigation_case",
            "investigator.investigation_event",
        ],
    },
}
_PHASE1_ALLOWS = {
    **_PHASE0_ALLOWS,
    "snapshot.create": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "SNAPSHOT_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
        ],
        "writes": [
            "investigator.case_snapshot",
            "investigator.case_snapshot_request",
        ],
    },
    "snapshot.read": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "READ_SNAPSHOT_RECORD",
        "reads": [
            "investigator.case_snapshot",
            "investigator.case_snapshot_invalidation",
            "investigator.is_snapshot_current",
        ],
        "writes": [],
    },
    "snapshot.invalidate": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "SNAPSHOT_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
            "investigator.case_snapshot",
            "investigator.case_snapshot_invalidation",
        ],
        "writes": [
            "investigator.investigation_case",
            "investigator.investigation_event",
            "investigator.case_snapshot_invalidation",
        ],
    },
}
_REQUIRED_DENIES = {
    "credit.approve": "CREDIT_APPROVE",
    "credit.decline": "CREDIT_DECLINE",
    "credit.price": "PRICE_SET",
    "credit.terms.set": "AUTHORITATIVE_TERMS_SET",
    "credit.limit.change": "LIMIT_CHANGE",
    "money.disburse": "DISBURSE",
    "money.collect": "COLLECT",
    "facility.graduate": "GRADUATE",
    "repayment.trigger": "REPAYMENT_TRIGGER",
    "bank_policy.override": "POLICY_OVERRIDE",
    "verified_evidence.mutate": "VERIFIED_EVIDENCE_MUTATE",
    "permission.grant": "PERMISSION_GRANT",
    "money_credentials.read": "MONEY_CREDENTIAL_READ",
    "provider.call": "EXTERNAL_ACQUISITION",
    "ai.invoke": "AI_REASONING",
}


def _validate_contract(contract: dict) -> None:
    if contract.get("contract_version") != "investigator-authority-1.1":
        raise RuntimeError("Unsupported Investigator authority contract")
    if contract.get("deployment_profile") != "investigator_v1_phase1":
        raise RuntimeError("Investigator deployment profile must be Phase 1")
    if contract.get("default") != "deny":
        raise RuntimeError("Investigator authority contract must default to deny")
    principals = contract.get("principals")
    capabilities = contract.get("capabilities")
    if not isinstance(principals, list) or not all(
        isinstance(item, str) for item in principals
    ):
        raise TypeError("Investigator authority principals are invalid")
    if len(principals) != len(set(principals)):
        raise RuntimeError("Investigator authority principals must be unique")
    if principals != _PHASE0_PRINCIPALS:
        raise RuntimeError("Investigator Phase 0 principal must be exact")
    if not isinstance(capabilities, dict):
        raise TypeError("Investigator authority capabilities are missing")
    surfaces = contract.get("forbidden_surfaces")
    allowed_objects = contract.get("allowed_database_objects")
    if not isinstance(surfaces, dict) or not isinstance(allowed_objects, list):
        raise TypeError("Investigator authority surfaces are invalid")
    forbidden_tables = set(surfaces.get("database_tables", []))
    if forbidden_tables.intersection(allowed_objects):
        raise RuntimeError("A forbidden database object is allowlisted")
    if set(allowed_objects) != _PHASE1_OBJECTS:
        raise RuntimeError("Investigator Phase 1 database objects must be exact")
    if contract.get("allowed_routes") != []:
        raise RuntimeError("Investigator Phase 0 exposes no routes")
    if contract.get("allowed_event_types") != _PHASE1_EVENT_TYPES:
        raise RuntimeError("Investigator Phase 1 event types must be exact")
    allowed_environment = contract.get("allowed_environment_variables")
    if not isinstance(allowed_environment, list) or len(allowed_environment) != len(
        set(allowed_environment)
    ):
        raise TypeError("Investigator allowed environment names are invalid")
    forbidden_names = set(surfaces.get("environment_variables", []))
    forbidden_prefixes = tuple(surfaces.get("environment_prefixes", []))
    if set(allowed_environment) != _PHASE0_ENVIRONMENT:
        raise RuntimeError("Investigator Phase 0 environment allowlist must be exact")
    for name in allowed_environment:
        if name in forbidden_names or name.startswith(forbidden_prefixes):
            raise RuntimeError(f"Forbidden environment name is allowlisted: {name}")

    principal_set = set(principals)
    for name, rule in capabilities.items():
        if not isinstance(rule, dict) or rule.get("decision") not in {"allow", "deny"}:
            raise RuntimeError(f"Invalid capability rule: {name}")
        rule_principals = rule.get("principals")
        if (
            not isinstance(rule_principals, list)
            or not set(rule_principals) <= principal_set
        ):
            raise RuntimeError(f"Capability has unknown principals: {name}")
        if rule["decision"] == "deny" and rule_principals:
            raise RuntimeError(f"Denied capability grants principals: {name}")
        if rule["decision"] == "allow":
            if rule.get("effect") not in _ALLOWED_EFFECTS:
                raise RuntimeError(f"Capability grants a forbidden effect: {name}")
            for field in ("reads", "writes"):
                objects = rule.get(field)
                if not isinstance(objects, list) or not set(objects) <= set(
                    allowed_objects
                ):
                    raise RuntimeError(
                        f"Capability references unauthorized objects: {name}.{field}"
                    )
    for name, effect in _REQUIRED_DENIES.items():
        rule = capabilities.get(name)
        if rule != {"decision": "deny", "principals": [], "effect": effect}:
            raise RuntimeError(
                f"Required authority denial is absent or changed: {name}"
            )
    expected_capabilities = set(_PHASE1_ALLOWS) | set(_REQUIRED_DENIES)
    if set(capabilities) != expected_capabilities:
        raise RuntimeError("Investigator Phase 0 capability set must be exact")
    for name, expected in _PHASE1_ALLOWS.items():
        if capabilities[name] != expected:
            raise RuntimeError(f"Allowed capability is not exact: {name}")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@lru_cache(maxsize=1)
def authority_contract() -> Mapping[str, Any]:
    """Load, validate, and freeze the sole Investigator authority contract."""
    with _CONTRACT_PATH.open(encoding="utf-8") as handle:
        contract = json.load(handle)
    _validate_contract(contract)
    return _freeze(contract)


def is_allowed(principal: str, capability: str) -> bool:
    """Return true only for an exact principal/capability allowlist match."""
    contract = authority_contract()
    if principal not in contract["principals"]:
        return False
    rule = contract["capabilities"].get(capability)
    return bool(
        isinstance(rule, Mapping)
        and rule.get("decision") == "allow"
        and principal in rule.get("principals", [])
    )


def require_capability(principal: str, capability: str) -> None:
    """Enforce the contract without overrides, wildcards, or fallback roles."""
    if not is_allowed(principal, capability):
        raise AuthorityDenied(f"{principal!r} is not allowed {capability!r}")


def forbidden_environment_names(environment: Mapping[str, str]) -> list[str]:
    """Return non-allowlisted names without reading their values."""
    allowed = set(authority_contract()["allowed_environment_variables"])
    return sorted(name for name in environment if name not in allowed)


def assert_runtime_environment(environment: Mapping[str, str]) -> None:
    """Fail startup if an Investigator process receives forbidden authority."""
    names = forbidden_environment_names(environment)
    if names:
        raise AuthorityDenied(
            "Investigator runtime contains forbidden environment names: "
            + ", ".join(names)
        )
