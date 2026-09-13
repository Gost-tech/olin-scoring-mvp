from __future__ import annotations

import copy
import json
import unittest
from contextlib import contextmanager
from contextvars import copy_context
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_DOWN, Inexact, getcontext
from unittest.mock import patch
from uuid import UUID

from olin.investigator.claims import (
    EXTERNAL_ASSERTION_PROFILE,
    MERCHANT_ASSERTION_PROFILE,
    PHASE3_RULES_VERSION,
    ClaimsAssessment,
    Confidence,
    EpistemicType,
    assess_claims,
)
from olin.investigator.evidence import (
    EvidenceBoundaryError,
    EvidenceClass,
    EvidenceReference,
    IndependenceStatus,
    LineageRelation,
    VerificationStatus,
)
from olin.investigator.evidence_boundary import (
    _REASONING_GATE_ISSUER,
    PostgresReasoningSnapshotGate,
    ReasoningReadySnapshot,
)
from olin.investigator.spine import CaseSnapshot
from test_investigator_evidence import NOW, resolution


class Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class TransactionConnection:
    def __init__(self):
        self.info = self
        self.transaction_status = type("Status", (), {"name": "IDLE"})()
        self.state_checks = 0
        self.callback_state_checks: list[int] = []
        self.server_time = NOW

    def execute(self, query, parameters=()):
        del parameters
        if "session_tenant_id()" in query or (
            "tenant_access_allowed" in query
            and "canonical.authority_revision" not in query
        ):
            return Cursor((True,))
        if "set_config" in query:
            return Cursor((str(UUID(int=1)),))
        if "canonical.authority_revision" in query:
            self.state_checks += 1
            return Cursor((7001, "42", True, True, self.server_time, 7, "a" * 64))
        return Cursor((7001, "42"))

    @contextmanager
    def transaction(self):
        self.transaction_status = type("Status", (), {"name": "INTRANS"})()
        try:
            yield
        finally:
            self.transaction_status = type("Status", (), {"name": "IDLE"})()


class SyntheticCustody:
    @staticmethod
    def require_connection(_):
        return None


class SyntheticGate(PostgresReasoningSnapshotGate):
    def __init__(self, capability, connection):
        self._capability = capability
        self._connection = connection
        self._runtime_custody = SyntheticCustody()

    def require_snapshot_current_for_reasoning(self, **_):
        return self._capability


@dataclass(frozen=True)
class DeferredDataclass:
    value: str

    @property
    def deferred(self):
        return iter((self.value,))


class StatefulString(str):
    pass


def evidence_reference(reference_id: int, **changes) -> EvidenceReference:
    supersedes_reference_id = changes.pop("_supersedes_reference_id", None)
    resolved = resolution(UUID(int=1), UUID(int=10), **changes)
    return EvidenceReference.from_resolution(
        reference_id=UUID(int=reference_id),
        resolution=resolved,
        supersedes_reference_id=supersedes_reference_id,
        accepted_at=NOW,
    )


def fact(reference_id=101, **changes):
    values = {
        "evidence_id": f"fact-{reference_id}",
        "artifact_digest": f"{reference_id:064x}",
        "proposition_type": "bank_visible_inflows",
        "proposition_value": "118000",
        "proposition_unit": "MXN",
        "period_start": NOW - timedelta(days=30),
        "period_end": NOW,
        "semantic_lineage_id": f"fact-lineage-{reference_id}",
    }
    values.update(changes)
    return evidence_reference(reference_id, **values)


def merchant_claim(reference_id=201, **changes):
    values = {
        "evidence_id": f"claim-{reference_id}",
        "artifact_digest": f"{reference_id:064x}",
        "evidence_class": EvidenceClass.MERCHANT_SUPPLIED_ARTIFACT,
        "verification_status": VerificationStatus.UNVERIFIED,
        "proposition_type": "monthly_revenue",
        "proposition_schema_version": 1,
        "proposition_value": "260000",
        "proposition_unit": "MXN",
        "verification_method": MERCHANT_ASSERTION_PROFILE,
        "period_start": NOW - timedelta(days=30),
        "period_end": NOW,
        "issuer_id": "merchant-claimant-1",
        "upstream_issuer_id": "merchant-claimant-1",
        "semantic_lineage_id": f"claim-lineage-{reference_id}",
    }
    values.update(changes)
    return evidence_reference(reference_id, **values)


