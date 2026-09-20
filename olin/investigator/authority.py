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


class RuntimeDatabaseCustody:
    """Opaque guard that rechecks the bound runtime connection on every use."""

    __slots__ = ("_connection",)

    def __new__(cls):
        raise TypeError("use establish_runtime_database_custody")

    @classmethod
    def _establish(cls, connection: Any) -> RuntimeDatabaseCustody:
        assert_runtime_database_custody(connection)
        instance = object.__new__(cls)
        instance._connection = connection
        return instance

    def require_current(self) -> None:
        assert_runtime_database_custody(self._connection)

    def require_connection(self, connection: Any) -> None:
        """Recheck custody and bind it to the exact connection being used."""
        if connection is not self._connection:
            raise AuthorityDenied(
                "runtime database custody does not cover the requested connection"
            )
        self.require_current()


_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "investigator-authority-v1.json"
)
_ALLOWED_EFFECTS = frozenset(
    {
        "INVESTIGATION_RECORD",
        "READ_INVESTIGATION_RECORD",
        "SNAPSHOT_RECORD",
        "READ_SNAPSHOT_RECORD",
        "READ_EVIDENCE_REFERENCE",
        "REASONING_CURRENTNESS_GATE",
        "INVESTIGATION_ACTION_RECORD",
        "READ_INVESTIGATION_ACTION_RECORD",
    }
)
_PHASE0_PRINCIPALS = ["investigator_runtime", "investigator_action_writer"]
_PHASE1_EVENT_TYPES = [
    "CASE_CREATED",
    "INVESTIGATION_EVENT_RECORDED",
    "CASE_SNAPSHOT_INVALIDATED",
]
_PHASE2_EVENT_TYPES = _PHASE1_EVENT_TYPES + [
    "EVIDENCE_ACCEPTED",
    "EVIDENCE_BECAME_UNUSABLE",
    "CONSENT_STATE_CHANGED",
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
_PHASE2_OBJECTS = _PHASE1_OBJECTS | {
    "investigator.investigation_evidence_reference",
    "investigator.investigation_evidence_semantics",
    "investigator.create_snapshot_v2",
    "investigator.current_canonical_authority_revision",
}
_PHASE5_OBJECTS = _PHASE2_OBJECTS | {
    "evidence_authority.investigator_evidence_projection_change",
    "investigator.investigation_action",
    "investigator.investigation_action_transition",
    "investigator.action_session_tenant_id",
    "investigator.action_tenant_access_allowed",
    "investigator.select_investigation_action",
    "investigator.transition_investigation_action",
    "investigator.read_investigation_actions",
}
_PHASE0_ENVIRONMENT = {
    "HOME",
    "HOSTNAME",
    "LANG",
    "LC_ALL",
    "LOG_LEVEL",
    "OLIN_INVESTIGATOR_AUTH_AUDIENCE",
    "OLIN_INVESTIGATOR_AUTH_ISSUER",
    "OLIN_INVESTIGATOR_ACTION_DATABASE_URL",
    "OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL",
    "OLIN_INVESTIGATOR_DATABASE_URL",
    "OLIN_INVESTIGATOR_SESSION_SECRET",
    "OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_TOKEN",
    "OLIN_INVESTIGATOR_SYNTHETIC_OPERATOR_URL",
    "OLIN_INVESTIGATOR_USERS",
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
_PHASE2_ALLOWS = {
    **_PHASE1_ALLOWS,
    "evidence.reference.read": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "READ_EVIDENCE_REFERENCE",
        "reads": [
            "investigator.investigation_evidence_reference",
            "investigator.investigation_evidence_semantics",
        ],
        "writes": [],
    },
    "snapshot.v2.create": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "SNAPSHOT_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
            "investigator.investigation_evidence_reference",
        ],
        "writes": [
            "investigator.case_snapshot",
            "investigator.case_snapshot_request",
        ],
    },
    "snapshot.reasoning.require": {
        "decision": "allow",
        "principals": ["investigator_runtime"],
        "effect": "REASONING_CURRENTNESS_GATE",
        "reads": [
            "investigator.investigation_case",
            "investigator.investigation_event",
            "investigator.case_snapshot",
            "investigator.case_snapshot_invalidation",
            "investigator.investigation_evidence_reference",
            "investigator.investigation_evidence_semantics",
            "investigator.current_canonical_authority_revision",
        ],
        "writes": [],
    },
}
_PHASE5_ALLOWS = {
    **_PHASE2_ALLOWS,
    "investigation_action.select": {
        "decision": "allow",
        "principals": ["investigator_action_writer"],
        "effect": "INVESTIGATION_ACTION_RECORD",
        "reads": [
            "investigator.investigation_case",
            "investigator.case_snapshot",
            "investigator.case_snapshot_invalidation",
            "evidence_authority.investigator_evidence_projection_change",
        ],
        "writes": [
            "investigator.investigation_action",
            "investigator.investigation_action_transition",
        ],
    },
    "investigation_action.transition": {
        "decision": "allow",
        "principals": ["investigator_action_writer"],
        "effect": "INVESTIGATION_ACTION_RECORD",
        "reads": [
            "investigator.investigation_action",
            "investigator.investigation_action_transition",
        ],
        "writes": ["investigator.investigation_action_transition"],
    },
    "investigation_action.read": {
        "decision": "allow",
        "principals": ["investigator_action_writer"],
        "effect": "READ_INVESTIGATION_ACTION_RECORD",
        "reads": [
            "investigator.investigation_action",
            "investigator.investigation_action_transition",
        ],
        "writes": [],
    },
}
_PHASE5_ROUTES = [
    "GET /investigator",
    "POST /api/session",
    "GET /api/cases/{case_id}",
    "GET /api/cases/{case_id}/actions",
    "POST /api/cases/{case_id}/actions",
    "POST /api/cases/{case_id}/actions/{action_id}/transitions",
    "POST /api/cases/{case_id}/actions/{action_id}/synthetic-response",
]
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
    "canonical_evidence.delete": "CANONICAL_EVIDENCE_DELETE",
    "source_trust.grant": "SOURCE_TRUST_GRANT",
    "consent.create": "CONSENT_CREATE",
    "consent.approve": "CONSENT_APPROVE",
    "consent.receipt.mutate": "CONSENT_RECEIPT_MUTATE",
    "permission.grant": "PERMISSION_GRANT",
    "money_credentials.read": "MONEY_CREDENTIAL_READ",
    "provider.call": "EXTERNAL_ACQUISITION",
    "ai.invoke": "AI_REASONING",
}


