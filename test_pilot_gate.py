from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from olin.pilot_gate import SHADOW_APPROVALS, evaluate_pilot_manifest


def complete_manifest(stage: str = "controlled_shadow") -> dict:
    approvals = {
        name: {
            "approved": True,
            "approver": f"Bank owner for {name}",
            "approved_at": "2026-08-20",
            "evidence_ref": f"BANK-{name.upper()}-001",
        }
        for name in SHADOW_APPROVALS
    }
    return {
        "pilot_id": "BANK-OLIN-SHADOW-01",
        "institution": "Example Bank",
        "stage": stage,
        "owners": {
            "credit_risk": "Credit Owner",
            "model_risk": "Model Risk Owner",
            "security": "Security Owner",
            "privacy": "Privacy Owner",
            "engineering": "Engineering Owner",
            "operations": "Operations Owner",
            "procurement": "Procurement Owner",
        },
        "cohort": {
            "case_ceiling": 10,
            "evidence_routes": ["inventory_led", "tpv_led", "bank_flow_led"],
            "selection_rule": "Authorized SMEs selected before Olin scoring",
        },
        "safeguards": {
            "shadow_only": True,
            "money_movement_disabled": True,
            "bank_makes_decision": True,
            "kill_switch_owner": "Operations Owner",
            "stop_conditions": [
                "cross_tenant_exposure", "consent_bypass", "unverifiable_evidence",
                "corrupted_audit_history", "high_severity_security_event",
                "unauthorized_money_movement",
            ],
        },
        "success_criteria": {
            "consent_coverage_pct": 100,
            "provenance_coverage_pct": 100,
            "reconstructable_recommendations_pct": 100,
            "bank_outcome_coverage_pct": 100,
            "unauthorized_money_movement_events": 0,
            "turnaround_baseline_method": "Median analyst minutes on matched cases",
            "turnaround_target_minutes": 45,
        },
        "outcome_contract": {
            "bank_committed_to_deliver": True,
            "outcome_label": "30+ DPD under bank policy version CR-12",
            "observation_window_days": 180,
            "delivery_owner": "Model Risk Owner",
            "delivery_method": "Bank approved encrypted transfer",
            "evidence_ref": "SIGNED-OUTCOME-ADDENDUM-001",
        },
        "approvals": approvals,
    }


class PilotGateTests(unittest.TestCase):
    def test_distributed_example_fails_closed(self):
        path = Path("docs/bank-integration-pack/pilot_manifest.example.json")
        result = evaluate_pilot_manifest(json.loads(path.read_text(encoding="utf-8")))
        self.assertFalse(result["ok"])
        self.assertEqual("NO_GO", result["verdict"])
        self.assertTrue(any("outcome_data_access" in item for item in result["blockers"]))

    def test_complete_synthetic_uat_manifest_is_go_without_external_approvals(self):
        manifest = complete_manifest("synthetic_uat")
        manifest.pop("approvals")
        result = evaluate_pilot_manifest(manifest)
        self.assertTrue(result["ok"])
        self.assertEqual("GO_SYNTHETIC_UAT", result["verdict"])

    def test_shadow_requires_security_privacy_outcomes_and_conversion(self):
        manifest = complete_manifest()
        for name in ("security_review", "privacy_review", "outcome_data_access", "paid_conversion_path"):
            manifest["approvals"][name]["approved"] = False
        result = evaluate_pilot_manifest(manifest)
        self.assertFalse(result["ok"])
        for name in ("security_review", "privacy_review", "outcome_data_access", "paid_conversion_path"):
            self.assertTrue(any(name in item for item in result["blockers"]))

    def test_complete_shadow_is_ready_but_does_not_claim_evidence_verification(self):
        result = evaluate_pilot_manifest(complete_manifest())
        self.assertTrue(result["ok"])
        self.assertEqual("READY_FOR_CONTROLLED_SHADOW", result["verdict"])
        self.assertFalse(result["evidence_independently_verified"])
        self.assertTrue(any("not default prediction" in item for item in result["warnings"]))

    def test_shadow_fails_if_money_or_case_scope_expands(self):
        manifest = complete_manifest()
        manifest["cohort"]["case_ceiling"] = 11
        manifest["safeguards"]["money_movement_disabled"] = False
        result = evaluate_pilot_manifest(manifest)
        self.assertFalse(result["ok"])
        self.assertTrue(any("between 1 and 10" in item for item in result["blockers"]))
        self.assertTrue(any("money_movement_disabled" in item for item in result["blockers"]))

    def test_production_always_uses_a_separate_gate(self):
        manifest = copy.deepcopy(complete_manifest("real_data_production"))
        result = evaluate_pilot_manifest(manifest)
        self.assertFalse(result["ok"])
        self.assertTrue(any("outside the controlled-shadow gate" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