def external_claim(reference_id=301, **changes):
    values = {
        "evidence_id": f"external-{reference_id}",
        "artifact_digest": f"{reference_id:064x}",
        "evidence_class": EvidenceClass.EXTERNAL_EVIDENCE,
        "verification_status": VerificationStatus.UNVERIFIED,
        "proposition_type": "monthly_revenue",
        "proposition_schema_version": 1,
        "proposition_value": "240000",
        "proposition_unit": "MXN",
        "verification_method": EXTERNAL_ASSERTION_PROFILE,
        "period_start": NOW - timedelta(days=30),
        "period_end": NOW,
        "issuer_id": "external-claimant-1",
        "upstream_issuer_id": "external-claimant-1",
        "semantic_lineage_id": f"external-lineage-{reference_id}",
    }
    values.update(changes)
    return evidence_reference(reference_id, **values)


def ready(references=()):
    connection = TransactionConnection()
    capability = ReasoningReadySnapshot._issue_values(
        tenant_id=UUID(int=1),
        case_id=UUID(int=10),
        snapshot_id=UUID(int=20),
        snapshot_digest="b" * 64,
        authority_state_digest="a" * 64,
        evidence_state_digest="c" * 64,
        authority_revision=7,
        canonical_projection_version="canonical-evidence-projection-1",
        checked_at=NOW,
        evidence_references=tuple(references),
        connection=connection,
        transaction_id="42",
        backend_pid=7001,
        deadline=NOW + timedelta(seconds=5),
        issuer=_REASONING_GATE_ISSUER,
    )
    return capability, connection


def assess(references=()) -> ClaimsAssessment:
    capability, connection = ready(references)
    return SyntheticGate(capability, connection).assess_claims_current(
        tenant_id=capability.tenant_id,
        case_id=capability.case_id,
        snapshot_id=capability.snapshot_id,
        as_of=NOW,
    )


