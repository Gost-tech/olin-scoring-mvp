from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from olin.investigator.authority import (
    AuthorityDenied,
    _validate_contract,
    assert_runtime_environment,
    authority_contract,
    is_allowed,
    require_capability,
)

ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "config" / "investigator-authority-v1.json"
SCHEMA_PATH = ROOT / "config" / "investigator-authority.schema.json"
MIGRATION_PATH = ROOT / "db" / "migrations" / "0001_investigator_phase0.sql"
PHASE1_MIGRATION_PATH = (
    ROOT / "db" / "migrations" / "0002_investigator_case_event_snapshot.sql"
)

PROHIBITED_CAPABILITIES = {
    "credit.approve",
    "credit.decline",
    "credit.price",
    "credit.terms.set",
    "credit.limit.change",
    "money.disburse",
    "money.collect",
    "facility.graduate",
    "repayment.trigger",
    "bank_policy.override",
    "verified_evidence.mutate",
    "permission.grant",
    "money_credentials.read",
    "provider.call",
    "ai.invoke",
}


class InvestigatorAuthorityContractTests(unittest.TestCase):
    def setUp(self):
        authority_contract.cache_clear()

    def test_contract_and_schema_are_valid_json(self):
        contract = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["contract_version"], "investigator-authority-1.1")
        self.assertEqual(contract["default"], "deny")
        self.assertEqual(schema["properties"]["default"]["const"], "deny")
        self.assertEqual(len(contract["principals"]), len(set(contract["principals"])))
        self.assertEqual(contract["allowed_routes"], [])
        self.assertEqual(
            contract["allowed_event_types"],
            [
                "CASE_CREATED",
                "INVESTIGATION_EVENT_RECORDED",
                "CASE_SNAPSHOT_INVALIDATED",
            ],
        )
        self.assertEqual(
            set(contract["allowed_database_objects"]),
            {
                "investigator.investigation_case",
                "investigator.investigation_event",
                "investigator.case_snapshot",
                "investigator.case_snapshot_invalidation",
                "investigator.case_snapshot_request",
                "investigator.create_case",
                "investigator.append_event",
                "investigator.create_snapshot",
                "investigator.invalidate_snapshot",
                "investigator.is_snapshot_current",
                "investigator.session_tenant_id",
                "investigator.context_tenant_id",
                "investigator.tenant_access_allowed",
            },
        )

    def test_every_prohibited_capability_is_an_explicit_unconditional_deny(self):
        contract = authority_contract()
        self.assertTrue(PROHIBITED_CAPABILITIES.issubset(contract["capabilities"]))
        for capability in PROHIBITED_CAPABILITIES:
            rule = contract["capabilities"][capability]
            self.assertEqual(rule["decision"], "deny", capability)
            self.assertEqual(rule["principals"], (), capability)
            for principal in contract["principals"]:
                self.assertFalse(
                    is_allowed(principal, capability), (principal, capability)
                )

    def test_unknown_principal_and_capability_fail_closed(self):
        self.assertFalse(is_allowed("admin", "case.read"))
        self.assertFalse(is_allowed("investigator_runtime", "unknown.capability"))
        with self.assertRaises(AuthorityDenied):
            require_capability("investigator_runtime", "money.disburse")
        with self.assertRaises(AuthorityDenied):
            require_capability("investigator_runtime", "unknown.capability")

    def test_positive_authority_is_exact_and_minimal(self):
        self.assertTrue(is_allowed("investigator_runtime", "case.create"))
        self.assertTrue(is_allowed("investigator_runtime", "case.read"))
        self.assertTrue(is_allowed("investigator_runtime", "event.append"))
        self.assertTrue(is_allowed("investigator_runtime", "snapshot.create"))
        self.assertTrue(is_allowed("investigator_runtime", "snapshot.read"))
        self.assertTrue(is_allowed("investigator_runtime", "snapshot.invalidate"))
        allowed = {
            name
            for name, rule in authority_contract()["capabilities"].items()
            if rule["decision"] == "allow"
        }
        self.assertEqual(
            allowed,
            {
                "case.create",
                "case.read",
                "event.append",
                "snapshot.create",
                "snapshot.read",
                "snapshot.invalidate",
            },
        )

    def test_caller_verified_label_never_grants_trust_or_evidence_mutation(self):
        contract = authority_contract()
        self.assertIn("verified", contract["forbidden_surfaces"]["caller_trust_labels"])
        self.assertFalse(is_allowed("investigator_runtime", "verified_evidence.mutate"))

    def test_forbidden_environment_names_fail_without_exposing_values(self):
        secret = "must-not-appear-in-error"
        with self.assertRaises(AuthorityDenied) as caught:
            assert_runtime_environment({"STP_PRIVATE_KEY_PATH": secret})
        self.assertNotIn(secret, str(caught.exception))
        assert_runtime_environment(
            {
                "OLIN_INVESTIGATOR_DATABASE_URL": "redacted",
                "OLIN_INVESTIGATOR_AUTH_ISSUER": "redacted",
            }
        )

    def test_loaded_contract_is_immutable(self):
        with self.assertRaises(TypeError):
            authority_contract()["default"] = "allow"
        with self.assertRaises(TypeError):
            authority_contract()["capabilities"]["money.disburse"]["decision"] = "allow"

    def test_cross_field_contract_validation_fails_closed(self):
        original = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        mutations = []

        unknown_principal = copy.deepcopy(original)
        unknown_principal["capabilities"]["case.read"]["principals"] = ["admin"]
        mutations.append(unknown_principal)

        forbidden_effect = copy.deepcopy(original)
        forbidden_effect["capabilities"]["case.read"]["effect"] = "DISBURSE"
        mutations.append(forbidden_effect)

        forbidden_object = copy.deepcopy(original)
        forbidden_object["capabilities"]["case.read"]["reads"] = ["public.scoring_log"]
        mutations.append(forbidden_object)

        missing_deny = copy.deepcopy(original)
        del missing_deny["capabilities"]["credit.approve"]
        mutations.append(missing_deny)

        route_added = copy.deepcopy(original)
        route_added["allowed_routes"] = ["POST /api/investigator"]
        mutations.append(route_added)

        event_added = copy.deepcopy(original)
        event_added["allowed_event_types"].append("CREDIT_APPROVED")
        mutations.append(event_added)

        forbidden_environment = copy.deepcopy(original)
        forbidden_environment["allowed_environment_variables"].append("STP_PRIVATE_KEY")
        mutations.append(forbidden_environment)

        benign_environment = copy.deepcopy(original)
        benign_environment["allowed_environment_variables"].append("AWS_REGION")
        mutations.append(benign_environment)

        extra_principal = copy.deepcopy(original)
        extra_principal["principals"].append("investigator_shadow")
        mutations.append(extra_principal)

        changed_profile = copy.deepcopy(original)
        changed_profile["deployment_profile"] = "expanded"
        mutations.append(changed_profile)

        extra_allow = copy.deepcopy(original)
        extra_allow["capabilities"]["case.inspect"] = copy.deepcopy(
            original["capabilities"]["case.read"]
        )
        mutations.append(extra_allow)

        for mutated in mutations:
            with self.subTest(), self.assertRaises((RuntimeError, TypeError)):
                _validate_contract(mutated)

    def test_investigator_package_has_no_forbidden_imports(self):
        forbidden = tuple(authority_contract()["forbidden_surfaces"]["python_modules"])
        violations: list[str] = []
        for path in (ROOT / "olin" / "investigator").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        names = [node.module or ""]
                    elif node.level == 2 and node.module:
                        names = [f"olin.{node.module}"]
                    elif node.level == 2:
                        names = [f"olin.{alias.name}" for alias in node.names]
                for name in names:
                    if any(
                        name == item or name.startswith(item + ".")
                        for item in forbidden
                    ):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}:{name}"
                        )
        self.assertEqual(violations, [])

    def test_importing_investigator_does_not_load_forbidden_modules(self):
        code = """
import json, sys
import olin.investigator
from olin.investigator.authority import authority_contract
forbidden = authority_contract()['forbidden_surfaces']['python_modules']
print(json.dumps([name for name in forbidden if name in sys.modules]))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_phase0_has_no_investigator_http_entrypoint_or_routes(self):
        self.assertFalse((ROOT / "olin" / "investigator" / "server.py").exists())
        self.assertEqual(authority_contract()["allowed_routes"], ())

    def test_migration_contains_fail_closed_postgres_controls(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        required = (
            "create role olin_investigator_runtime",
            "nologin nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls",
            "alter table investigator.investigation_case enable row level security",
            "alter table investigator.investigation_case force row level security",
            "alter table investigator.investigation_event enable row level security",
            "alter table investigator.investigation_event force row level security",
            "using (investigator.tenant_access_allowed(tenant_id))",
            "with check (investigator.tenant_access_allowed(tenant_id))",
            "revoke all on all tables in schema public from olin_investigator_runtime",
            "granted_role.rolname in ('olin_investigator_owner', 'olin_investigator_runtime')",
            "investigator runtime inherits create on non-investigator schema",
            "investigator runtime inherits execute on non-investigator routine",
            "relation.relkind in ('r', 'p', 'v', 'm', 's', 'f')",
            "commit;",
        )
        for fragment in required:
            self.assertIn(fragment, sql)
        self.assertNotIn("grant insert on investigator.investigation_event", sql)
        self.assertNotIn("grant update on investigator.investigation_event", sql)
        self.assertNotIn("grant delete on investigator.investigation_event", sql)

    def test_phase1_migration_is_additive_immutable_and_tenant_bound(self):
        sql = PHASE1_MIGRATION_PATH.read_text(encoding="utf-8").lower()
        required = (
            "create table investigator.case_snapshot",
            "create table investigator.case_snapshot_invalidation",
            "alter table investigator.case_snapshot enable row level security",
            "alter table investigator.case_snapshot force row level security",
            "alter table investigator.case_snapshot_invalidation enable row level security",
            "alter table investigator.case_snapshot_invalidation force row level security",
            "create trigger case_snapshot_immutable",
            "create trigger investigation_event_immutable",
            "phase 1 requires an empty phase 0 case/event store",
            "create trigger case_snapshot_invalidation_immutable",
            "create function investigator.create_snapshot",
            "create function investigator.invalidate_snapshot",
            "create function investigator.is_snapshot_current",
            "grant select on investigator.case_snapshot to olin_investigator_runtime",
            "grant select on investigator.case_snapshot_invalidation to olin_investigator_runtime",
            "grant select on investigator.investigation_case to olin_investigator_runtime",
            "grant select on investigator.investigation_event to olin_investigator_runtime",
        )
        for fragment in required:
            self.assertIn(fragment, sql)
        self.assertNotIn("grant insert on investigator.case_snapshot", sql)
        self.assertNotIn("grant update on investigator.case_snapshot", sql)
        self.assertNotIn("grant delete on investigator.case_snapshot", sql)
        self.assertNotIn("public.scoring_log", sql)
        self.assertNotIn("payment_ledger", sql)


if __name__ == "__main__":
    unittest.main()
