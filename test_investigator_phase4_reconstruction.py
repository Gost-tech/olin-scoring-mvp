from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import ROUND_DOWN, Inexact, getcontext
from unittest.mock import patch
from uuid import UUID

from olin.investigator.claims import (
    PHASE3_RULES_VERSION,
    ClaimsAssessment,
    assess_claims,
)
from olin.investigator.evidence_boundary import EvidenceBoundaryError
from olin.investigator.reconstruction import (
    PHASE4_RULES_VERSION,
    PHASE4_SCHEMA_VERSION,
    CoverageStatus,
    CoverageType,
    EconomicDimension,
    EconomicReconstruction,
    EconomicValueType,
    ReconstructionStatus,
    reconstruct_economics,
)
from olin.investigator.spine import CaseSnapshot
from test_investigator_phase3_claims import (
    NOW,
    SyntheticGate,
    fact,
    merchant_claim,
    ready,
)


def reconstruct(references=()) -> EconomicReconstruction:
    capability, connection = ready(tuple(references))
    return SyntheticGate(capability, connection).reconstruct_economics_current(
        tenant_id=capability.tenant_id,
        case_id=capability.case_id,
        snapshot_id=capability.snapshot_id,
        as_of=NOW,
    )


def coverage(
    reference_id: int, proposition_type: str, value: str = "COMPLETE", **changes
):
    return fact(
        reference_id=reference_id,
        proposition_type=proposition_type,
        proposition_value=value,
        proposition_unit="STATUS",
        semantic_lineage_id=f"coverage-{reference_id}",
        **changes,
    )


def values_by_quantity(values):
    return {item.quantity: item for item in values}