def _validate_contract(contract: dict) -> None:
    if contract.get("contract_version") != "investigator-authority-1.5":
        raise RuntimeError("Unsupported Investigator authority contract")
    if contract.get("deployment_profile") != "investigator_v1_phase6":
        raise RuntimeError("Investigator deployment profile must be Phase 6")
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
        raise RuntimeError("Investigator Phase 5A principals must be exact")
    if not isinstance(capabilities, dict):
        raise TypeError("Investigator authority capabilities are missing")
    surfaces = contract.get("forbidden_surfaces")
    allowed_objects = contract.get("allowed_database_objects")
    if not isinstance(surfaces, dict) or not isinstance(allowed_objects, list):
        raise TypeError("Investigator authority surfaces are invalid")
    forbidden_tables = set(surfaces.get("database_tables", []))
    if forbidden_tables.intersection(allowed_objects):
        raise RuntimeError("A forbidden database object is allowlisted")
    if set(allowed_objects) != _PHASE5_OBJECTS:
        raise RuntimeError("Investigator Phase 5A database objects must be exact")
    report_route = "GET /api/cases/{case_id}/report"
    routes = contract.get("allowed_routes")
    if (
        not isinstance(routes, list)
        or routes.count(report_route) != 1
        or [route for route in routes if route != report_route] != _PHASE5_ROUTES
    ):
        raise RuntimeError(
            "Investigator Phase 5A routes plus one read-only report route must be exact"
        )
    if contract.get("allowed_event_types") != _PHASE2_EVENT_TYPES:
        raise RuntimeError("Investigator Phase 2 event types must be exact")
    allowed_environment = contract.get("allowed_environment_variables")
    prohibited_environment = contract.get("prohibited_environment_variables")
    if not isinstance(prohibited_environment, list) or len(
        prohibited_environment
    ) != len(set(prohibited_environment)):
        raise TypeError("Investigator prohibited environment names are invalid")
    if not isinstance(allowed_environment, list) or len(allowed_environment) != len(
        set(allowed_environment)
    ):
        raise TypeError("Investigator allowed environment names are invalid")
    forbidden_names = set(surfaces.get("environment_variables", []))
    forbidden_prefixes = tuple(surfaces.get("environment_prefixes", []))
    if set(allowed_environment) != _PHASE0_ENVIRONMENT:
        raise RuntimeError("Investigator Phase 5A environment allowlist must be exact")
    for name in allowed_environment:
        if name in forbidden_names or name.startswith(forbidden_prefixes):
            raise RuntimeError(f"Forbidden environment name is allowlisted: {name}")
    if set(allowed_environment).intersection(prohibited_environment):
        raise RuntimeError("Prohibited environment name is allowlisted")

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
    expected_capabilities = set(_PHASE5_ALLOWS) | set(_REQUIRED_DENIES)
    if set(capabilities) != expected_capabilities:
        raise RuntimeError("Investigator Phase 2 capability set must be exact")
    for name, expected in _PHASE5_ALLOWS.items():
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
    prohibited = set(authority_contract().get("prohibited_environment_variables", ()))
    present = sorted(name for name in environment if name in prohibited)
    if present:
        raise AuthorityDenied(
            "Investigator runtime contains prohibited authority credentials: "
            + ", ".join(present)
        )
    names = forbidden_environment_names(environment)
    if names:
        raise AuthorityDenied(
            "Investigator runtime contains forbidden environment names: "
            + ", ".join(names)
        )


