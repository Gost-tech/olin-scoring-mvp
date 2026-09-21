"""Synthetic release semantics; no provider calls or new evidence authority."""

import json
import unittest
from datetime import timedelta

from olin.investigator.reconstruction import PHASE4_RULES_VERSION
from olin.investigator.workflow import ACTION_CATALOGUE, ActionType
from olin.investigator_reports import ReportInput, canonical, render
from olin.investigator_shadow import project
from test_investigator_phase4_reconstruction import (
    NOW,
    fact,
    merchant_claim,
    reconstruct,
)


class V1SemanticTests(unittest.TestCase):
    def test_equivalent_rates_have_identical_exact_thirty_day_targets(self):
        start = NOW - timedelta(days=365)
        cases = (
            ("daily", "100", 1, "DAILY_VALUE * 30", "001"),
            ("weekly", "700", 7, "WEEKLY_VALUE * 30 / 7", "002"),
            ("annual", "36500", 365, "ANNUAL_VALUE * 30 / 365", "002"),
        )
        for index, (frequency, amount, days, formula, revision) in enumerate(cases):
            with self.subTest(frequency=frequency):
                source = fact(
                    reference_id=810 + index,
                    proposition_type=frequency + "_operating_costs",
                    proposition_value=amount,
                    period_start=start,
                    period_end=start + timedelta(days=days),
                )
                result = reconstruct((source,))
                value = result.derived_values[0]
                self.assertEqual(value.value, "3000")
                self.assertEqual(value.period_start, start)
                self.assertEqual(value.period_end, start + timedelta(days=30))
                self.assertEqual(value.formula, formula)
                self.assertTrue(value.rule_id.endswith(revision))
                self.assertEqual(
                    value.rule_version, "investigator-economic-reconstruction-rules-1.1"
                )
                self.assertEqual(value.rule_version, PHASE4_RULES_VERSION)
                self.assertIn("Strict 30-day equivalent", value.assumptions[0])
                self.assertIn("not", value.assumptions[0])
                self.assertIn("observed calendar-month total", value.assumptions[0])
                self.assertTrue(value.input_proposition_digests)
                self.assertEqual(value.provenance[0].reference_id, source.reference_id)
                self.assertEqual(
                    result.canonical_bytes, reconstruct((source,)).canonical_bytes
                )

    def test_fixed_duration_not_leap_calendar_year(self):
        # Fixed-duration normalization has no leap-year exception or calendar inference.
        source = fact(
            proposition_type="annual_operating_costs",
            proposition_value="36600",
            period_start=NOW - timedelta(days=366),
        )
        self.assertFalse(reconstruct((source,)).derived_values)

    def test_direct_monthly_is_observed_not_normalized_or_combined(self):
        direct = fact(
            reference_id=821,
            proposition_type="monthly_operating_costs",
            proposition_value="3000",
        )
        daily = fact(
            reference_id=822,
            proposition_type="daily_operating_costs",
            proposition_value="100",
            period_start=NOW - timedelta(days=1),
        )
        result = reconstruct((direct, daily))
        self.assertEqual(
            result.canonical_bytes, reconstruct((daily, direct)).canonical_bytes
        )
        observed = result.observed_values[0]
        self.assertEqual(observed.quantity, "total_monthly_operating_costs")
        self.assertEqual(observed.value_type.value, "OBSERVED_VALUE")
        self.assertIsNone(observed.formula)
        self.assertEqual(observed.assumptions, ())
        self.assertEqual(result.derived_values[0].value_type.value, "DERIVED_VALUE")
        self.assertIn(
            "total_operating_costs", {v.quantity for v in result.unresolved_quantities}
        )

    def test_reports_and_shadow_retain_normalization_meaning(self):
        result = reconstruct(
            (
                fact(
                    reference_id=830,
                    proposition_type="weekly_operating_costs",
                    proposition_value="700",
                    period_start=NOW - timedelta(days=7),
                ),
            )
        )
        r = json.loads(result.canonical_bytes)
        frozen = ReportInput(
            canonical(
                {
                    "manifest": {
                        **r["input_assessment"],
                        "reconstruction_rules_version": r["rules_version"],
                        "event_cutoff": 1,
                        "action_history_digest": "0" * 64,
                        "report_template_version": "investigator-report-template-2",
                    },
                    "reconstruction": r,
                    "evidence": [],
                    "action_history": [],
                    "historical_snapshot_invalidations": [],
                    "bank_question": "NOT PROVIDED",
                    "bank_disposition": "NOT PROVIDED",
                    "bank_reasons": "NOT PROVIDED",
                    "human_signoffs": "NOT PROVIDED",
                    "candidate_structure_questions": "NOT ASSESSED",
                }
            )
        )
        pair = render(frozen)
        self.assertEqual(canonical(pair), canonical(render(frozen)))
        self.assertEqual(pair["brief"]["manifest"], pair["annex"]["manifest"])
        self.assertEqual(pair["brief"]["arithmetic_derivations"], r["derived_values"])
        for html in pair["printable_html"].values():
            self.assertIn("Strict 30-day equivalent", html)
            self.assertIn("not an observed calendar-month total", html)
        self.assertIn("WEEKLY_VALUE * 30 / 7", pair["printable_html"]["annex"])
        context, _ = project(r)
        derived = next(x for x in context["facts"] if x["kind"] == "derived_values")
        for key in (
            "formula",
            "assumptions",
            "rule_version",
            "period_start",
            "period_end",
        ):
            self.assertEqual(derived[key], r["derived_values"][0][key])

    def test_catalogue_is_amount_neutral_and_claim_remains_claim(self):
        definition = ACTION_CATALOGUE[
            ActionType.CLARIFY_MERCHANT_ASSERTION_SCOPE
        ].canonical_record()
        self.assertEqual(
            definition["unresolved_question"],
            "What exact period, business scope, and channels does the merchant's revenue assertion describe?",
        )
        for amount in ("260000", "410000"):
            with self.subTest(amount=amount):
                result = reconstruct((fact(), merchant_claim(proposition_value=amount)))
                context, _ = project(result.canonical_record())
                pairs = context["action_eligibility"]["pairs"]
                self.assertTrue(
                    any(
                        x["action_type"] == "CLARIFY_MERCHANT_ASSERTION_SCOPE"
                        for x in pairs
                    )
                )
                self.assertTrue(
                    all(
                        x["effect"] == "ATTRIBUTED_CLAIM_CLARIFICATION_ONLY"
                        for x in pairs
                        if x["action_type"] == "CLARIFY_MERCHANT_ASSERTION_SCOPE"
                    )
                )
                self.assertEqual(result.claimed_values[0].value, amount)
                self.assertFalse(
                    any(
                        x.quantity == "total_monthly_revenue"
                        for x in result.observed_values
                    )
                )
                self.assertEqual(
                    ACTION_CATALOGUE[
                        ActionType.CLARIFY_MERCHANT_ASSERTION_SCOPE
                    ].canonical_record(),
                    definition,
                )
        context, _ = project(reconstruct((fact(),)).canonical_record())
        self.assertFalse(
            any(
                x["action_type"] == "CLARIFY_MERCHANT_ASSERTION_SCOPE"
                for x in context["action_eligibility"]["pairs"]
            )
        )