class Phase3ClaimsTests(unittest.TestCase):
    def test_first_target_case_preserves_epistemic_classes(self):
        result = assess((merchant_claim(), fact()))

        self.assertEqual(len(result.verified_facts), 1)
        self.assertEqual(
            result.verified_facts[0].epistemic_type, EpistemicType.VERIFIED_FACT
        )
        self.assertEqual(result.verified_facts[0].proposition.value, "118000")
        self.assertEqual(len(result.claims), 1)
        self.assertEqual(result.claims[0].epistemic_type, EpistemicType.MERCHANT_CLAIM)
        self.assertEqual(result.claims[0].proposition.value, "260000")
        self.assertIsNone(result.claims[0].assertion_timestamp)
        self.assertEqual(len(result.unknowns), 1)
        self.assertEqual(result.unknowns[0].epistemic_type, EpistemicType.UNKNOWN)
        self.assertEqual(len(result.contradictions), 1)
        self.assertIn(
            "MATERIAL_DISAGREEMENT", result.contradictions[0].contradiction_type
        )
        self.assertEqual(
            result.contradictions[0].materiality.value,
            "RECONCILIATION_GAP_AT_LEAST_20_PERCENT",
        )
        self.assertEqual(result.contradictions[0].materiality_threshold_ratio, "0.20")
        self.assertEqual(
            result.contradictions[0].materiality_denominator,
            "CLAIMED_REVENUE_VALUE",
        )
        self.assertEqual(
            {item.explanation_family for item in result.possible_explanations},
            {
                "CASH_REVENUE",
                "SECONDARY_FINANCIAL_ACCOUNT",
                "PAYMENT_PROCESSOR_OR_DELIVERY_PLATFORM",
                "PERIOD_OR_ACCOUNTING_CLASSIFICATION_MISMATCH",
                "MERCHANT_OVERSTATEMENT",
            },
        )
        self.assertTrue(
            all(
                item.status == "HYPOTHESIS"
                and item.epistemic_type is EpistemicType.POSSIBLE_EXPLANATION
                for item in result.possible_explanations
            )
        )

    def test_external_and_merchant_assertions_remain_claims_and_unknowns(self):
        result = assess((external_claim(), merchant_claim()))
        self.assertEqual(
            {claim.epistemic_type for claim in result.claims},
            {EpistemicType.EXTERNAL_CLAIM, EpistemicType.MERCHANT_CLAIM},
        )
        self.assertEqual(len(result.verified_facts), 0)
        self.assertEqual(len(result.unknowns), 2)
        self.assertTrue(
            all(item.materiality.value == "NOT_CLASSIFIED" for item in result.unknowns)
        )

    def test_uploaded_or_unversioned_artifact_is_not_an_assertion(self):
        for method in ("document_text_extracted:v1", "merchant_assertion_recorded"):
            artifact = merchant_claim(verification_method=method)
            with self.subTest(method=method):
                result = assess((artifact,))
                self.assertEqual(result.claims, ())
                self.assertEqual(result.unknowns, ())

    def test_assertion_profile_requires_complete_supported_metadata(self):
        variants = (
            merchant_claim(proposition_schema_version=2),
            merchant_claim(proposition_type=" "),
            merchant_claim(proposition_value=" "),
            merchant_claim(proposition_unit=" "),
            merchant_claim(period_start=None),
            merchant_claim(period_end=None),
        )
        for artifact in variants:
            with self.subTest(artifact=artifact):
                result = assess((artifact,))
                self.assertEqual(result.claims, ())
                self.assertEqual(result.unknowns, ())

    def test_only_exact_phase2_verified_proposition_becomes_fact(self):
        result = assess((fact(),))
        self.assertEqual(
            result.verified_facts[0].proposition.proposition_type,
            "bank_visible_inflows",
        )
        self.assertNotEqual(
            result.verified_facts[0].proposition.proposition_type, "monthly_revenue"
        )

    def test_period_unit_and_schema_incompatibility_do_not_contradict(self):
        variants = (
            fact(period_start=NOW - timedelta(days=60)),
            fact(proposition_unit="USD"),
            fact(proposition_schema_version=2),
            fact(proposition_type="net_bank_visible_inflows"),
        )
        for item in variants:
            with self.subTest(item=item):
                result = assess((merchant_claim(), item))
                self.assertEqual(result.contradictions, ())
                self.assertEqual(result.possible_explanations, ())
                self.assertEqual(len(result.unknowns), 1)

    def test_same_supported_proposition_detects_material_disagreement(self):
        declared = merchant_claim()
        verified = fact(
            proposition_type="monthly_revenue",
            proposition_value="118000",
            semantic_lineage_id="verified-revenue-lineage",
        )
        result = assess((declared, verified))
        self.assertEqual(len(result.contradictions), 1)
        self.assertEqual(
            result.contradictions[0].contradiction_type,
            "MATERIAL_DISAGREEMENT_SAME_PROPOSITION",
        )
        self.assertNotIn("FRAUD", result.canonical_bytes.decode("utf-8"))

    def test_unknown_schema_and_unspecified_scope_do_not_assert_compatibility(self):
        future_schema = fact(
            proposition_type="monthly_revenue",
            proposition_schema_version=2,
            semantic_lineage_id="future-schema-lineage",
        )
        unspecified = fact(
            proposition_type="gross_sales",
            semantic_lineage_id="unspecified-scope-lineage",
        )
        for verified in (future_schema, unspecified):
            result = assess((merchant_claim(), verified))
            self.assertEqual(result.contradictions, ())

    def test_bank_visible_facts_without_account_set_scope_do_not_conflict(self):
        first = fact(
            reference_id=110,
            proposition_value="118000",
            semantic_lineage_id="bank-account-set-unknown-1",
        )
        second = fact(
            reference_id=111,
            proposition_value="260000",
            semantic_lineage_id="bank-account-set-unknown-2",
        )
        result = assess((first, second))
        self.assertEqual(result.contradictions, ())
        self.assertEqual(result.unknowns, ())

    def test_revenue_reconciliation_suppresses_circular_and_non_original_lineage(self):
        cases = (
            (
                merchant_claim(semantic_lineage_id="shared-lineage"),
                fact(semantic_lineage_id="shared-lineage"),
            ),
            (
                merchant_claim(
                    lineage_relation=LineageRelation.DERIVED_COPY,
                    derived_from_evidence_namespace="evidence_passport",
                    derived_from_evidence_id="merchant-parent",
                    derived_from_evidence_version="1",
                ),
                fact(),
            ),
            (
                merchant_claim(
                    lineage_relation=LineageRelation.CORRECTION,
                    derived_from_evidence_namespace="evidence_passport",
                    derived_from_evidence_id="merchant-prior",
                    derived_from_evidence_version="1",
                    _supersedes_reference_id=UUID(int=199),
                ),
                fact(),
            ),
            (
                merchant_claim(economic_event_id="shared-event"),
                fact(economic_event_id="shared-event"),
            ),
            (
                merchant_claim(upstream_issuer_id="shared-upstream"),
                fact(upstream_issuer_id="shared-upstream"),
            ),
        )
        for claim, verified in cases:
            with self.subTest(claim=claim, verified=verified):
                result = assess((claim, verified))
                self.assertEqual(result.contradictions, ())
                self.assertEqual(result.possible_explanations, ())
                self.assertEqual(len(result.unknowns), 1)

    def test_unknown_independence_remains_unknown_without_blocking_distinct_lineage(
        self,
    ):
        claim = merchant_claim()
        verified = fact()
        result = assess((claim, verified))
        self.assertEqual(len(result.contradictions), 1)
        self.assertTrue(
            all(
                provenance.independence_status
                is IndependenceStatus.INDEPENDENCE_UNKNOWN
                for provenance in result.contradictions[0].provenance
                if provenance.reference_id
                in {claim.reference_id, verified.reference_id}
            )
        )

    def test_difference_below_explicit_reconciliation_threshold_is_not_material(self):
        result = assess((merchant_claim(proposition_value="120000"), fact()))
        self.assertEqual(result.contradictions, ())
        self.assertEqual(len(result.unknowns), 1)

    def test_high_precision_threshold_boundary_is_exact(self):
        at_threshold = assess(
            (
                merchant_claim(
                    proposition_value="1.000000000000000000000000000000000000"
                ),
                fact(proposition_value="0.800000000000000000000000000000000000"),
            )
        )
        below_threshold = assess(
            (
                merchant_claim(
                    reference_id=202,
                    proposition_value="1.000000000000000000000000000000000000",
                ),
                fact(
                    reference_id=102,
                    proposition_value="0.800000000000000000000000000000000001",
                ),
            )
        )
        self.assertEqual(len(at_threshold.contradictions), 1)
        self.assertEqual(below_threshold.contradictions, ())

    def test_copy_same_lineage_collapses_without_independence_inflation(self):
        original = fact()
        copy = fact(
            reference_id=102,
            evidence_id="fact-copy",
            artifact_digest="d" * 64,
            semantic_lineage_id=original.semantic_lineage_id,
            lineage_relation=LineageRelation.DERIVED_COPY,
            derived_from_evidence_namespace=original.evidence_namespace,
            derived_from_evidence_id=original.evidence_id,
            derived_from_evidence_version=original.evidence_version,
            independence_status=IndependenceStatus.INDEPENDENCE_UNKNOWN,
        )
        result = assess((copy, original))
        self.assertEqual(len(result.verified_facts), 1)
        self.assertEqual(len(result.verified_facts[0].provenance), 2)
        self.assertTrue(
            all(
                item.independence_status is IndependenceStatus.INDEPENDENCE_UNKNOWN
                for item in result.verified_facts[0].provenance
            )
        )

    def test_correction_provenance_is_retained_without_independent_support(self):
        corrected = fact(
            reference_id=103,
            evidence_id="corrected-fact",
            semantic_lineage_id="corrected-lineage",
            lineage_relation=LineageRelation.CORRECTION,
            derived_from_evidence_namespace="evidence_passport",
            derived_from_evidence_id="prior-fact",
            derived_from_evidence_version="1",
            _supersedes_reference_id=UUID(int=99),
        )
        result = assess((corrected,))
        provenance = result.verified_facts[0].provenance[0]
        self.assertIs(provenance.lineage_relation, LineageRelation.CORRECTION)
        self.assertIs(
            provenance.independence_status,
            IndependenceStatus.INDEPENDENCE_UNKNOWN,
        )

    def test_result_is_deterministic_versioned_and_bound(self):
        references = (merchant_claim(), external_claim(), fact())
        forward = assess(references)
        reverse = assess(tuple(reversed(references)))
        self.assertEqual(forward.canonical_bytes, reverse.canonical_bytes)
        self.assertEqual(forward.rules_version, PHASE3_RULES_VERSION)
        self.assertEqual(forward.authority_revision, 7)
        self.assertEqual(forward.authority_digest, "a" * 64)
        self.assertEqual(forward.evidence_state_digest, "c" * 64)
        forbidden = ("credit_score", "pd", "approve", "decline", "loan_amount", "fraud")
        canonical = forward.canonical_bytes.decode("utf-8").lower()
        self.assertTrue(all(term not in canonical for term in forbidden))

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
            result = assess((merchant_claim(), fact()))
        self.assertEqual(len(result.contradictions), 1)

    def test_raw_snapshot_dict_and_inactive_capability_are_rejected(self):
        with self.assertRaises(TypeError):
            assess_claims({"verified": True})
        with self.assertRaises(TypeError):
            assess_claims(object.__new__(CaseSnapshot))
        capability, _ = ready((fact(),))
        with self.assertRaisesRegex(TypeError, "approved transaction-bound"):
            assess_claims(capability)

    def test_capability_copy_json_and_field_activation_bypasses_fail(self):
        capability, _ = ready((fact(),))
        with self.assertRaises(TypeError):
            copy.copy(capability)
        with self.assertRaises(TypeError):
            json.dumps(capability)
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(capability, "_phase3_active", True)
        with self.assertRaisesRegex(TypeError, "approved transaction-bound"):
            capability._consume_phase3(assess_claims)

    def test_active_capability_field_mutation_is_detected(self):
        capability, connection = ready((fact(),))
        gate = SyntheticGate(capability, connection)
        original = assess_claims

        def mutate_then_assess(item):
            object.__setattr__(item, "snapshot_digest", "d" * 64)
            return original(item)

        with (
            patch("olin.investigator.claims.assess_claims", mutate_then_assess),
            self.assertRaisesRegex(EvidenceBoundaryError, "altered"),
        ):
            gate.assess_claims_current(
                tenant_id=capability.tenant_id,
                case_id=capability.case_id,
                snapshot_id=capability.snapshot_id,
                as_of=NOW,
            )

    def test_copied_operation_context_expires_after_success_and_exception(self):
        for fail in (False, True):
            capability, connection = ready((fact(),))
            gate = SyntheticGate(capability, connection)
            captured = {}
            original = assess_claims

            def capture_context(
                item,
                *,
                captured_state=captured,
                should_fail=fail,
                classifier=original,
            ):
                captured_state["context"] = copy_context()
                captured_state["capability"] = item
                if should_fail:
                    raise RuntimeError("synthetic callback failure")
                return classifier(item)

            with patch("olin.investigator.claims.assess_claims", capture_context):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "synthetic callback"):
                        gate.assess_claims_current(
                            tenant_id=capability.tenant_id,
                            case_id=capability.case_id,
                            snapshot_id=capability.snapshot_id,
                            as_of=NOW,
                        )
                else:
                    gate.assess_claims_current(
                        tenant_id=capability.tenant_id,
                        case_id=capability.case_id,
                        snapshot_id=capability.snapshot_id,
                        as_of=NOW,
                    )
            with (
                self.subTest(fail=fail),
                self.assertRaisesRegex(TypeError, "approved transaction-bound"),
            ):
                captured["context"].run(original, captured["capability"])

    def test_phase3_requires_transaction_bound_capability(self):
        capability, _ = ready((fact(),))
        object.__setattr__(capability, "_connection", None)
        with self.assertRaisesRegex(TypeError, "approved transaction-bound"):
            capability._consume_phase3(assess_claims)

    def test_async_generator_and_lazy_callbacks_are_rejected(self):
        async def async_callback(_):
            return "async"

        def generator_callback(_):
            yield "later"

        class AsyncCallable:
            async def __call__(self, _):
                return "later"

        class AsyncGeneratorCallable:
            async def __call__(self, _):
                yield "later"

        for callback in (
            async_callback,
            generator_callback,
            AsyncCallable(),
            AsyncGeneratorCallable(),
        ):
            capability, connection = ready()
            with (
                self.subTest(callback=callback),
                self.assertRaisesRegex(TypeError, "synchronous"),
                connection.transaction(),
            ):
                capability.consume(callback)

        async def deferred():
            return "later"

        for callback in (
            lambda _: deferred(),
            lambda _: iter(("later",)),
            lambda _: {},
            lambda _: DeferredDataclass("later"),
            lambda _: StatefulString("later"),
        ):
            capability, connection = ready()
            with (
                self.subTest(callback=callback),
                self.assertRaises(TypeError),
                connection.transaction(),
            ):
                capability.consume(callback)

    def test_server_expiry_is_checked_immediately_before_kernel_invocation(self):
        capability, connection = ready((fact(),))

        def consumer(item):
            connection.callback_state_checks.append(connection.state_checks)
            return item.snapshot_id

        with connection.transaction():
            capability.consume(consumer)
        self.assertEqual(connection.callback_state_checks, [1])
        self.assertEqual(connection.state_checks, 2)

    def test_server_deadline_and_each_evidence_expiry_reject_before_callback(self):
        callback_called = []
        capability, connection = ready((fact(),))
        connection.server_time = NOW + timedelta(seconds=6)
        with (
            self.assertRaisesRegex(EvidenceBoundaryError, "deadline expired"),
            connection.transaction(),
        ):
            capability.consume(lambda _: callback_called.append(True))
        self.assertEqual(callback_called, [])

        expiry_fields = (
            "source_valid_until",
            "consent_expires_at",
            "retention_until",
            "evidence_expires_at",
        )
        for index, field in enumerate(expiry_fields, start=1):
            expiring = fact(
                reference_id=400 + index,
                **{field: NOW + timedelta(seconds=1)},
            )
            capability, connection = ready((expiring,))
            connection.server_time = NOW + timedelta(seconds=2)
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(
                    EvidenceBoundaryError, "expired during consumption"
                ),
                connection.transaction(),
            ):
                capability.consume(lambda _: callback_called.append(True))
        self.assertEqual(callback_called, [])

    def test_caller_cannot_forge_verified_merchant_claim(self):
        with self.assertRaisesRegex(EvidenceBoundaryError, "only VERIFIED_FACT"):
            merchant_claim(
                verification_status=VerificationStatus.VERIFIED_FOR_PROPOSITION
            )

    def test_decimal_context_does_not_change_canonical_result(self):
        original_precision = getcontext().prec
        original_rounding = getcontext().rounding
        original_inexact_trap = getcontext().traps[Inexact]
        try:
            baseline = assess((merchant_claim(), fact())).canonical_bytes
            getcontext().prec = 6
            getcontext().rounding = ROUND_DOWN
            getcontext().traps[Inexact] = True
            changed = assess((merchant_claim(), fact())).canonical_bytes
        finally:
            getcontext().prec = original_precision
            getcontext().rounding = original_rounding
            getcontext().traps[Inexact] = original_inexact_trap
        self.assertEqual(changed, baseline)

    def test_fractional_same_proposition_is_independent_of_decimal_context(self):
        references = (
            merchant_claim(proposition_value="260000.123456789"),
            fact(
                proposition_type="monthly_revenue",
                proposition_value="118000.123456789",
                semantic_lineage_id="fractional-verified-revenue",
            ),
        )
        original_precision = getcontext().prec
        original_rounding = getcontext().rounding
        original_inexact_trap = getcontext().traps[Inexact]
        try:
            baseline = assess(references).canonical_bytes
            getcontext().prec = 6
            getcontext().rounding = ROUND_DOWN
            getcontext().traps[Inexact] = True
            changed = assess(references).canonical_bytes
        finally:
            getcontext().prec = original_precision
            getcontext().rounding = original_rounding
            getcontext().traps[Inexact] = original_inexact_trap
        self.assertEqual(changed, baseline)
        self.assertEqual(len(assess(references).contradictions), 1)

    def test_exact_verified_revenue_changes_reconciliation_unknown(self):
        verified_revenue = fact(
            reference_id=112,
            proposition_type="monthly_revenue",
            proposition_value="260000",
            semantic_lineage_id="verified-total-revenue",
        )
        result = assess((merchant_claim(), fact(), verified_revenue))
        self.assertEqual(len(result.unknowns), 1)
        unknown = result.unknowns[0]
        self.assertIn(
            "Overall revenue is proposition-specifically verified",
            unknown.why_unresolved,
        )
        self.assertNotIn(
            "does not verify the remaining claimed revenue", unknown.why_unresolved
        )
        self.assertIn(
            verified_revenue.reference_id,
            unknown.evidence_considered,
        )
        self.assertEqual(len(result.contradictions), 1)
        self.assertNotIn(
            "MERCHANT_OVERSTATEMENT",
            {
                explanation.explanation_family
                for explanation in result.possible_explanations
            },
        )

    def test_provenance_keeps_verification_and_independence_distinct(self):
        result = assess((merchant_claim(), fact()))
        claim_provenance = result.claims[0].provenance[0]
        fact_provenance = result.verified_facts[0].provenance[0]
        self.assertEqual(claim_provenance.confidence, Confidence.CLAIM_ONLY)
        self.assertEqual(
            fact_provenance.confidence, Confidence.AUTHORITATIVE_PROPOSITION
        )
        self.assertIs(
            claim_provenance.independence_status,
            IndependenceStatus.INDEPENDENCE_UNKNOWN,
        )


if __name__ == "__main__":
    unittest.main()
