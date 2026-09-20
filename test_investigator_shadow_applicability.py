"""Offline saved-output regressions, not inference or renewed authorization."""

import copy
import json
import unittest
from pathlib import Path

from olin.investigator_shadow import (
    ACTIONS,
    OUTPUT_SCHEMA,
    action_eligibility,
    assess_applicability,
    canonical,
    digest,
    generation_schema,
    validate_output,
)
from olin.investigator_shadow_openai import request_body


def saved_cases():
    return json.loads(
        Path("tests/fixtures/shadow_applicability_saved_batch_v1.json").read_text()
    )["cases"]


class ApplicabilityTests(unittest.TestCase):
    def test_all_six_original_outputs_remain_structurally_valid_separate_fit(self):
        for case in saved_cases():
            with self.subTest(case=case["case"]):
                original = canonical(case)
                self.assertEqual(digest(case["context"]), case["input_digest"])
                self.assertEqual(
                    validate_output(case["proposal"], case["context"]), case["proposal"]
                )
                rows = assess_applicability(case["proposal"], case["context"])[
                    "proposals"
                ]
                self.assertEqual(
                    [r["status"] for r in rows],
                    ["NOT_APPLICABLE", "APPLICABLE"]
                    if case["case"] == "account-complete"
                    else ["APPLICABLE", "APPLICABLE"],
                )
                self.assertTrue(
                    all(
                        r["narrative_semantics"] == "REQUIRES_SEMANTIC_REVIEW"
                        for r in rows
                    )
                )
                self.assertTrue(all(r["execution_authorized"] is False for r in rows))
                if case["case"] == "account-complete":
                    self.assertEqual(
                        rows[0]["reason_codes"],
                        [
                            "UNSUPPORTED_ACTION_TARGET",
                            "ACCOUNT_COVERAGE_ALREADY_COMPLETE_SAME_SCOPE",
                        ],
                    )
                self.assertEqual(canonical(case), original)

    def test_generation_and_returned_pair_checks_use_same_derivation(self):
        for case in saved_cases():
            context = case["context"]
            e = action_eligibility(context)
            allowed = {p["action_type"] for p in e["pairs"]}
            schema = generation_schema(context)
            enums = schema["properties"]["proposals"]["items"]["properties"][
                "action_type"
            ]["enum"]
            self.assertEqual(set(enums), allowed | {None})
            self.assertEqual(
                json.loads(request_body(context))["text"]["format"]["schema"][
                    "properties"
                ]["proposals"]["items"]["properties"]["action_type"]["enum"],
                enums,
            )
            for action in ACTIONS:
                for target in context["uncertainties"]:
                    output = copy.deepcopy(case["proposal"])
                    output["proposals"] = output["proposals"][:1]
                    output["proposals"][0].update(
                        action_type=action, uncertainty=target
                    )
                    result = assess_applicability(output, context)["proposals"][0]
                    self.assertEqual(
                        result["status"] == "APPLICABLE",
                        any(
                            (p["action_type"], p["target"]) == (action, target)
                            for p in e["pairs"]
                        ),
                    )
        self.assertEqual(
            OUTPUT_SCHEMA["properties"]["proposals"]["items"]["properties"][
                "action_type"
            ]["enum"],
            [*ACTIONS, None],
        )

    def test_complete_account_is_not_channel_completeness_or_cost_debt_capability(self):
        case = saved_cases()[1]
        e = action_eligibility(case["context"])
        self.assertTrue(e["bank_account_complete_same_scope"])
        self.assertNotIn(ACTIONS[0], e["capabilities"])
        self.assertEqual(
            {p["effect"] for p in e["pairs"]}, {"ATTRIBUTED_CLAIM_CLARIFICATION_ONLY"}
        )
        for target in (
            "COST_COVERAGE",
            "DEBT_COVERAGE",
            "total_operating_costs",
            "total_debt_service",
            "total_sustainable_revenue",
        ):
            self.assertIn(target, e["uncovered_targets"])
        self.assertIn("REVENUE_CHANNEL_COVERAGE", case["context"]["uncertainties"])

    def test_redundant_same_scope_no_recheck_reason_and_different_scope(self):
        case = saved_cases()[1]
        context = copy.deepcopy(case["context"])
        context["uncertainties"].append("BANK_ACCOUNT_COVERAGE")
        output = copy.deepcopy(case["proposal"])
        output["proposals"] = output["proposals"][:1]
        output["proposals"][0]["uncertainty"] = "BANK_ACCOUNT_COVERAGE"
        self.assertEqual(
            assess_applicability(output, context)["proposals"][0]["status"], "REDUNDANT"
        )
        for fact in context["facts"]:
            if fact.get("coverage_type") == "BANK_ACCOUNT_COVERAGE":
                fact["period_start"] = "2025-01-01T00:00:00Z"
                fact["period_end"] = "2025-01-31T00:00:00Z"
        self.assertEqual(
            assess_applicability(output, context)["proposals"][0]["status"],
            "APPLICABLE",
        )

    def test_scope_missing_ambiguous_or_merchant_claim_absent_fails_closed(self):
        for mode in ("missing", "ambiguous", "invalid-period"):
            context = copy.deepcopy(saved_cases()[0]["context"])
            context["facts"] = [
                f for f in context["facts"] if f["kind"] != "claimed_values"
            ]
            observed = next(
                f for f in context["facts"] if f["kind"] == "observed_values"
            )
            if mode == "missing":
                observed.pop("period_end")
            elif mode == "invalid-period":
                observed["period_end"] = observed["period_start"]
            else:
                other = dict(
                    observed,
                    period_start="2025-01-01T00:00:00Z",
                    period_end="2025-01-31T00:00:00Z",
                )
                context["facts"].append(other)
            self.assertEqual(action_eligibility(context)["pairs"], [])

    def test_no_pair_allows_abstention_without_permission_or_zero_inference(self):
        context = copy.deepcopy(saved_cases()[0]["context"])
        context["uncertainties"] = ["COST_COVERAGE", "DEBT_COVERAGE"]
        self.assertEqual(action_eligibility(context)["pairs"], [])
        output = {
            "schema_version": "shadow-proposal-1",
            "proposals": [],
            "abstention_reason": "No supported action addresses these uncertainties.",
        }
        result = assess_applicability(output, context)
        self.assertEqual(result["overall"], "NO_APPLICABLE_PROPOSALS")
        self.assertEqual(
            result["uncovered_targets"], ["COST_COVERAGE", "DEBT_COVERAGE"]
        )

    def test_forged_eligibility_cannot_override_facts_and_bad_references_fail(self):
        case = saved_cases()[1]
        context = copy.deepcopy(case["context"])
        context["action_eligibility"] = {
            "pairs": [{"action_type": ACTIONS[0], "target": "REVENUE_CHANNEL_COVERAGE"}]
        }
        self.assertEqual(
            assess_applicability(case["proposal"], context)["proposals"][0]["status"],
            "NOT_APPLICABLE",
        )
        for refs in (["ref-fabricated"], ["ref-1", "ref-1"]):
            output = copy.deepcopy(case["proposal"])
            output["proposals"][0]["references"] = refs
            with self.assertRaises(ValueError):
                assess_applicability(output, context)

    def test_cost_debt_case_has_no_hidden_focus_visible_to_model(self):
        a, b = saved_cases()[0]["context"], saved_cases()[2]["context"]

        def economic_projection(context):
            return [
                {
                    k: v
                    for k, v in f.items()
                    if k not in {"references", "period_start", "period_end"}
                }
                for f in context["facts"]
            ]

        self.assertEqual(economic_projection(a), economic_projection(b))
        self.assertEqual(a["uncertainties"], b["uncertainties"])
        self.assertEqual(a["actions"], b["actions"])
        self.assertNotIn("focus", a)
        self.assertNotIn("focus", b)


if __name__ == "__main__":
    unittest.main()