def assert_runtime_database_custody(connection: Any) -> None:
    """Fail startup unless this session is the isolated Investigator runtime."""
    cursor = connection.execute(
        "SELECT current_user = 'olin_investigator_runtime', "
        "pg_has_role(session_user, 'olin_investigator_runtime', 'member'), "
        "pg_has_role(session_user, 'olin_investigator_evidence_authority', 'member'), "
        "pg_has_role(session_user, 'olin_investigator_owner', 'member'), "
        "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
        "OR rolreplication OR rolbypassrls) FROM pg_roles "
        "WHERE rolname=session_user),false), "
        "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
        "OR rolreplication OR rolbypassrls) FROM pg_roles "
        "WHERE rolname=current_user),false), "
        "NOT EXISTS (SELECT 1 FROM ("
        "SELECT (aclexplode(relacl)).grantee FROM pg_class UNION ALL "
        "SELECT (aclexplode(proacl)).grantee FROM pg_proc UNION ALL "
        "SELECT (aclexplode(nspacl)).grantee FROM pg_namespace) direct_acl "
        "JOIN pg_roles grantee ON grantee.oid=direct_acl.grantee "
        "WHERE grantee.rolname=session_user), "
        "NOT EXISTS (WITH RECURSIVE memberships(roleid) AS ("
        "SELECT membership.roleid FROM pg_auth_members membership "
        "JOIN pg_roles login ON login.oid=membership.member "
        "WHERE login.rolname=session_user UNION "
        "SELECT membership.roleid FROM pg_auth_members membership "
        "JOIN memberships prior ON membership.member=prior.roleid) "
        "SELECT 1 FROM memberships "
        "JOIN pg_roles granted ON granted.oid=memberships.roleid "
        "WHERE granted.rolname <> 'olin_investigator_runtime')"
    )
    row = cursor.fetchone()
    if row is None or tuple(row) != (
        True,
        True,
        False,
        False,
        True,
        True,
        True,
        True,
    ):
        raise AuthorityDenied(
            "Investigator runtime database identity or credential custody is ambiguous"
        )


def assert_evidence_authority_database_custody(connection: Any) -> None:
    """Reject a privileged or mixed-membership evidence-authority login."""
    row = connection.execute(
        "SELECT current_user = 'olin_investigator_evidence_authority', "
        "pg_has_role(session_user, "
        "'olin_investigator_evidence_authority', 'member'), "
        "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
        "OR rolreplication OR rolbypassrls) FROM pg_roles "
        "WHERE rolname=session_user),false), "
        "COALESCE((SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb "
        "OR rolreplication OR rolbypassrls) FROM pg_roles "
        "WHERE rolname=current_user),false), "
        "NOT EXISTS (SELECT 1 FROM ("
        "SELECT (aclexplode(relacl)).grantee FROM pg_class UNION ALL "
        "SELECT (aclexplode(proacl)).grantee FROM pg_proc UNION ALL "
        "SELECT (aclexplode(nspacl)).grantee FROM pg_namespace) direct_acl "
        "JOIN pg_roles grantee ON grantee.oid=direct_acl.grantee "
        "WHERE grantee.rolname=session_user), "
        "NOT EXISTS (WITH RECURSIVE memberships(roleid) AS ("
        "SELECT membership.roleid FROM pg_auth_members membership "
        "JOIN pg_roles login ON login.oid=membership.member "
        "WHERE login.rolname=session_user UNION "
        "SELECT membership.roleid FROM pg_auth_members membership "
        "JOIN memberships prior ON membership.member=prior.roleid) "
        "SELECT 1 FROM memberships "
        "JOIN pg_roles granted ON granted.oid=memberships.roleid "
        "WHERE granted.rolname <> 'olin_investigator_evidence_authority')"
    ).fetchone()
    if row is None or tuple(row) != (True, True, True, True, True, True):
        raise AuthorityDenied(
            "Evidence-authority database identity or credential custody is ambiguous"
        )


def establish_runtime_database_custody(connection: Any) -> RuntimeDatabaseCustody:
    """Establish the only custody guard accepted by the reasoning boundary."""
    return RuntimeDatabaseCustody._establish(connection)
