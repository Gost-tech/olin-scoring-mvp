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
PHASE2_MIGRATION_PATH = (
    ROOT / "db" / "migrations" / "0003_investigator_evidence_consent_passport.sql"
)
PHASE25_MIGRATION_PATH = (
    ROOT / "db" / "migrations" / "0004_investigator_evidence_reasoning_readiness.sql"
)
PHASE3_MIGRATION_PATH = (
    ROOT / "db" / "migrations" / "0005_investigator_phase3_assertion_metadata.sql"
)
PHASE5A_MIGRATION_PATH = (
    ROOT / "db" / "migrations" / "0006_investigator_human_action_workflow.sql"
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
    "canonical_evidence.delete",
    "source_trust.grant",
    "consent.create",
    "consent.approve",
    "consent.receipt.mutate",
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
        self.assertEqual(contract["contract_version"], "investigator-authority-1.7")
        self.assertEqual(
            schema["properties"]["contract_version"]["const"],
            contract["contract_version"],
        )
        self.assertEqual(contract["default"], "deny")
        self.assertEqual(schema["properties"]["default"]["const"], "deny")
        self.assertEqual(len(contract["principals"]), len(set(contract["principals"])))
        self.assertEqual(
            contract["allowed_routes"].count("GET /api/cases/{case_id}/report"), 1
        )
        self.assertEqual(
            len(
                [
                    r
                    for r in contract["allowed_routes"]
                    if r
                    not in {
                        "GET /api/cases/{case_id}/report",
                        "GET /api/cases/{case_id}/feedback",
                        "POST /api/cases/{case_id}/feedback",
                        "GET /api/cohorts",
                        "GET /api/cases/{case_id}/shadow",
                        "POST /api/cases/{case_id}/shadow",
                        "POST /api/cases/{case_id}/shadow/{round_id}/generate",
                        "POST /api/cases/{case_id}/shadow/{round_id}/disclose",
                        "POST /api/cases/{case_id}/shadow/{round_id}/rate",
                        "POST /api/cases/{case_id}/shadow/{round_id}/history",
                    }
                ]
            ),
            7,
        )
        self.assertEqual(
            contract["allowed_event_types"],
            [
                "CASE_CREATED",
                "INVESTIGATION_EVENT_RECORDED",
                "CASE_SNAPSHOT_INVALIDATED",
                "EVIDENCE_ACCEPTED",
                "EVIDENCE_BECAME_UNUSABLE",
                "CONSENT_STATE_CHANGED",
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
                "investigator.investigation_evidence_reference",
                "investigator.investigation_evidence_semantics",
                "investigator.create_case",
                "investigator.append_event",
                "investigator.create_snapshot",
                "investigator.invalidate_snapshot",
                "investigator.is_snapshot_current",
                "investigator.create_snapshot_v2",
                "investigator.current_canonical_authority_revision",
                "investigator.session_tenant_id",
                "investigator.context_tenant_id",
                "investigator.tenant_access_allowed",
                "investigator.investigation_action",
                "investigator.investigation_action_transition",
                "investigator.action_session_tenant_id",
                "investigator.action_tenant_access_allowed",
                "investigator.select_investigation_action",
                "investigator.transition_investigation_action",
                "investigator.read_investigation_actions",
                "evidence_authority.investigator_evidence_projection_change",
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
        self.assertTrue(is_allowed("investigator_runtime", "evidence.reference.read"))
        self.assertTrue(is_allowed("investigator_runtime", "snapshot.v2.create"))
        self.assertTrue(
            is_allowed("investigator_runtime", "snapshot.reasoning.require")
        )
        self.assertTrue(
            is_allowed("investigator_action_writer", "investigation_action.select")
        )
        self.assertTrue(
            is_allowed("investigator_action_writer", "investigation_action.transition")
        )
        self.assertTrue(
            is_allowed("investigator_action_writer", "investigation_action.read")
        )
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
                "evidence.reference.read",
                "snapshot.v2.create",
                "snapshot.reasoning.require",
                "investigation_action.select",
                "investigation_action.transition",
                "investigation_action.read",
            },
        )

    def test_caller_verified_label_never_grants_trust_or_evidence_mutation(self):
        contract = authority_contract()
        self.assertEqual(
            set(contract["forbidden_surfaces"]["caller_trust_labels"]),
            {
                "verified",
                "trusted",
                "authoritative",
                "issuer_validated",
                "source_verified",
                "official",
                "validated",
                "independent",
                "independence_status",
                "semantic_lineage_id",
                "economic_event_id",
                "derived_from_evidence_id",
                "independence_attestation_id",
            },
        )
        self.assertFalse(is_allowed("investigator_runtime", "verified_evidence.mutate"))

    def test_forbidden_environment_names_fail_without_exposing_values(self):
        secret = "must-not-appear-in-error"
        with self.assertRaises(AuthorityDenied) as caught:
            assert_runtime_environment({"STP_PRIVATE_KEY_PATH": secret})
        self.assertNotIn(secret, str(caught.exception))
        with self.assertRaises(AuthorityDenied):
            assert_runtime_environment(
                {"OLIN_CANONICAL_EVIDENCE_DATABASE_URL": "redacted"}
            )
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

        route_removed = copy.deepcopy(original)
        route_removed["allowed_routes"] = route_removed["allowed_routes"][:-1]
        mutations.append(route_removed)

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

    def test_phase5a_uses_separate_investigator_http_entrypoint(self):
        self.assertFalse((ROOT / "olin" / "investigator" / "server.py").exists())
        self.assertTrue((ROOT / "olin" / "investigator_app.py").exists())
        self.assertNotIn(
            "olin.server", (ROOT / "olin" / "investigator_app.py").read_text()
        )

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
            "set session authorization olin_investigator_owner",
            "reset session authorization",
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
        self.assertNotIn("grant olin_investigator_owner to %i", sql)
        self.assertNotIn("revoke olin_investigator_owner from %i", sql)
        self.assertNotIn("comment on role olin_investigator_runtime", sql)
        self.assertNotIn("public.scoring_log", sql)
        self.assertNotIn("payment_ledger", sql)

    def test_phase2_migration_is_reference_only_and_least_privilege(self):
        sql = PHASE2_MIGRATION_PATH.read_text(encoding="utf-8").lower()
        required = (
            "create table investigator.investigation_evidence_reference",
            "alter table investigator.investigation_evidence_reference enable row level security",
            "alter table investigator.investigation_evidence_reference force row level security",
            "create trigger investigation_evidence_reference_immutable",
            "create trigger investigation_evidence_reference_no_truncate",
            "create function investigator.accept_evidence_reference",
            "create function investigator.create_snapshot_v2",
            "create function investigator.is_snapshot_structurally_current_v2",
            "security definer",
            "set search_path = pg_catalog, investigator",
            "caller trust labels are forbidden",
            "revoke all on table investigator.investigation_evidence_reference",
            "grant select on investigator.investigation_evidence_reference",
            "reset session authorization",
            "commit;",
        )
        for fragment in required:
            self.assertIn(fragment, sql)
        self.assertNotIn(
            "grant insert on investigator.investigation_evidence_reference to olin_investigator_runtime",
            sql,
        )
        self.assertNotIn(
            "grant update on investigator.investigation_evidence_reference to olin_investigator_runtime",
            sql,
        )
        self.assertNotIn(
            "grant delete on investigator.investigation_evidence_reference to olin_investigator_runtime",
            sql,
        )
        self.assertNotIn("alter table public.", sql)
        self.assertNotIn(
            "create table investigator.investigation_consent_reference", sql
        )

    def test_phase25_migration_is_lineage_only_and_forward_migrated(self):
        sql = PHASE25_MIGRATION_PATH.read_text(encoding="utf-8").lower()
        for fragment in (
            "create table investigator.investigation_evidence_semantics",
            "enable row level security",
            "force row level security",
            "create function investigator.accept_evidence_reference_v2",
            "create function investigator.enrich_snapshot_v2_semantics",
            "rename to create_snapshot_v2_phase2_legacy",
            "caller independence fields are forbidden",
            "canonical_reference' is distinct from",
            "revoke all on function investigator.accept_evidence_reference(",
            "grant execute on function investigator.accept_evidence_reference_v2(",
            "reset session authorization",
            "commit;",
        ):
            self.assertIn(fragment, sql)
        for forbidden in (
            "create table investigator.claim",
            "artifact_body",
            "credit_score",
            "approved_amount",
            "payment_ledger",
            "provider.call",
        ):
            self.assertNotIn(forbidden, sql)

    def test_phase3_migration_only_adds_closed_assertion_profiles(self):
        sql = PHASE3_MIGRATION_PATH.read_text(encoding="utf-8").lower()
        for fragment in (
            "investigator migration 0004 must be applied first",
            "drop constraint investigation_evidence_reference_proposition_check",
            "add constraint investigation_evidence_reference_proposition_check",
            "merchant_assertion_recorded:v1",
            "external_assertion_recorded:v1",
            "proposition_schema_version = 1",
            ") is true",
            "reset session authorization",
            "commit;",
        ):
            self.assertIn(fragment, sql)
        for forbidden in (
            "create table",
            "create role",
            "grant ",
            "credit_score",
            "approved_amount",
            "reasoning_result",
        ):
            self.assertNotIn(forbidden, sql)

    def test_phase5a_migration_is_additive_append_only_and_least_privilege(self):
        sql = PHASE5A_MIGRATION_PATH.read_text(encoding="utf-8").lower()
        for fragment in (
            "create role olin_investigator_action_writer",
            "create table investigator.investigation_action",
            "create table investigator.investigation_action_transition",
            "force row level security",
            "create function investigator.select_investigation_action",
            "create function investigator.transition_investigation_action",
            "isolated tenant-bound action writer is required",
            "selected snapshot is stale or mismatched",
            "selected authority or evidence state is stale",
            "action history is append-only",
            "grant execute on function investigator.select_investigation_action",
            "reset session authorization",
            "commit;",
        ):
            self.assertIn(fragment, sql)
        for forbidden in (
            "alter table investigator.investigation_event add",
            "create table investigator.claims_assessment",
            "economic_reconstruction jsonb",
            "grant insert on investigator.investigation_action to olin_investigator_action_writer",
            "credit_score",
            "approved_amount",
        ):
            self.assertNotIn(forbidden, sql)


if __name__ == "__main__":
    unittest.main()