class Phase4EconomicReconstructionTests(unittest.TestCase):
    def test_value_types_are_distinct_and_v1_emits_no_estimate_or_scenario(self):
        self.assertEqual(
            {item.value for item in EconomicValueType},
            {
                "OBSERVED_VALUE",
                "CLAIMED_VALUE",
                "DERIVED_VALUE",
                "CONSTRAINED_RANGE",
                "ESTIMATED_RANGE",
                "UNKNOWN_VALUE",
                "SCENARIO_VALUE",
            },
        )
        emitted = reconstruct((merchant_claim(), fact()))
        self.assertFalse(
            any(
                item.value_type
                in {
                    EconomicValueType.ESTIMATED_RANGE,
                    EconomicValueType.SCENARIO_VALUE,
                }
                for item in (
                    emitted.observed_values
                    + emitted.claimed_values
                    + emitted.derived_values
                )
            )
        )

    def test_target_case_is_range_first_and_preserves_disagreement(self):
        result = reconstruct((merchant_claim(), fact()))
        observed = values_by_quantity(result.observed_values)
        claimed = values_by_quantity(result.claimed_values)
        derived = values_by_quantity(result.derived_values)
        unknowns = {item.quantity: item for item in result.unresolved_quantities}

        self.assertEqual(observed["observable_bank_inflows"].value, "118000")
        self.assertIs(
            observed["observable_bank_inflows"].value_type,
            EconomicValueType.OBSERVED_VALUE,
        )
        self.assertEqual(claimed["total_monthly_revenue"].value, "260000")
        self.assertIs(
            claimed["total_monthly_revenue"].value_type,
            EconomicValueType.CLAIMED_VALUE,
        )
        self.assertEqual(derived["revenue_reconciliation_gap"].value, "142000")
        self.assertIn(
            "does not establish", derived["revenue_reconciliation_gap"].assumptions[0]
        )
        self.assertIn("total_sustainable_revenue", unknowns)
        self.assertIn("additional_revenue_channels", unknowns)
        self.assertEqual(result.constrained_ranges, ())
        self.assertEqual(len(result.contradictions_carried_forward), 1)
        self.assertEqual(len(result.phase3_unknowns), 1)

    def test_default_coverage_is_unknown_not_complete(self):
        result = reconstruct((fact(),))
        statuses = {
            item.coverage_type: item.status for item in result.coverage_diagnostics
        }
        self.assertEqual(set(statuses), set(CoverageType))
        self.assertTrue(
            all(item is CoverageStatus.UNKNOWN for item in statuses.values())
        )

    def test_partial_account_coverage_cannot_establish_total_revenue(self):
        result = reconstruct(
            (
                fact(),
                coverage(300, "bank_account_coverage", "PARTIAL"),
            )
        )
        self.assertIn(
            "total_sustainable_revenue",
            {item.quantity for item in result.unresolved_quantities},
        )
        self.assertFalse(result.constrained_ranges)

    def test_authoritative_coverage_is_preserved_but_claim_is_not_promoted(self):
        result = reconstruct(
            (
                coverage(301, "bank_account_coverage", "PARTIAL"),
                merchant_claim(
                    reference_id=302,
                    proposition_type="debt_coverage",
                    proposition_value="COMPLETE",
                    proposition_unit="STATUS",
                ),
            )
        )
        statuses = {
            item.coverage_type: item.status for item in result.coverage_diagnostics
        }
        self.assertIs(
            statuses[CoverageType.BANK_ACCOUNT_COVERAGE], CoverageStatus.PARTIAL
        )
        self.assertIs(statuses[CoverageType.DEBT_COVERAGE], CoverageStatus.UNKNOWN)

    def test_no_debt_or_cost_evidence_does_not_create_zero(self):
        result = reconstruct(())
        unknowns = {item.quantity: item for item in result.unresolved_quantities}
        self.assertIn("total_debt_service", unknowns)
        self.assertIn("total_operating_costs", unknowns)
        emitted = result.observed_values + result.derived_values
        self.assertFalse(
            any(
                item.dimension
                in {EconomicDimension.DEBT_SERVICE, EconomicDimension.OPERATING_COSTS}
                and item.value == "0"
                for item in emitted
            )
        )

    def test_claim_only_dimension_is_insufficient_not_supported(self):
        result = reconstruct((merchant_claim(),))
        revenue = next(
            item
            for item in result.dimension_assessments
            if item.dimension is EconomicDimension.REVENUE
        )
        self.assertIs(revenue.status, ReconstructionStatus.INSUFFICIENT_INPUT)
        self.assertEqual(len(result.claimed_values), 1)

    def test_mixed_supported_and_claimed_dimension_is_only_partial(self):
        working_capital_result = reconstruct(
            (
                fact(
                    reference_id=399,
                    proposition_type="working_capital",
                    proposition_value="50000",
                ),
                merchant_claim(
                    reference_id=400,
                    proposition_type="working_capital",
                    proposition_value="50000",
                ),
            )
        )
        working_capital = next(
            item
            for item in working_capital_result.dimension_assessments
            if item.dimension is EconomicDimension.WORKING_CAPITAL
        )
        self.assertIs(
            working_capital.status,
            ReconstructionStatus.PARTIALLY_SUPPORTED,
        )

        cash_result = reconstruct(
            (
                fact(
                    reference_id=401,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                ),
                fact(
                    reference_id=402,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="125000",
                ),
                coverage(403, "period_coverage"),
                merchant_claim(
                    reference_id=404,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                ),
            )
        )
        cash_flow = next(
            item
            for item in cash_result.dimension_assessments
            if item.dimension is EconomicDimension.CASH_FLOW
        )
        self.assertIs(cash_flow.status, ReconstructionStatus.PARTIALLY_SUPPORTED)

    def test_negative_inflow_cannot_enter_revenue_gap_arithmetic(self):
        result = reconstruct(
            (
                merchant_claim(proposition_value="100"),
                fact(proposition_value="-1"),
            )
        )
        self.assertNotIn(
            "revenue_reconciliation_gap",
            values_by_quantity(result.derived_values),
        )
        self.assertNotIn(
            "observable_bank_inflows",
            values_by_quantity(result.observed_values),
        )

    def test_verified_and_claimed_costs_remain_distinct(self):
        result = reconstruct(
            (
                fact(
                    reference_id=310,
                    proposition_type="monthly_operating_costs",
                    proposition_value="70000",
                    semantic_lineage_id="verified-costs",
                ),
                merchant_claim(
                    reference_id=311,
                    proposition_type="monthly_operating_costs",
                    proposition_value="65000",
                    semantic_lineage_id="claimed-costs",
                ),
            )
        )
        self.assertEqual(
            values_by_quantity(result.observed_values)[
                "total_monthly_operating_costs"
            ].value,
            "70000",
        )
        self.assertEqual(
            values_by_quantity(result.claimed_values)[
                "total_monthly_operating_costs"
            ].value,
            "65000",
        )
        complete_coverage = reconstruct(
            (
                fact(
                    reference_id=312,
                    proposition_type="monthly_operating_costs",
                    proposition_value="70000",
                ),
                coverage(313, "cost_coverage"),
            )
        )
        self.assertIn(
            "total_operating_costs",
            {item.quantity for item in complete_coverage.unresolved_quantities},
        )

    def test_margin_remains_unknown_without_accounting_basis_metadata(self):
        base = (
            fact(
                reference_id=320,
                proposition_type="monthly_revenue",
                proposition_value="200000",
                semantic_lineage_id="verified-total-revenue",
            ),
            fact(
                reference_id=321,
                proposition_type="monthly_operating_costs",
                proposition_value="140000",
                semantic_lineage_id="verified-total-costs",
            ),
        )
        incomplete = reconstruct(base)
        self.assertNotIn(
            "operating_margin_ratio", values_by_quantity(incomplete.derived_values)
        )

        complete = reconstruct(
            base
            + (
                coverage(322, "revenue_channel_coverage"),
                coverage(323, "cost_coverage"),
                coverage(324, "period_coverage"),
            )
        )
        self.assertNotIn(
            "operating_margin_ratio", values_by_quantity(complete.derived_values)
        )
        self.assertIn(
            "operating_margin",
            {item.quantity for item in complete.unresolved_quantities},
        )

    def test_margin_suppresses_incompatible_currency_and_period(self):
        requirements = (
            coverage(330, "revenue_channel_coverage"),
            coverage(331, "cost_coverage"),
            coverage(332, "period_coverage"),
        )
        for cost in (
            fact(
                reference_id=333,
                proposition_type="monthly_operating_costs",
                proposition_value="100000",
                proposition_unit="USD",
            ),
            fact(
                reference_id=334,
                proposition_type="monthly_operating_costs",
                proposition_value="100000",
                period_start=NOW - timedelta(days=60),
                period_end=NOW - timedelta(days=30),
            ),
        ):
            result = reconstruct(
                (
                    fact(
                        reference_id=335,
                        proposition_type="monthly_revenue",
                        proposition_value="200000",
                    ),
                    cost,
                    *requirements,
                )
            )
            with self.subTest(cost=cost):
                self.assertNotIn(
                    "operating_margin_ratio", values_by_quantity(result.derived_values)
                )

    def test_cash_flow_is_derived_only_from_complete_compatible_components(self):
        components = (
            fact(
                reference_id=340,
                proposition_type="monthly_operating_cash_inflows",
                proposition_value="180000",
            ),
            fact(
                reference_id=341,
                proposition_type="monthly_operating_cash_outflows",
                proposition_value="125000",
            ),
        )
        incomplete = reconstruct(components)
        self.assertNotIn(
            "monthly_net_operating_cash_movement",
            values_by_quantity(incomplete.derived_values),
        )
        complete = reconstruct(components + (coverage(342, "period_coverage"),))
        value = values_by_quantity(complete.derived_values)[
            "monthly_net_operating_cash_movement"
        ]
        self.assertEqual(value.value, "55000")
        self.assertEqual(
            value.formula,
            "MONTHLY_OPERATING_CASH_INFLOWS - MONTHLY_OPERATING_CASH_OUTFLOWS",
        )
        self.assertEqual(value.dimensional_scope.value, "UNSPECIFIED")

    def test_multiple_complete_cash_periods_are_reconstructed_independently(self):
        old_start = NOW - timedelta(days=60)
        old_end = NOW - timedelta(days=30)
        result = reconstruct(
            (
                fact(
                    reference_id=356,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                    period_start=old_start,
                    period_end=old_end,
                ),
                fact(
                    reference_id=357,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="125000",
                    period_start=old_start,
                    period_end=old_end,
                ),
                coverage(
                    358,
                    "period_coverage",
                    period_start=old_start,
                    period_end=old_end,
                ),
                fact(
                    reference_id=359,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="150000",
                ),
                fact(
                    reference_id=390,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="110000",
                ),
                coverage(391, "period_coverage"),
            )
        )
        cash_values = tuple(
            item
            for item in result.derived_values
            if item.quantity == "monthly_net_operating_cash_movement"
        )
        self.assertEqual({item.value for item in cash_values}, {"40000", "55000"})
        self.assertNotIn(
            "net_operating_cash_movement",
            {item.quantity for item in result.unresolved_quantities},
        )

    def test_old_period_coverage_cannot_authorize_current_cash_arithmetic(self):
        old_start = NOW - timedelta(days=400)
        old_end = NOW - timedelta(days=370)
        result = reconstruct(
            (
                fact(
                    reference_id=343,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                ),
                fact(
                    reference_id=344,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="125000",
                ),
                coverage(
                    345,
                    "period_coverage",
                    period_start=old_start,
                    period_end=old_end,
                ),
            )
        )
        self.assertNotIn(
            "monthly_net_operating_cash_movement",
            values_by_quantity(result.derived_values),
        )

    def test_incompatible_cash_currency_and_period_fail_safely(self):
        variants = (
            fact(
                reference_id=395,
                proposition_type="monthly_operating_cash_outflows",
                proposition_value="125000",
                proposition_unit="USD",
            ),
            fact(
                reference_id=396,
                proposition_type="monthly_operating_cash_outflows",
                proposition_value="125000",
                period_start=NOW - timedelta(days=60),
                period_end=NOW - timedelta(days=30),
            ),
        )
        for outflow in variants:
            result = reconstruct(
                (
                    fact(
                        reference_id=397,
                        proposition_type="monthly_operating_cash_inflows",
                        proposition_value="180000",
                    ),
                    outflow,
                    coverage(398, "period_coverage"),
                )
            )
            with self.subTest(outflow=outflow.proposition_unit):
                self.assertNotIn(
                    "monthly_net_operating_cash_movement",
                    values_by_quantity(result.derived_values),
                )
                self.assertIn(
                    "net_operating_cash_movement",
                    {item.quantity for item in result.unresolved_quantities},
                )

    def test_other_subject_coverage_and_cash_component_cannot_authorize_arithmetic(
        self,
    ):
        for references in (
            (
                fact(
                    reference_id=346,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                ),
                fact(
                    reference_id=347,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="125000",
                ),
                coverage(348, "period_coverage", subject_id="other-business"),
            ),
            (
                fact(
                    reference_id=349,
                    proposition_type="monthly_operating_cash_inflows",
                    proposition_value="180000",
                ),
                fact(
                    reference_id=354,
                    proposition_type="monthly_operating_cash_outflows",
                    proposition_value="125000",
                    subject_id="other-business",
                ),
                coverage(355, "period_coverage"),
            ),
        ):
            result = reconstruct(references)
            with self.subTest(references=references):
                self.assertNotIn(
                    "monthly_net_operating_cash_movement",
                    values_by_quantity(result.derived_values),
                )

    def test_verified_and_claimed_debt_are_preserved_while_total_exposure_unknown(self):
        result = reconstruct(
            (
                fact(
                    reference_id=350,
                    proposition_type="monthly_debt_service",
                    proposition_value="12000",
                ),
                merchant_claim(
                    reference_id=351,
                    proposition_type="monthly_debt_service",
                    proposition_value="10000",
                ),
            )
        )
        self.assertEqual(
            values_by_quantity(result.observed_values)["monthly_debt_service"].value,
            "12000",
        )
        self.assertEqual(
            values_by_quantity(result.claimed_values)["monthly_debt_service"].value,
            "10000",
        )
        self.assertIn(
            "total_debt_service",
            {item.quantity for item in result.unresolved_quantities},
        )

        complete = reconstruct(
            (
                fact(
                    reference_id=352,
                    proposition_type="monthly_debt_service",
                    proposition_value="12000",
                ),
                coverage(353, "debt_coverage"),
            )
        )
        self.assertIn(
            "total_debt_service",
            {item.quantity for item in complete.unresolved_quantities},
        )

    def test_explicit_normalization_is_deterministic_and_provenance_bound(self):
        cases = (
            ("daily_operating_costs", "1000", "30000", 1),
            ("weekly_operating_costs", "12000", "51428.57142857142857142857143", 7),
            ("annual_operating_costs", "120000", "9863.013698630136986301369863", 365),
        )
        for index, (proposition_type, value, expected, source_days) in enumerate(
            cases, start=360
        ):
            result = reconstruct(
                (
                    fact(
                        reference_id=index,
                        proposition_type=proposition_type,
                        proposition_value=value,
                        period_start=NOW - timedelta(days=source_days),
                    ),
                )
            )
            normalized = values_by_quantity(result.derived_values)[
                "normalized_monthly_operating_costs"
            ]
            with self.subTest(proposition_type=proposition_type):
                self.assertEqual(normalized.value, expected)
                self.assertTrue(normalized.assumptions)
                self.assertTrue(normalized.input_proposition_digests)
                self.assertTrue(normalized.rule_version)
                self.assertEqual(
                    normalized.period_end - normalized.period_start,
                    timedelta(days=30),
                )

    def test_incompatible_source_periods_do_not_normalize(self):
        for index, (proposition_type, source_days) in enumerate(
            (("daily_operating_costs", 365), ("annual_operating_costs", 1)),
            start=392,
        ):
            result = reconstruct(
                (
                    fact(
                        reference_id=index,
                        proposition_type=proposition_type,
                        proposition_value="12000",
                        period_start=NOW - timedelta(days=source_days),
                    ),
                )
            )
            with self.subTest(proposition_type=proposition_type):
                self.assertNotIn(
                    "normalized_monthly_operating_costs",
                    values_by_quantity(result.derived_values),
                )

    def test_nonnumeric_normalization_remains_unresolved(self):
        result = reconstruct(
            (
                fact(
                    reference_id=370,
                    proposition_type="daily_operating_costs",
                    proposition_value="unknown",
                ),
            )
        )
        self.assertNotIn(
            "normalized_monthly_operating_costs",
            values_by_quantity(result.derived_values),
        )
        self.assertIn(
            "total_operating_costs",
            {item.quantity for item in result.unresolved_quantities},
        )

    def test_unsupported_proposition_schemas_remain_uninterpreted(self):
        result = reconstruct(
            (
                fact(
                    reference_id=368,
                    proposition_type="monthly_revenue",
                    proposition_schema_version=999,
                    proposition_value="200000",
                ),
                fact(
                    reference_id=369,
                    proposition_type="annual_operating_costs",
                    proposition_schema_version=999,
                    proposition_value="120000",
                ),
            )
        )
        self.assertFalse(result.observed_values)
        self.assertNotIn(
            "normalized_monthly_operating_costs",
            values_by_quantity(result.derived_values),
        )

    def test_invalid_or_conflicting_costs_preserve_total_cost_unknown(self):
        variants = (
            (
                fact(
                    reference_id=381,
                    proposition_type="monthly_operating_costs",
                    proposition_value="invalid",
                ),
            ),
            (
                fact(
                    reference_id=382,
                    proposition_type="monthly_operating_costs",
                    proposition_value="70000",
                ),
                fact(
                    reference_id=383,
                    proposition_type="monthly_operating_costs",
                    proposition_value="140000",
                ),
            ),
        )
        for facts in variants:
            result = reconstruct((*facts, coverage(384, "cost_coverage")))
            with self.subTest(facts=facts):
                self.assertIn(
                    "total_operating_costs",
                    {item.quantity for item in result.unresolved_quantities},
                )
                status = next(
                    item.status
                    for item in result.dimension_assessments
                    if item.dimension is EconomicDimension.OPERATING_COSTS
                )
                self.assertIsNot(status, ReconstructionStatus.SUPPORTED)

    def test_invalid_coverage_conflicts_fail_closed(self):
        result = reconstruct(
            (
                coverage(385, "cost_coverage"),
                coverage(386, "cost_coverage", "INVALID"),
            )
        )
        diagnostic = next(
            item
            for item in result.coverage_diagnostics
            if item.coverage_type is CoverageType.COST_COVERAGE
        )
        self.assertIs(diagnostic.status, CoverageStatus.UNKNOWN)

    def test_unknown_and_dimension_status_bind_coverage_provenance(self):
        result = reconstruct((coverage(388, "cost_coverage", "PARTIAL"),))
        unknown = next(
            item
            for item in result.unresolved_quantities
            if item.quantity == "total_operating_costs"
        )
        self.assertIn(UUID(int=388), unknown.evidence_considered)
        self.assertTrue(unknown.input_proposition_digests)
        self.assertEqual(unknown.provenance[0].reference_id, UUID(int=388))
        dimension = next(
            item
            for item in result.dimension_assessments
            if item.dimension is EconomicDimension.OPERATING_COSTS
        )
        self.assertIn(
            UUID(int=388), {item.reference_id for item in dimension.provenance}
        )
        self.assertTrue(dimension.input_proposition_digests)

    def test_extreme_finite_input_cannot_overflow_output(self):
        result = reconstruct(
            (
                fact(
                    reference_id=387,
                    proposition_type="daily_operating_costs",
                    proposition_value="1e1000000",
                ),
            )
        )
        self.assertNotIn(
            "normalized_monthly_operating_costs",
            values_by_quantity(result.derived_values),
        )
        self.assertNotIn("Infinity", result.canonical_bytes.decode())

    def test_invalid_monetary_values_and_units_do_not_become_economic_values(self):
        variants = (
            {"proposition_value": "unknown"},
            {"proposition_value": "NaN"},
            {"proposition_value": "-1"},
            {"proposition_unit": "MXN/USD"},
            {"proposition_unit": "mxn"},
            {"proposition_unit": "ZZZ"},
        )
        for index, changes in enumerate(variants, start=371):
            result = reconstruct(
                (
                    fact(
                        reference_id=index,
                        proposition_type="monthly_operating_costs",
                        **changes,
                    ),
                )
            )
            with self.subTest(changes=changes):
                self.assertFalse(result.observed_values)
                self.assertIn(
                    "total_operating_costs",
                    {item.quantity for item in result.unresolved_quantities},
                )

    def test_invalid_working_capital_preserves_explicit_unknown(self):
        result = reconstruct(
            (
                fact(
                    reference_id=389,
                    proposition_type="working_capital",
                    proposition_value="NaN",
                ),
            )
        )
        self.assertIn(
            "working_capital",
            {item.quantity for item in result.unresolved_quantities},
        )

    def test_phase3_contradiction_and_unknown_are_carried_verbatim(self):
        assessment_result = reconstruct((merchant_claim(), fact()))
        self.assertEqual(
            assessment_result.contradictions_carried_forward[0].rule_id,
            "P3-CONTRADICTION-REVENUE-001",
        )
        self.assertEqual(
            assessment_result.phase3_unknowns[0].rule_id,
            "P3-UNKNOWN-REVENUE-001",
        )
        revenue_status = next(
            item.status
            for item in assessment_result.dimension_assessments
            if item.dimension is EconomicDimension.REVENUE
        )
        self.assertIs(revenue_status, ReconstructionStatus.CONTRADICTED)

    def test_conclusion_provenance_never_duplicates_evidence_identity(self):
        result = reconstruct((merchant_claim(), fact()))
        conclusions = result.unresolved_quantities + result.dimension_assessments
        for conclusion in conclusions:
            reference_ids = tuple(item.reference_id for item in conclusion.provenance)
            with self.subTest(conclusion=conclusion):
                self.assertEqual(len(reference_ids), len(set(reference_ids)))
        for unknown in result.unresolved_quantities:
            self.assertEqual(
                len(unknown.evidence_considered),
                len(set(unknown.evidence_considered)),
            )

    def test_public_or_mutable_assessment_substitutes_are_rejected(self):
        assessment = self._phase3_assessment((fact(),))
        for value in (
            assessment,
            assessment.canonical_record(),
            object.__new__(CaseSnapshot),
            fact(),
        ):
            with self.subTest(value=type(value)), self.assertRaises(TypeError):
                reconstruct_economics(value)

    def test_mismatched_and_unsupported_assessments_are_rejected(self):
        changes = (
            {"tenant_id": UUID(int=999)},
            {"case_id": UUID(int=999)},
            {"snapshot_id": UUID(int=999)},
            {"snapshot_digest": "f" * 64},
            {"authority_revision": 999},
            {"authority_digest": "f" * 64},
            {"evidence_state_digest": "f" * 64},
            {"schema_version": "unsupported"},
            {"rules_version": "unsupported"},
        )
        original = assess_claims
        for change in changes:
            capability, connection = ready((fact(),))
            gate = SyntheticGate(capability, connection)

            def tampered(item, *, fields=change):
                return replace(original(item), **fields)

            with (
                self.subTest(change=change),
                patch("olin.investigator.claims.assess_claims", tampered),
                self.assertRaises(EvidenceBoundaryError),
            ):
                gate.reconstruct_economics_current(
                    tenant_id=capability.tenant_id,
                    case_id=capability.case_id,
                    snapshot_id=capability.snapshot_id,
                    as_of=NOW,
                )

    def test_currentness_is_checked_immediately_before_and_after_reconstruction(self):
        capability, connection = ready((fact(),))
        SyntheticGate(capability, connection).reconstruct_economics_current(
            tenant_id=capability.tenant_id,
            case_id=capability.case_id,
            snapshot_id=capability.snapshot_id,
            as_of=NOW,
        )
        self.assertEqual(connection.state_checks, 3)

    def test_result_is_immutable_bound_versioned_and_order_invariant(self):
        references = (
            merchant_claim(),
            fact(),
            coverage(380, "bank_account_coverage", "UNKNOWN"),
        )
        forward = reconstruct(references)
        reverse = reconstruct(tuple(reversed(references)))
        self.assertEqual(forward.canonical_bytes, reverse.canonical_bytes)
        self.assertEqual(forward.schema_version, PHASE4_SCHEMA_VERSION)
        self.assertEqual(forward.rules_version, PHASE4_RULES_VERSION)
        self.assertEqual(
            forward.input_assessment.phase3_rules_version, PHASE3_RULES_VERSION
        )
        self.assertEqual(forward.input_assessment.tenant_id, UUID(int=1))
        self.assertTrue(forward.input_assessment.assessment_digest)
        self.assertEqual(forward.input_assessment.checked_at, NOW)
        self.assertEqual(
            forward.input_assessment.canonical_projection_version,
            "canonical-evidence-projection-1",
        )
        with self.assertRaises(FrozenInstanceError):
            forward.rules_version = "changed"

    def test_decimal_context_cannot_change_reconstruction(self):
        original_precision = getcontext().prec
        original_rounding = getcontext().rounding
        original_trap = getcontext().traps[Inexact]
        try:
            baseline = reconstruct((merchant_claim(), fact())).canonical_bytes
            getcontext().prec = 5
            getcontext().rounding = ROUND_DOWN
            getcontext().traps[Inexact] = True
            changed = reconstruct((merchant_claim(), fact())).canonical_bytes
        finally:
            getcontext().prec = original_precision
            getcontext().rounding = original_rounding
            getcontext().traps[Inexact] = original_trap
        self.assertEqual(changed, baseline)

    def test_output_has_no_credit_money_provider_ai_or_midpoint_surface(self):
        canonical = (
            reconstruct((merchant_claim(), fact())).canonical_bytes.decode().lower()
        )
        forbidden = (
            "credit_score",
            '"pd"',
            "approve",
            "decline",
            "loan_amount",
            "facility_structure",
            "pricing",
            "money_movement",
            "provider",
            "ai.invoke",
            "midpoint",
            "fraud",
        )
        self.assertTrue(all(item not in canonical for item in forbidden))

    def test_kernel_makes_no_network_provider_or_ai_calls(self):
        with (
            patch(
                "socket.create_connection",
                side_effect=AssertionError("network call forbidden"),
            ),
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("provider call forbidden"),
            ),
        ):
            result = reconstruct((merchant_claim(), fact()))
        self.assertEqual(
            values_by_quantity(result.derived_values)[
                "revenue_reconciliation_gap"
            ].value,
            "142000",
        )

    @staticmethod
    def _phase3_assessment(references) -> ClaimsAssessment:
        capability, connection = ready(tuple(references))
        return SyntheticGate(capability, connection).assess_claims_current(
            tenant_id=capability.tenant_id,
            case_id=capability.case_id,
            snapshot_id=capability.snapshot_id,
            as_of=NOW,
        )


if __name__ == "__main__":
    unittest.main()
