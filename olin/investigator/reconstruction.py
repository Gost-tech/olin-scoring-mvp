"""Deterministic Phase 4 economic reconstruction over accepted Phase 3 output."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from enum import Enum
from uuid import UUID

from .canonical import canonical_digest, canonical_json_bytes, normalize_timestamp
from .claims import (
    PHASE3_RULES_VERSION,
    PHASE3_SCHEMA_VERSION,
    Claim,
    ClaimsAssessment,
    Contradiction,
    DimensionalScope,
    Proposition,
    Provenance,
    Unknown,
    VerifiedFact,
)
from .evidence_boundary import EvidenceBoundaryError, ReasoningReadySnapshot

PHASE4_SCHEMA_VERSION = "investigator-economic-reconstruction-1"
PHASE4_RULES_VERSION = "investigator-economic-reconstruction-rules-1.1"

_ARITHMETIC_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, traps=[])
_MAX_DECIMAL_CHARACTERS = 128
_MAX_DECIMAL_DIGITS = 64
_MAX_DECIMAL_ADJUSTED_EXPONENT = 24
_SUPPORTED_CURRENCIES = frozenset({"MXN", "USD"})


class EconomicValueType(str, Enum):
    OBSERVED_VALUE = "OBSERVED_VALUE"
    CLAIMED_VALUE = "CLAIMED_VALUE"
    DERIVED_VALUE = "DERIVED_VALUE"
    CONSTRAINED_RANGE = "CONSTRAINED_RANGE"
    ESTIMATED_RANGE = "ESTIMATED_RANGE"
    UNKNOWN_VALUE = "UNKNOWN_VALUE"
    SCENARIO_VALUE = "SCENARIO_VALUE"


class EconomicDimension(str, Enum):
    REVENUE = "REVENUE"
    OPERATING_COSTS = "OPERATING_COSTS"
    OPERATING_MARGIN = "OPERATING_MARGIN"
    CASH_FLOW = "CASH_FLOW"
    DEBT_SERVICE = "DEBT_SERVICE"
    WORKING_CAPITAL = "WORKING_CAPITAL"


class ReconstructionStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    CONTRADICTED = "CONTRADICTED"


class CoverageType(str, Enum):
    BANK_ACCOUNT_COVERAGE = "BANK_ACCOUNT_COVERAGE"
    REVENUE_CHANNEL_COVERAGE = "REVENUE_CHANNEL_COVERAGE"
    COST_COVERAGE = "COST_COVERAGE"
    DEBT_COVERAGE = "DEBT_COVERAGE"
    PERIOD_COVERAGE = "PERIOD_COVERAGE"


class CoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AssessmentBinding:
    tenant_id: UUID
    case_id: UUID
    snapshot_id: UUID
    snapshot_digest: str
    authority_revision: int
    authority_digest: str
    evidence_state_digest: str
    checked_at: datetime
    canonical_projection_version: str
    phase3_schema_version: str
    phase3_rules_version: str
    assessment_digest: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "assessment_digest": self.assessment_digest,
            "authority_digest": self.authority_digest,
            "authority_revision": self.authority_revision,
            "case_id": str(self.case_id),
            "canonical_projection_version": self.canonical_projection_version,
            "checked_at": normalize_timestamp(self.checked_at),
            "evidence_state_digest": self.evidence_state_digest,
            "phase3_rules_version": self.phase3_rules_version,
            "phase3_schema_version": self.phase3_schema_version,
            "snapshot_digest": self.snapshot_digest,
            "snapshot_id": str(self.snapshot_id),
            "tenant_id": str(self.tenant_id),
        }


@dataclass(frozen=True, slots=True)
class CoverageDiagnostic:
    coverage_type: CoverageType
    subject_id: str | None
    period_start: object | None
    period_end: object | None
    status: CoverageStatus
    why: str
    input_proposition_digests: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "coverage_type": self.coverage_type.value,
            "period_end": (
                normalize_timestamp(self.period_end)
                if self.period_end is not None
                else None
            ),
            "period_start": (
                normalize_timestamp(self.period_start)
                if self.period_start is not None
                else None
            ),
            "input_proposition_digests": self.input_proposition_digests,
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "rule_id": self.rule_id,
            "status": self.status.value,
            "subject_id": self.subject_id,
            "why": self.why,
        }


@dataclass(frozen=True, slots=True)
class EconomicValue:
    value_type: EconomicValueType
    dimension: EconomicDimension
    quantity: str
    subject_id: str
    value: str
    unit: str
    period_start: object
    period_end: object
    dimensional_scope: DimensionalScope
    input_proposition_digests: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    formula: str | None
    assumptions: tuple[str, ...]
    rule_id: str
    rule_version: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "assumptions": self.assumptions,
            "dimension": self.dimension.value,
            "dimensional_scope": self.dimensional_scope.value,
            "formula": self.formula,
            "input_proposition_digests": self.input_proposition_digests,
            "period_end": normalize_timestamp(self.period_end),
            "period_start": normalize_timestamp(self.period_start),
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "quantity": self.quantity,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "subject_id": self.subject_id,
            "unit": self.unit,
            "value": self.value,
            "value_type": self.value_type.value,
        }


@dataclass(frozen=True, slots=True)
class ConstrainedRange:
    dimension: EconomicDimension
    quantity: str
    subject_id: str
    lower_bound: str | None
    upper_bound: str | None
    unit: str
    period_start: object
    period_end: object
    input_proposition_digests: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    assumptions: tuple[str, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "assumptions": self.assumptions,
            "dimension": self.dimension.value,
            "input_proposition_digests": self.input_proposition_digests,
            "lower_bound": self.lower_bound,
            "period_end": normalize_timestamp(self.period_end),
            "period_start": normalize_timestamp(self.period_start),
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "quantity": self.quantity,
            "rule_id": self.rule_id,
            "subject_id": self.subject_id,
            "unit": self.unit,
            "upper_bound": self.upper_bound,
            "value_type": EconomicValueType.CONSTRAINED_RANGE.value,
        }


@dataclass(frozen=True, slots=True)
class UnknownEconomicQuantity:
    dimension: EconomicDimension
    quantity: str
    subject_id: str | None
    status: ReconstructionStatus
    why_unresolved: str
    evidence_considered: tuple[UUID, ...]
    evidence_missing: tuple[str, ...]
    input_proposition_digests: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    contradiction_rule_ids: tuple[str, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "contradiction_rule_ids": self.contradiction_rule_ids,
            "dimension": self.dimension.value,
            "evidence_considered": tuple(
                str(item) for item in self.evidence_considered
            ),
            "evidence_missing": self.evidence_missing,
            "input_proposition_digests": self.input_proposition_digests,
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "quantity": self.quantity,
            "rule_id": self.rule_id,
            "status": self.status.value,
            "subject_id": self.subject_id,
            "value_type": EconomicValueType.UNKNOWN_VALUE.value,
            "why_unresolved": self.why_unresolved,
        }


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    dimension: EconomicDimension
    status: ReconstructionStatus
    why: str
    input_proposition_digests: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    contradiction_rule_ids: tuple[str, ...]
    rule_id: str
    rule_version: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "dimension": self.dimension.value,
            "input_proposition_digests": self.input_proposition_digests,
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "contradiction_rule_ids": self.contradiction_rule_ids,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "status": self.status.value,
            "why": self.why,
        }


@dataclass(frozen=True, slots=True)
class EconomicReconstruction:
    schema_version: str
    rules_version: str
    input_assessment: AssessmentBinding
    coverage_diagnostics: tuple[CoverageDiagnostic, ...]
    dimension_assessments: tuple[DimensionAssessment, ...]
    observed_values: tuple[EconomicValue, ...]
    claimed_values: tuple[EconomicValue, ...]
    derived_values: tuple[EconomicValue, ...]
    constrained_ranges: tuple[ConstrainedRange, ...]
    unresolved_quantities: tuple[UnknownEconomicQuantity, ...]
    phase3_unknowns: tuple[Unknown, ...]
    contradictions_carried_forward: tuple[Contradiction, ...]
    assumptions: tuple[str, ...]

    def canonical_record(self) -> dict[str, object]:
        return {
            "assumptions": self.assumptions,
            "claimed_values": tuple(
                item.canonical_record() for item in self.claimed_values
            ),
            "constrained_ranges": tuple(
                item.canonical_record() for item in self.constrained_ranges
            ),
            "contradictions_carried_forward": tuple(
                item.canonical_record() for item in self.contradictions_carried_forward
            ),
            "coverage_diagnostics": tuple(
                item.canonical_record() for item in self.coverage_diagnostics
            ),
            "derived_values": tuple(
                item.canonical_record() for item in self.derived_values
            ),
            "dimension_assessments": tuple(
                item.canonical_record() for item in self.dimension_assessments
            ),
            "input_assessment": self.input_assessment.canonical_record(),
            "observed_values": tuple(
                item.canonical_record() for item in self.observed_values
            ),
            "phase3_unknowns": tuple(
                item.canonical_record() for item in self.phase3_unknowns
            ),
            "rules_version": self.rules_version,
            "schema_version": self.schema_version,
            "unresolved_quantities": tuple(
                item.canonical_record() for item in self.unresolved_quantities
            ),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())


_PHASE4_OPERATION: ContextVar[
    tuple[
        ClaimsAssessment,
        str,
        tuple[object, ...],
        list[bool],
        datetime,
        str,
    ]
    | None
] = ContextVar("investigator_phase4_operation", default=None)

_COVERAGE_PROPOSITIONS = {
    "bank_account_coverage": CoverageType.BANK_ACCOUNT_COVERAGE,
    "revenue_channel_coverage": CoverageType.REVENUE_CHANNEL_COVERAGE,
    "cost_coverage": CoverageType.COST_COVERAGE,
    "debt_coverage": CoverageType.DEBT_COVERAGE,
    "period_coverage": CoverageType.PERIOD_COVERAGE,
}

_DIRECT_QUANTITIES = {
    "bank_visible_inflows": (EconomicDimension.REVENUE, "observable_bank_inflows"),
    "monthly_revenue": (EconomicDimension.REVENUE, "total_monthly_revenue"),
    "monthly_operating_costs": (
        EconomicDimension.OPERATING_COSTS,
        "total_monthly_operating_costs",
    ),
    "monthly_operating_cash_inflows": (
        EconomicDimension.CASH_FLOW,
        "monthly_operating_cash_inflows",
    ),
    "monthly_operating_cash_outflows": (
        EconomicDimension.CASH_FLOW,
        "monthly_operating_cash_outflows",
    ),
    "monthly_debt_service": (EconomicDimension.DEBT_SERVICE, "monthly_debt_service"),
    "working_capital": (EconomicDimension.WORKING_CAPITAL, "working_capital"),
}

_NORMALIZATION_RULES = {
    "daily_operating_costs": (
        30,
        1,
        1,
        "DAILY_VALUE * 30",
        "P4-NORMALIZE-DAILY-TO-MONTHLY-001",
        "Strict 30-day equivalent at the source-period average daily rate; not an observed calendar-month total",
    ),
    "weekly_operating_costs": (
        30,
        7,
        7,
        "WEEKLY_VALUE * 30 / 7",
        "P4-NORMALIZE-WEEKLY-TO-MONTHLY-002",
        "Strict 30-day equivalent at the source-period average daily rate; seven-day source, not an observed calendar-month total",
    ),
    "annual_operating_costs": (
        30,
        365,
        365,
        "ANNUAL_VALUE * 30 / 365",
        "P4-NORMALIZE-ANNUAL-TO-MONTHLY-002",
        "Strict 30-day equivalent at the source-period average daily rate; fixed 365-day source, not a calendar year or observed calendar-month total",
    ),
}


def _assessment_fingerprint(assessment: ClaimsAssessment) -> tuple[object, ...]:
    return (
        assessment.tenant_id,
        assessment.case_id,
        assessment.snapshot_id,
        assessment.snapshot_digest,
        assessment.authority_revision,
        assessment.authority_digest,
        assessment.evidence_state_digest,
        assessment.schema_version,
        assessment.rules_version,
        canonical_digest(assessment.canonical_record()),
    )


def _require_accepted_assessment(
    assessment: ClaimsAssessment,
) -> tuple[ClaimsAssessment, str, tuple[object, ...], list[bool], datetime, str]:
    if type(assessment) is not ClaimsAssessment:
        raise TypeError("Phase 4 accepts only an approved ClaimsAssessment")
    operation = _PHASE4_OPERATION.get()
    if operation is None or operation[0] is not assessment or not operation[3][0]:
        raise TypeError("Phase 4 requires the approved assessment acceptance boundary")
    if operation[1] != canonical_digest(assessment.canonical_record()):
        raise EvidenceBoundaryError("accepted ClaimsAssessment was altered")
    if operation[2] != _assessment_fingerprint(assessment):
        raise EvidenceBoundaryError("accepted ClaimsAssessment binding changed")
    return operation


def _accept_and_reconstruct(
    assessment: ClaimsAssessment, ready: ReasoningReadySnapshot
) -> EconomicReconstruction:
    """Accept the exact Phase 3 output while its authority transaction is current."""
    ready._require_phase3_operation()
    if type(assessment) is not ClaimsAssessment:
        raise TypeError("Phase 4 accepts only an approved ClaimsAssessment")
    if (
        assessment.schema_version != PHASE3_SCHEMA_VERSION
        or assessment.rules_version != PHASE3_RULES_VERSION
    ):
        raise EvidenceBoundaryError("unsupported Phase 3 schema or rules version")
    expected = (
        ready.tenant_id,
        ready.case_id,
        ready.snapshot_id,
        ready.snapshot_digest,
        ready.authority_revision,
        ready.authority_state_digest,
        ready.evidence_state_digest,
    )
    actual = (
        assessment.tenant_id,
        assessment.case_id,
        assessment.snapshot_id,
        assessment.snapshot_digest,
        assessment.authority_revision,
        assessment.authority_digest,
        assessment.evidence_state_digest,
    )
    if actual != expected:
        raise EvidenceBoundaryError(
            "ClaimsAssessment does not match current authority binding"
        )
    ready._current_transaction_state(stage="ended")
    digest = canonical_digest(assessment.canonical_record())
    lease = [True]
    token = _PHASE4_OPERATION.set(
        (
            assessment,
            digest,
            _assessment_fingerprint(assessment),
            lease,
            ready.checked_at,
            ready.canonical_projection_version,
        )
    )
    try:
        return reconstruct_economics(assessment)
    finally:
        lease[0] = False
        _PHASE4_OPERATION.reset(token)


def _decimal(value: str) -> Decimal | None:
    if len(value) > _MAX_DECIMAL_CHARACTERS:
        return None
    try:
        with localcontext(_ARITHMETIC_CONTEXT):
            parsed = Decimal(value)
    except DecimalException:
        return None
    if not parsed.is_finite() or len(parsed.as_tuple().digits) > _MAX_DECIMAL_DIGITS:
        return None
    if parsed and abs(parsed.adjusted()) > _MAX_DECIMAL_ADJUSTED_EXPONENT:
        return None
    return parsed


def _valid_result(value: Decimal) -> bool:
    return bool(
        value.is_finite()
        and (not value or abs(value.adjusted()) <= _MAX_DECIMAL_ADJUSTED_EXPONENT)
    )


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(_ARITHMETIC_CONTEXT), "f")


def _proposition_digest(proposition: Proposition) -> str:
    return canonical_digest(proposition.canonical_record())


def _ordered_provenance(items: tuple[Provenance, ...]) -> tuple[Provenance, ...]:
    return tuple(sorted(items, key=lambda item: str(item.reference_id)))


def _unique_ordered_provenance(
    items: tuple[Provenance, ...],
) -> tuple[Provenance, ...]:
    by_reference: dict[UUID, Provenance] = {}
    for item in items:
        existing = by_reference.get(item.reference_id)
        if (
            existing is not None
            and existing.canonical_record() != item.canonical_record()
        ):
            raise EvidenceBoundaryError(
                "one evidence reference has conflicting provenance records"
            )
        by_reference[item.reference_id] = item
    return tuple(by_reference[key] for key in sorted(by_reference, key=str))


def _references(items: tuple[Provenance, ...]) -> tuple[UUID, ...]:
    return tuple(item.reference_id for item in _unique_ordered_provenance(items))


def _coverage_diagnostics(
    facts: tuple[VerifiedFact, ...],
) -> tuple[CoverageDiagnostic, ...]:
    diagnostics = []
    for proposition_type, coverage_type in _COVERAGE_PROPOSITIONS.items():
        candidates = tuple(
            fact
            for fact in facts
            if fact.proposition.proposition_type == proposition_type
        )
        groups: dict[tuple[str, object, object], list[VerifiedFact]] = {}
        for fact in candidates:
            proposition = fact.proposition
            groups.setdefault(
                (
                    proposition.subject_id,
                    proposition.period_start,
                    proposition.period_end,
                ),
                [],
            ).append(fact)
        if not groups:
            diagnostics.append(
                CoverageDiagnostic(
                    coverage_type=coverage_type,
                    subject_id=None,
                    period_start=None,
                    period_end=None,
                    status=CoverageStatus.UNKNOWN,
                    why="No accepted authoritative proposition establishes this coverage.",
                    input_proposition_digests=(),
                    provenance=(),
                    rule_id="P4-COVERAGE-001",
                )
            )
            continue
        for (subject_id, period_start, period_end), group in groups.items():
            valid = all(
                fact.proposition.proposition_schema_version == 1
                and fact.proposition.unit == "STATUS"
                and fact.proposition.value in CoverageStatus._value2member_map_
                for fact in group
            )
            statuses = (
                {CoverageStatus(fact.proposition.value) for fact in group}
                if valid
                else set()
            )
            if len(statuses) == 1:
                status = statuses.pop()
                why = "Authoritative coverage metadata applies to this subject and period."
            elif valid:
                status = CoverageStatus.UNKNOWN
                why = "Authoritative coverage propositions disagree for this subject and period."
            else:
                status = CoverageStatus.UNKNOWN
                why = "Coverage metadata is invalid or uses an unsupported proposition schema."
            diagnostics.append(
                CoverageDiagnostic(
                    coverage_type=coverage_type,
                    subject_id=subject_id,
                    period_start=period_start,
                    period_end=period_end,
                    status=status,
                    why=why,
                    input_proposition_digests=tuple(
                        sorted(_proposition_digest(fact.proposition) for fact in group)
                    ),
                    provenance=_ordered_provenance(
                        tuple(item for fact in group for item in fact.provenance)
                    ),
                    rule_id="P4-COVERAGE-001",
                )
            )
    return tuple(
        sorted(
            diagnostics, key=lambda item: canonical_json_bytes(item.canonical_record())
        )
    )


def _direct_value(
    item: VerifiedFact | Claim, value_type: EconomicValueType
) -> EconomicValue | None:
    definition = _DIRECT_QUANTITIES.get(item.proposition.proposition_type)
    amount = _decimal(item.proposition.value)
    unit = item.proposition.unit
    if (
        definition is None
        or item.proposition.proposition_schema_version != 1
        or amount is None
        or unit not in _SUPPORTED_CURRENCIES
        or (amount < 0 and item.proposition.proposition_type != "working_capital")
    ):
        return None
    dimension, quantity = definition
    return EconomicValue(
        value_type=value_type,
        dimension=dimension,
        quantity=quantity,
        subject_id=item.proposition.subject_id,
        value=item.proposition.value,
        unit=item.proposition.unit,
        period_start=item.proposition.period_start,
        period_end=item.proposition.period_end,
        dimensional_scope=item.proposition.dimensional_scope,
        input_proposition_digests=(_proposition_digest(item.proposition),),
        provenance=item.provenance,
        formula=None,
        assumptions=(),
        rule_id=(
            "P4-OBSERVED-001"
            if value_type is EconomicValueType.OBSERVED_VALUE
            else "P4-CLAIMED-001"
        ),
        rule_version=PHASE4_RULES_VERSION,
    )


def _normalized_cost(fact: VerifiedFact) -> EconomicValue | None:
    rule = _NORMALIZATION_RULES.get(fact.proposition.proposition_type)
    amount = _decimal(fact.proposition.value)
    unit = fact.proposition.unit
    if (
        rule is None
        or fact.proposition.proposition_schema_version != 1
        or amount is None
        or amount < 0
        or unit not in _SUPPORTED_CURRENCIES
    ):
        return None
    numerator, denominator, source_days, formula, rule_id, assumption = rule
    period_start = fact.proposition.period_start
    period_end = fact.proposition.period_end
    if not isinstance(period_start, datetime) or not isinstance(period_end, datetime):
        return None
    try:
        source_period = period_end - period_start
    except (TypeError, OverflowError):
        return None
    if source_period != timedelta(days=source_days):
        return None
    try:
        with localcontext(_ARITHMETIC_CONTEXT):
            normalized = amount * Decimal(numerator) / Decimal(denominator)
    except DecimalException:
        return None
    if not _valid_result(normalized):
        return None
    return EconomicValue(
        value_type=EconomicValueType.DERIVED_VALUE,
        dimension=EconomicDimension.OPERATING_COSTS,
        quantity="normalized_monthly_operating_costs",
        subject_id=fact.proposition.subject_id,
        value=_decimal_text(normalized),
        unit=fact.proposition.unit,
        period_start=period_start,
        period_end=period_start + timedelta(days=30),
        dimensional_scope=fact.proposition.dimensional_scope,
        input_proposition_digests=(_proposition_digest(fact.proposition),),
        provenance=fact.provenance,
        formula=formula,
        assumptions=(assumption,),
        rule_id=rule_id,
        rule_version=PHASE4_RULES_VERSION,
    )


def _applicable_coverage(
    diagnostics: tuple[CoverageDiagnostic, ...],
    coverage_type: CoverageType,
    value: EconomicValue,
) -> CoverageDiagnostic | None:
    matches = tuple(
        item
        for item in diagnostics
        if item.coverage_type is coverage_type
        and item.subject_id == value.subject_id
        and item.period_start == value.period_start
        and item.period_end == value.period_end
    )
    return matches[0] if len(matches) == 1 else None


def _has_complete_coverage(
    diagnostics: tuple[CoverageDiagnostic, ...],
    coverage_type: CoverageType,
    value: EconomicValue,
) -> bool:
    diagnostic = _applicable_coverage(diagnostics, coverage_type, value)
    return diagnostic is not None and diagnostic.status is CoverageStatus.COMPLETE


def _relevant_contradictions(
    assessment: ClaimsAssessment, proposition_types: set[str]
) -> tuple[Contradiction, ...]:
    return tuple(
        item
        for item in assessment.contradictions
        if any(
            proposition.proposition_type in proposition_types
            for proposition in item.propositions
        )
    )


def _revenue_gap(assessment: ClaimsAssessment) -> tuple[EconomicValue, ...]:
    results = []
    expected_type = (
        "MATERIAL_DISAGREEMENT_DECLARED_REVENUE_EXCEEDS_BANK_VISIBLE_INFLOWS"
    )
    for contradiction in assessment.contradictions:
        if contradiction.contradiction_type != expected_type:
            continue
        claims = tuple(
            item
            for item in contradiction.propositions
            if item.proposition_type == "monthly_revenue"
        )
        inflows = tuple(
            item
            for item in contradiction.propositions
            if item.proposition_type == "bank_visible_inflows"
        )
        if len(claims) != 1 or len(inflows) != 1:
            continue
        claim, inflow = claims[0], inflows[0]
        if (
            claim.subject_id != inflow.subject_id
            or claim.proposition_schema_version != 1
            or inflow.proposition_schema_version != 1
            or claim.unit != inflow.unit
            or claim.unit not in _SUPPORTED_CURRENCIES
            or claim.period_start != inflow.period_start
            or claim.period_end != inflow.period_end
        ):
            continue
        claimed, observed = _decimal(claim.value), _decimal(inflow.value)
        if (
            claimed is None
            or observed is None
            or claimed < 0
            or observed < 0
            or claimed < observed
        ):
            continue
        with localcontext(_ARITHMETIC_CONTEXT):
            gap = claimed - observed
        if not _valid_result(gap):
            continue
        results.append(
            EconomicValue(
                value_type=EconomicValueType.DERIVED_VALUE,
                dimension=EconomicDimension.REVENUE,
                quantity="revenue_reconciliation_gap",
                subject_id=claim.subject_id,
                value=_decimal_text(gap),
                unit=claim.unit,
                period_start=claim.period_start,
                period_end=claim.period_end,
                dimensional_scope=DimensionalScope.UNSPECIFIED,
                input_proposition_digests=tuple(
                    sorted((_proposition_digest(claim), _proposition_digest(inflow)))
                ),
                provenance=contradiction.provenance,
                formula="CLAIMED_MONTHLY_REVENUE - OBSERVABLE_BANK_INFLOWS",
                assumptions=(
                    "Arithmetic gap only; it does not establish missing, false, or sustainable revenue.",
                ),
                rule_id="P4-DERIVE-REVENUE-GAP-001",
                rule_version=PHASE4_RULES_VERSION,
            )
        )
    return tuple(results)


def _derive_margin() -> EconomicValue | None:
    # V1 propositions do not establish compatible gross/net, tax, accounting,
    # or cost-category bases. Coverage alone cannot make that ratio a margin.
    return None


def _derive_cash_flows(
    observed: tuple[EconomicValue, ...],
    diagnostics: tuple[CoverageDiagnostic, ...],
    assessment: ClaimsAssessment,
) -> tuple[EconomicValue, ...]:
    quantities = {
        "monthly_operating_cash_inflows",
        "monthly_operating_cash_outflows",
    }
    groups: dict[tuple[object, ...], dict[str, list[EconomicValue]]] = {}
    for value in observed:
        if value.quantity not in quantities:
            continue
        key = (
            value.subject_id,
            value.unit,
            value.period_start,
            value.period_end,
            value.dimensional_scope,
        )
        groups.setdefault(key, {}).setdefault(value.quantity, []).append(value)

    results = []
    for group in groups.values():
        inflow_values = group.get("monthly_operating_cash_inflows", [])
        outflow_values = group.get("monthly_operating_cash_outflows", [])
        if len(inflow_values) != 1 or len(outflow_values) != 1:
            continue
        inflows, outflows = inflow_values[0], outflow_values[0]
        period_coverage = _applicable_coverage(
            diagnostics, CoverageType.PERIOD_COVERAGE, inflows
        )
        contradictions = _relevant_contradictions(assessment, quantities)
        matching_contradiction = any(
            proposition.subject_id == inflows.subject_id
            and proposition.unit == inflows.unit
            and proposition.period_start == inflows.period_start
            and proposition.period_end == inflows.period_end
            and proposition.dimensional_scope is inflows.dimensional_scope
            for contradiction in contradictions
            for proposition in contradiction.propositions
            if proposition.proposition_type in quantities
        )
        if (
            period_coverage is None
            or period_coverage.status is not CoverageStatus.COMPLETE
            or matching_contradiction
        ):
            continue
        inflow_amount = _decimal(inflows.value)
        outflow_amount = _decimal(outflows.value)
        if inflow_amount is None or outflow_amount is None:
            continue
        with localcontext(_ARITHMETIC_CONTEXT):
            net = inflow_amount - outflow_amount
        if not _valid_result(net):
            continue
        results.append(
            EconomicValue(
                value_type=EconomicValueType.DERIVED_VALUE,
                dimension=EconomicDimension.CASH_FLOW,
                quantity="monthly_net_operating_cash_movement",
                subject_id=inflows.subject_id,
                value=_decimal_text(net),
                unit=inflows.unit,
                period_start=inflows.period_start,
                period_end=inflows.period_end,
                dimensional_scope=inflows.dimensional_scope,
                input_proposition_digests=tuple(
                    sorted(
                        inflows.input_proposition_digests
                        + outflows.input_proposition_digests
                        + period_coverage.input_proposition_digests
                    )
                ),
                provenance=_ordered_provenance(
                    inflows.provenance
                    + outflows.provenance
                    + period_coverage.provenance
                ),
                formula=(
                    "MONTHLY_OPERATING_CASH_INFLOWS - MONTHLY_OPERATING_CASH_OUTFLOWS"
                ),
                assumptions=(
                    "Arithmetic preserves the accepted input scope; it does not establish business-total cash flow.",
                ),
                rule_id="P4-DERIVE-NET-OPERATING-CASH-001",
                rule_version=PHASE4_RULES_VERSION,
            )
        )
    return tuple(results)


def _unknown(
    dimension: EconomicDimension,
    quantity: str,
    why: str,
    missing: tuple[str, ...],
    facts: tuple[VerifiedFact, ...] = (),
    claims: tuple[Claim, ...] = (),
    contradictions: tuple[Contradiction, ...] = (),
    coverage: tuple[CoverageDiagnostic, ...] = (),
) -> UnknownEconomicQuantity:
    provenance = (
        tuple(item for finding in facts + claims for item in finding.provenance)
        + tuple(
            item
            for contradiction in contradictions
            for item in contradiction.provenance
        )
        + tuple(item for diagnostic in coverage for item in diagnostic.provenance)
    )
    subjects = {finding.proposition.subject_id for finding in facts + claims}
    subjects.update(
        proposition.subject_id
        for contradiction in contradictions
        for proposition in contradiction.propositions
    )
    subjects.update(
        diagnostic.subject_id
        for diagnostic in coverage
        if diagnostic.subject_id is not None
    )
    return UnknownEconomicQuantity(
        dimension=dimension,
        quantity=quantity,
        subject_id=subjects.pop() if len(subjects) == 1 else None,
        status=(
            ReconstructionStatus.CONTRADICTED
            if contradictions
            else ReconstructionStatus.INSUFFICIENT_INPUT
        ),
        why_unresolved=why,
        evidence_considered=_references(provenance),
        evidence_missing=missing,
        input_proposition_digests=tuple(
            sorted(
                {_proposition_digest(finding.proposition) for finding in facts + claims}
                | {
                    _proposition_digest(proposition)
                    for contradiction in contradictions
                    for proposition in contradiction.propositions
                }
                | {
                    digest
                    for diagnostic in coverage
                    for digest in diagnostic.input_proposition_digests
                }
            )
        ),
        provenance=_unique_ordered_provenance(provenance),
        contradiction_rule_ids=tuple(sorted(item.rule_id for item in contradictions)),
        rule_id="P4-UNKNOWN-001",
    )


def _dimension_assessments(
    observed: tuple[EconomicValue, ...],
    claimed: tuple[EconomicValue, ...],
    derived: tuple[EconomicValue, ...],
    unknowns: tuple[UnknownEconomicQuantity, ...],
) -> tuple[DimensionAssessment, ...]:
    results = []
    for dimension in EconomicDimension:
        dimension_values = tuple(
            item for item in observed + claimed + derived if item.dimension is dimension
        )
        dimension_unknowns = tuple(
            item for item in unknowns if item.dimension is dimension
        )
        has_supported = any(item.dimension is dimension for item in observed + derived)
        has_claim = any(item.dimension is dimension for item in claimed)
        if any(
            item.status is ReconstructionStatus.CONTRADICTED
            for item in dimension_unknowns
        ):
            status = ReconstructionStatus.CONTRADICTED
            why = "A carried Phase 3 disagreement constrains this dimension."
        elif has_supported and (dimension_unknowns or has_claim):
            status = ReconstructionStatus.PARTIALLY_SUPPORTED
            why = (
                "Some quantities are supported while claims or material components "
                "remain unresolved."
            )
        elif has_supported:
            status = ReconstructionStatus.SUPPORTED
            why = "Accepted inputs support the emitted quantities for this bounded dimension."
        elif has_claim:
            status = ReconstructionStatus.INSUFFICIENT_INPUT
            why = (
                "Claimed values are preserved, but no authoritative input supports "
                "this dimension."
            )
        else:
            status = ReconstructionStatus.INSUFFICIENT_INPUT
            why = "Accepted input does not support reconstruction of this dimension."
        results.append(
            DimensionAssessment(
                dimension=dimension,
                status=status,
                why=why,
                input_proposition_digests=tuple(
                    sorted(
                        {
                            digest
                            for item in dimension_values
                            for digest in item.input_proposition_digests
                        }
                        | {
                            digest
                            for item in dimension_unknowns
                            for digest in item.input_proposition_digests
                        }
                    )
                ),
                provenance=_unique_ordered_provenance(
                    tuple(
                        provenance
                        for item in dimension_values
                        for provenance in item.provenance
                    )
                    + tuple(
                        provenance
                        for item in dimension_unknowns
                        for provenance in item.provenance
                    )
                ),
                contradiction_rule_ids=tuple(
                    sorted(
                        {
                            rule_id
                            for item in dimension_unknowns
                            for rule_id in item.contradiction_rule_ids
                        }
                    )
                ),
                rule_id="P4-DIMENSION-STATUS-001",
                rule_version=PHASE4_RULES_VERSION,
            )
        )
    return tuple(results)


def reconstruct_economics(assessment: ClaimsAssessment) -> EconomicReconstruction:
    """Reconstruct bounded economics from one live, accepted Phase 3 assessment."""
    operation = _require_accepted_assessment(assessment)
    diagnostics = _coverage_diagnostics(assessment.verified_facts)
    observed = tuple(
        value
        for fact in assessment.verified_facts
        if (value := _direct_value(fact, EconomicValueType.OBSERVED_VALUE)) is not None
    )
    claimed = tuple(
        value
        for claim in assessment.claims
        if (value := _direct_value(claim, EconomicValueType.CLAIMED_VALUE)) is not None
    )
    normalized = tuple(
        value
        for fact in assessment.verified_facts
        if (value := _normalized_cost(fact)) is not None
    )
    derived_values = list(_revenue_gap(assessment) + normalized)
    margin = _derive_margin()
    if margin is not None:
        derived_values.append(margin)
    cash_flows = _derive_cash_flows(observed, diagnostics, assessment)
    derived_values.extend(cash_flows)

    revenue_facts = tuple(
        item
        for item in assessment.verified_facts
        if item.proposition.proposition_type
        in {"monthly_revenue", "bank_visible_inflows"}
    )
    revenue_claims = tuple(
        item
        for item in assessment.claims
        if item.proposition.proposition_type == "monthly_revenue"
    )
    revenue_contradictions = _relevant_contradictions(
        assessment, {"monthly_revenue", "bank_visible_inflows"}
    )
    cost_facts = tuple(
        item
        for item in assessment.verified_facts
        if item.proposition.proposition_type
        in {"monthly_operating_costs", *tuple(_NORMALIZATION_RULES)}
    )
    cost_claims = tuple(
        item
        for item in assessment.claims
        if item.proposition.proposition_type == "monthly_operating_costs"
    )
    cash_facts = tuple(
        item
        for item in assessment.verified_facts
        if item.proposition.proposition_type
        in {"monthly_operating_cash_inflows", "monthly_operating_cash_outflows"}
    )
    debt_facts = tuple(
        item
        for item in assessment.verified_facts
        if item.proposition.proposition_type == "monthly_debt_service"
    )
    debt_claims = tuple(
        item
        for item in assessment.claims
        if item.proposition.proposition_type == "monthly_debt_service"
    )
    working_capital_facts = tuple(
        item
        for item in assessment.verified_facts
        if item.proposition.proposition_type == "working_capital"
    )
    observed_cost_totals = tuple(
        item for item in observed if item.quantity == "total_monthly_operating_costs"
    )
    cost_total_supported = (
        len(observed_cost_totals) == 1
        and observed_cost_totals[0].dimensional_scope is DimensionalScope.BUSINESS_TOTAL
        and _has_complete_coverage(
            diagnostics, CoverageType.COST_COVERAGE, observed_cost_totals[0]
        )
        and not _relevant_contradictions(assessment, {"monthly_operating_costs"})
    )
    observed_working_capital = tuple(
        item for item in observed if item.quantity == "working_capital"
    )
    working_capital_supported = len(
        observed_working_capital
    ) == 1 and not _relevant_contradictions(assessment, {"working_capital"})
    revenue_coverage = tuple(
        item
        for item in diagnostics
        if item.coverage_type
        in {
            CoverageType.BANK_ACCOUNT_COVERAGE,
            CoverageType.REVENUE_CHANNEL_COVERAGE,
        }
    )
    cost_coverage = tuple(
        item for item in diagnostics if item.coverage_type is CoverageType.COST_COVERAGE
    )
    period_coverage = tuple(
        item
        for item in diagnostics
        if item.coverage_type is CoverageType.PERIOD_COVERAGE
    )
    debt_coverage = tuple(
        item for item in diagnostics if item.coverage_type is CoverageType.DEBT_COVERAGE
    )

    unresolved = [
        _unknown(
            EconomicDimension.REVENUE,
            "total_sustainable_revenue",
            "Observable inflows and claims do not establish sustainable total revenue.",
            ("authoritative total-revenue and channel-coverage evidence",),
            revenue_facts,
            revenue_claims,
            revenue_contradictions,
            revenue_coverage,
        ),
        _unknown(
            EconomicDimension.REVENUE,
            "additional_revenue_channels",
            "Additional revenue channels and total account coverage are unresolved.",
            ("authoritative channel and account-coverage reconciliation",),
            revenue_facts,
            revenue_claims,
            revenue_contradictions,
            revenue_coverage,
        ),
    ]
    if not cost_total_supported:
        unresolved.append(
            _unknown(
                EconomicDimension.OPERATING_COSTS,
                "total_operating_costs",
                "Available cost evidence does not establish the complete cost structure.",
                ("complete authoritative operating-cost evidence and coverage",),
                cost_facts,
                cost_claims,
                _relevant_contradictions(assessment, {"monthly_operating_costs"}),
                cost_coverage,
            )
        )
    if margin is None:
        unresolved.append(
            _unknown(
                EconomicDimension.OPERATING_MARGIN,
                "operating_margin",
                "V1 inputs do not establish compatible accounting bases for revenue and costs.",
                ("aligned gross/net, tax, accounting, and cost-category bases",),
                revenue_facts + cost_facts,
                revenue_claims + cost_claims,
                _relevant_contradictions(
                    assessment, {"monthly_revenue", "monthly_operating_costs"}
                ),
                revenue_coverage + cost_coverage + period_coverage,
            )
        )
    observed_cash_values = tuple(
        item
        for item in observed
        if item.quantity
        in {
            "monthly_operating_cash_inflows",
            "monthly_operating_cash_outflows",
        }
    )
    all_cash_inputs_reconstructed = bool(cash_flows) and (
        len(cash_flows) * 2 == len(observed_cash_values) == len(cash_facts)
    )
    if not all_cash_inputs_reconstructed:
        unresolved.append(
            _unknown(
                EconomicDimension.CASH_FLOW,
                "net_operating_cash_movement",
                "Compatible verified operating cash components are incomplete.",
                ("verified operating cash inflows, outflows, and period coverage",),
                cash_facts,
                (),
                _relevant_contradictions(
                    assessment,
                    {
                        "monthly_operating_cash_inflows",
                        "monthly_operating_cash_outflows",
                    },
                ),
                period_coverage,
            )
        )
    unresolved.append(
        _unknown(
            EconomicDimension.DEBT_SERVICE,
            "total_debt_service",
            "V1 does not aggregate obligations or treat one obligation as total debt service.",
            (
                "authoritative total debt-service proposition or safe obligation aggregation",
            ),
            debt_facts,
            debt_claims,
            _relevant_contradictions(assessment, {"monthly_debt_service"}),
            debt_coverage,
        )
    )
    if not working_capital_supported:
        unresolved.append(
            _unknown(
                EconomicDimension.WORKING_CAPITAL,
                "working_capital",
                "No proposition-specific verified working-capital value is present.",
                ("authoritative working-capital evidence",),
                working_capital_facts,
            )
        )

    observed = tuple(
        sorted(observed, key=lambda item: canonical_json_bytes(item.canonical_record()))
    )
    claimed = tuple(
        sorted(claimed, key=lambda item: canonical_json_bytes(item.canonical_record()))
    )
    derived = tuple(
        sorted(
            derived_values,
            key=lambda item: canonical_json_bytes(item.canonical_record()),
        )
    )
    unresolved_tuple = tuple(
        sorted(unresolved, key=lambda item: (item.dimension.value, item.quantity))
    )
    result = EconomicReconstruction(
        schema_version=PHASE4_SCHEMA_VERSION,
        rules_version=PHASE4_RULES_VERSION,
        input_assessment=AssessmentBinding(
            tenant_id=assessment.tenant_id,
            case_id=assessment.case_id,
            snapshot_id=assessment.snapshot_id,
            snapshot_digest=assessment.snapshot_digest,
            authority_revision=assessment.authority_revision,
            authority_digest=assessment.authority_digest,
            evidence_state_digest=assessment.evidence_state_digest,
            checked_at=operation[4],
            canonical_projection_version=operation[5],
            phase3_schema_version=assessment.schema_version,
            phase3_rules_version=assessment.rules_version,
            assessment_digest=canonical_digest(assessment.canonical_record()),
        ),
        coverage_diagnostics=diagnostics,
        dimension_assessments=_dimension_assessments(
            observed, claimed, derived, unresolved_tuple
        ),
        observed_values=observed,
        claimed_values=claimed,
        derived_values=derived,
        constrained_ranges=(),
        unresolved_quantities=unresolved_tuple,
        phase3_unknowns=assessment.unknowns,
        contradictions_carried_forward=assessment.contradictions,
        assumptions=(),
    )
    if not ReasoningReadySnapshot._is_closed_eager(result):
        raise TypeError("Phase 4 reconstruction must be closed eager data")
    return result


__all__ = [
    "PHASE4_RULES_VERSION",
    "PHASE4_SCHEMA_VERSION",
    "AssessmentBinding",
    "ConstrainedRange",
    "CoverageDiagnostic",
    "CoverageStatus",
    "CoverageType",
    "DimensionAssessment",
    "EconomicDimension",
    "EconomicReconstruction",
    "EconomicValue",
    "EconomicValueType",
    "ReconstructionStatus",
    "UnknownEconomicQuantity",
    "reconstruct_economics",
]
