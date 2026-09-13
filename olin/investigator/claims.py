"""Deterministic Phase 3 claims, unknowns, and contradictions kernel.

The kernel consumes only proposition metadata already sealed by the durable
Phase 2.5 readiness gate.  It performs no acquisition, verification, scoring,
credit decision, persistence, provider call, or model invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    InvalidOperation,
    localcontext,
)
from enum import Enum
from itertools import combinations
from uuid import UUID

from .canonical import canonical_json_bytes, normalize_timestamp
from .evidence import (
    EvidenceClass,
    EvidenceReference,
    IndependenceStatus,
    LineageRelation,
    VerificationStatus,
)
from .evidence_boundary import ReasoningReadySnapshot

PHASE3_SCHEMA_VERSION = "investigator-claims-assessment-1"
PHASE3_RULES_VERSION = "investigator-claims-rules-1.0"
MERCHANT_ASSERTION_PROFILE = "merchant_assertion_recorded:v1"
EXTERNAL_ASSERTION_PROFILE = "external_assertion_recorded:v1"
# Explicit reconciliation policy threshold.  It is not a credit-risk threshold.
MATERIAL_RECONCILIATION_GAP_RATIO = Decimal("0.20")
RECONCILIATION_DECIMAL_CONTEXT = Context(
    # Proposition values are capped at 128 characters; 256 digits keeps the
    # threshold multiplication exact without depending on ambient context.
    prec=256,
    rounding=ROUND_HALF_EVEN,
    traps=[],
)


class EpistemicType(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    MERCHANT_CLAIM = "MERCHANT_CLAIM"
    EXTERNAL_CLAIM = "EXTERNAL_CLAIM"
    UNKNOWN = "UNKNOWN"
    CONTRADICTION = "CONTRADICTION"
    POSSIBLE_EXPLANATION = "POSSIBLE_EXPLANATION"


class DimensionalScope(str, Enum):
    BUSINESS_TOTAL = "BUSINESS_TOTAL"
    BANK_VISIBLE = "BANK_VISIBLE"
    UNSPECIFIED = "UNSPECIFIED"


class Materiality(str, Enum):
    RECONCILIATION_GAP_AT_LEAST_20_PERCENT = "RECONCILIATION_GAP_AT_LEAST_20_PERCENT"
    NOT_CLASSIFIED = "NOT_CLASSIFIED"


class Confidence(str, Enum):
    AUTHORITATIVE_PROPOSITION = "AUTHORITATIVE_PROPOSITION"
    CLAIM_ONLY = "CLAIM_ONLY"
    UNRESOLVED = "UNRESOLVED"
    DETERMINISTIC_RULE_MATCH = "DETERMINISTIC_RULE_MATCH"
    HYPOTHETICAL = "HYPOTHETICAL"


@dataclass(frozen=True, slots=True)
class Proposition:
    proposition_type: str
    proposition_schema_version: int
    subject_id: str
    value: str
    unit: str
    period_start: object
    period_end: object
    dimensional_scope: DimensionalScope

    def canonical_record(self) -> dict[str, object]:
        return {
            "dimensional_scope": self.dimensional_scope.value,
            "period_end": normalize_timestamp(self.period_end),
            "period_start": normalize_timestamp(self.period_start),
            "proposition_schema_version": self.proposition_schema_version,
            "proposition_type": self.proposition_type,
            "subject_id": self.subject_id,
            "unit": self.unit,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class Provenance:
    reference_id: UUID
    evidence_namespace: str
    evidence_id: str
    evidence_version: str
    authority_digest: str
    source_id: str
    issuer_id: str
    observed_at: object
    evidence_expires_at: object
    verification_status: VerificationStatus
    confidence: Confidence
    semantic_lineage_id: str
    lineage_relation: LineageRelation
    economic_event_id: str | None
    upstream_issuer_id: str
    independence_status: IndependenceStatus

    def canonical_record(self) -> dict[str, object]:
        return {
            "authority_digest": self.authority_digest,
            "confidence": self.confidence.value,
            "evidence_expires_at": normalize_timestamp(self.evidence_expires_at)
            if self.evidence_expires_at is not None
            else None,
            "evidence_id": self.evidence_id,
            "evidence_namespace": self.evidence_namespace,
            "evidence_version": self.evidence_version,
            "economic_event_id": self.economic_event_id,
            "independence_status": self.independence_status.value,
            "issuer_id": self.issuer_id,
            "lineage_relation": self.lineage_relation.value,
            "observed_at": normalize_timestamp(self.observed_at),
            "reference_id": str(self.reference_id),
            "semantic_lineage_id": self.semantic_lineage_id,
            "source_id": self.source_id,
            "upstream_issuer_id": self.upstream_issuer_id,
            "verification_status": self.verification_status.value,
        }


@dataclass(frozen=True, slots=True)
class VerifiedFact:
    epistemic_type: EpistemicType
    confidence: Confidence
    proposition: Proposition
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return _finding_record(self)


@dataclass(frozen=True, slots=True)
class Claim:
    epistemic_type: EpistemicType
    confidence: Confidence
    asserted_by: str
    assertion_timestamp: object | None
    proposition: Proposition
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        record = _finding_record(self)
        record.update(
            asserted_by=self.asserted_by,
            assertion_timestamp=(
                normalize_timestamp(self.assertion_timestamp)
                if self.assertion_timestamp is not None
                else None
            ),
        )
        return record


@dataclass(frozen=True, slots=True)
class Unknown:
    epistemic_type: EpistemicType
    confidence: Confidence
    question: str
    why_unresolved: str
    evidence_considered: tuple[UUID, ...]
    evidence_missing: tuple[str, ...]
    materiality: Materiality
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "epistemic_type": self.epistemic_type.value,
            "confidence": self.confidence.value,
            "evidence_considered": tuple(
                str(item) for item in self.evidence_considered
            ),
            "evidence_missing": self.evidence_missing,
            "materiality": self.materiality.value,
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "question": self.question,
            "rule_id": self.rule_id,
            "why_unresolved": self.why_unresolved,
        }


@dataclass(frozen=True, slots=True)
class Contradiction:
    epistemic_type: EpistemicType
    confidence: Confidence
    contradiction_type: str
    propositions: tuple[Proposition, ...]
    materiality: Materiality
    materiality_threshold_ratio: str
    materiality_denominator: str
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "contradiction_type": self.contradiction_type,
            "confidence": self.confidence.value,
            "epistemic_type": self.epistemic_type.value,
            "materiality": self.materiality.value,
            "materiality_denominator": self.materiality_denominator,
            "materiality_threshold_ratio": self.materiality_threshold_ratio,
            "propositions": tuple(
                item.canonical_record() for item in self.propositions
            ),
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True, slots=True)
class PossibleExplanation:
    epistemic_type: EpistemicType
    confidence: Confidence
    explanation_family: str
    status: str
    contradiction_rule_id: str
    provenance: tuple[Provenance, ...]
    rule_id: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "contradiction_rule_id": self.contradiction_rule_id,
            "confidence": self.confidence.value,
            "epistemic_type": self.epistemic_type.value,
            "explanation_family": self.explanation_family,
            "provenance": tuple(item.canonical_record() for item in self.provenance),
            "rule_id": self.rule_id,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ClaimsAssessment:
    schema_version: str
    rules_version: str
    tenant_id: UUID
    case_id: UUID
    snapshot_id: UUID
    snapshot_digest: str
    authority_revision: int
    authority_digest: str
    evidence_state_digest: str
    verified_facts: tuple[VerifiedFact, ...]
    claims: tuple[Claim, ...]
    unknowns: tuple[Unknown, ...]
    contradictions: tuple[Contradiction, ...]
    possible_explanations: tuple[PossibleExplanation, ...]

    def canonical_record(self) -> dict[str, object]:
        return {
            "authority_digest": self.authority_digest,
            "authority_revision": self.authority_revision,
            "case_id": str(self.case_id),
            "claims": tuple(item.canonical_record() for item in self.claims),
            "contradictions": tuple(
                item.canonical_record() for item in self.contradictions
            ),
            "evidence_state_digest": self.evidence_state_digest,
            "possible_explanations": tuple(
                item.canonical_record() for item in self.possible_explanations
            ),
            "rules_version": self.rules_version,
            "schema_version": self.schema_version,
            "snapshot_digest": self.snapshot_digest,
            "snapshot_id": str(self.snapshot_id),
            "tenant_id": str(self.tenant_id),
            "unknowns": tuple(item.canonical_record() for item in self.unknowns),
            "verified_facts": tuple(
                item.canonical_record() for item in self.verified_facts
            ),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_record())


def _finding_record(finding: VerifiedFact | Claim) -> dict[str, object]:
    return {
        "confidence": finding.confidence.value,
        "epistemic_type": finding.epistemic_type.value,
        "proposition": finding.proposition.canonical_record(),
        "provenance": tuple(item.canonical_record() for item in finding.provenance),
        "rule_id": finding.rule_id,
    }


def _scope(proposition_type: str) -> DimensionalScope:
    if proposition_type == "monthly_revenue":
        return DimensionalScope.BUSINESS_TOTAL
    if proposition_type == "bank_visible_inflows":
        return DimensionalScope.BANK_VISIBLE
    return DimensionalScope.UNSPECIFIED


def _proposition(reference: EvidenceReference) -> Proposition | None:
    values = (
        reference.proposition_type,
        reference.proposition_schema_version,
        reference.proposition_value,
        reference.proposition_unit,
        reference.period_start,
        reference.period_end,
    )
    if any(value is None for value in values):
        return None
    return Proposition(
        proposition_type=reference.proposition_type,
        proposition_schema_version=reference.proposition_schema_version,
        subject_id=reference.subject_id,
        value=reference.proposition_value,
        unit=reference.proposition_unit,
        period_start=reference.period_start,
        period_end=reference.period_end,
        dimensional_scope=_scope(reference.proposition_type),
    )


def _is_closed_assertion_profile(reference: EvidenceReference) -> bool:
    return bool(
        reference.verification_status is VerificationStatus.UNVERIFIED
        and reference.proposition_schema_version == 1
        and reference.proposition_type
        and reference.proposition_type.strip()
        and reference.proposition_value
        and reference.proposition_value.strip()
        and reference.proposition_unit
        and reference.proposition_unit.strip()
        and reference.period_start is not None
        and reference.period_end is not None
        and reference.issuer_id.strip()
    )


def _provenance(reference: EvidenceReference, confidence: Confidence) -> Provenance:
    return Provenance(
        reference_id=reference.reference_id,
        evidence_namespace=reference.evidence_namespace,
        evidence_id=reference.evidence_id,
        evidence_version=reference.evidence_version,
        authority_digest=reference.authority_digest,
        source_id=reference.source_id,
        issuer_id=reference.issuer_id,
        observed_at=reference.observed_at,
        evidence_expires_at=reference.evidence_expires_at,
        verification_status=reference.verification_status,
        confidence=confidence,
        semantic_lineage_id=reference.semantic_lineage_id,
        lineage_relation=reference.lineage_relation,
        economic_event_id=reference.economic_event_id,
        upstream_issuer_id=reference.upstream_issuer_id,
        independence_status=reference.independence_status,
    )


def _proposition_key(proposition: Proposition) -> tuple[object, ...]:
    return (
        proposition.proposition_type,
        proposition.proposition_schema_version,
        proposition.subject_id,
        proposition.value,
        proposition.unit,
        normalize_timestamp(proposition.period_start),
        normalize_timestamp(proposition.period_end),
        proposition.dimensional_scope.value,
    )


def _ordered_provenance(items: list[Provenance]) -> tuple[Provenance, ...]:
    return tuple(sorted(items, key=lambda item: str(item.reference_id)))


def _decimal(value: str) -> Decimal | None:
    if len(value) > 128:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or abs(parsed.adjusted()) > 18:
        return None
    return parsed


def _compatible_revenue_pair(claim: Claim, fact: VerifiedFact) -> bool:
    return (
        claim.proposition.proposition_type == "monthly_revenue"
        and fact.proposition.proposition_type == "bank_visible_inflows"
        and claim.proposition.proposition_schema_version == 1
        and fact.proposition.proposition_schema_version == 1
        and claim.proposition.subject_id == fact.proposition.subject_id
        and claim.proposition.unit == fact.proposition.unit
        and claim.proposition.period_start == fact.proposition.period_start
        and claim.proposition.period_end == fact.proposition.period_end
    )


def _same_supported_interpretation(first: Proposition, second: Proposition) -> bool:
    return (
        # Bank-visible inflow lacks sealed account-set coverage in Phase 2.5,
        # so separate bank propositions cannot yet be compared as the same scope.
        first.proposition_type == "monthly_revenue"
        and first.proposition_type == second.proposition_type
        and first.proposition_schema_version == 1
        and second.proposition_schema_version == 1
        and first.subject_id == second.subject_id
        and first.unit == second.unit
        and first.period_start == second.period_start
        and first.period_end == second.period_end
        and first.dimensional_scope == second.dimensional_scope
        and first.dimensional_scope is not DimensionalScope.UNSPECIFIED
    )


def _material_numeric_disagreement(first: str, second: str) -> bool:
    first_value = _decimal(first)
    second_value = _decimal(second)
    if first_value is None or second_value is None:
        return False
    try:
        with localcontext(RECONCILIATION_DECIMAL_CONTEXT):
            denominator = max(abs(first_value), abs(second_value))
            if denominator == 0:
                return False
            return abs(first_value - second_value) >= (
                denominator * MATERIAL_RECONCILIATION_GAP_RATIO
            )
    except DecimalException:
        return False


def _has_distinct_original_lineage(
    first: tuple[Provenance, ...], second: tuple[Provenance, ...]
) -> bool:
    first_lineages = {
        item.semantic_lineage_id
        for item in first
        if item.lineage_relation is LineageRelation.ORIGINAL
    }
    second_lineages = {
        item.semantic_lineage_id
        for item in second
        if item.lineage_relation is LineageRelation.ORIGINAL
    }
    return bool(
        first_lineages
        and second_lineages
        and first_lineages.isdisjoint(second_lineages)
    )


def _has_non_circular_lineage(
    first: tuple[Provenance, ...], second: tuple[Provenance, ...]
) -> bool:
    if not _has_distinct_original_lineage(first, second):
        return False
    first_events = {item.economic_event_id for item in first if item.economic_event_id}
    second_events = {
        item.economic_event_id for item in second if item.economic_event_id
    }
    if first_events.intersection(second_events):
        return False
    first_upstreams = {item.upstream_issuer_id for item in first}
    second_upstreams = {item.upstream_issuer_id for item in second}
    return first_upstreams.isdisjoint(second_upstreams)


def assess_claims(ready: ReasoningReadySnapshot) -> ClaimsAssessment:
    """Classify sealed proposition metadata under explicit Phase 3 rules."""
    if not isinstance(ready, ReasoningReadySnapshot):
        raise TypeError("Phase 3 accepts only ReasoningReadySnapshot")
    ready._require_phase3_operation()

    fact_groups: dict[tuple[object, ...], tuple[Proposition, list[Provenance]]] = {}
    claim_groups: dict[
        tuple[object, ...],
        tuple[EpistemicType, str, object, Proposition, list[Provenance]],
    ] = {}
    for reference in sorted(
        ready.evidence_references, key=lambda item: str(item.reference_id)
    ):
        proposition = _proposition(reference)
        if proposition is None:
            continue
        proposition_key = _proposition_key(proposition)
        if (
            reference.evidence_class is EvidenceClass.VERIFIED_FACT
            and reference.verification_status
            is VerificationStatus.VERIFIED_FOR_PROPOSITION
        ):
            group = fact_groups.setdefault(
                proposition_key,
                (proposition, []),
            )
            group[1].append(
                _provenance(reference, Confidence.AUTHORITATIVE_PROPOSITION)
            )
            continue
        if not _is_closed_assertion_profile(reference):
            continue
        claim_type = {
            (
                EvidenceClass.MERCHANT_SUPPLIED_ARTIFACT,
                MERCHANT_ASSERTION_PROFILE,
            ): EpistemicType.MERCHANT_CLAIM,
            (
                EvidenceClass.EXTERNAL_EVIDENCE,
                EXTERNAL_ASSERTION_PROFILE,
            ): EpistemicType.EXTERNAL_CLAIM,
        }.get((reference.evidence_class, reference.verification_method))
        if claim_type is None:
            continue
        key = (claim_type.value, reference.issuer_id, *proposition_key)
        group = claim_groups.setdefault(
            key,
            (
                claim_type,
                reference.issuer_id,
                None,
                proposition,
                [],
            ),
        )
        group[4].append(_provenance(reference, Confidence.CLAIM_ONLY))

    facts = tuple(
        VerifiedFact(
            epistemic_type=EpistemicType.VERIFIED_FACT,
            confidence=Confidence.AUTHORITATIVE_PROPOSITION,
            proposition=proposition,
            provenance=_ordered_provenance(provenance),
            rule_id="P3-FACT-001",
        )
        for _, (proposition, provenance) in sorted(fact_groups.items())
    )
    claims = tuple(
        Claim(
            epistemic_type=claim_type,
            confidence=Confidence.CLAIM_ONLY,
            asserted_by=asserted_by,
            assertion_timestamp=assertion_timestamp,
            proposition=proposition,
            provenance=_ordered_provenance(provenance),
            rule_id="P3-CLAIM-001",
        )
        for _, (
            claim_type,
            asserted_by,
            assertion_timestamp,
            proposition,
            provenance,
        ) in sorted(claim_groups.items())
    )

    unknowns: list[Unknown] = []
    contradictions: list[Contradiction] = []
    explanations: list[PossibleExplanation] = []
    explanation_families = (
        "CASH_REVENUE",
        "SECONDARY_FINANCIAL_ACCOUNT",
        "PAYMENT_PROCESSOR_OR_DELIVERY_PLATFORM",
        "PERIOD_OR_ACCOUNTING_CLASSIFICATION_MISMATCH",
        "MERCHANT_OVERSTATEMENT",
    )
    for claim in claims:
        if claim.epistemic_type is not EpistemicType.MERCHANT_CLAIM:
            continue
        for fact in facts:
            if not (
                _compatible_revenue_pair(claim, fact)
                and _has_non_circular_lineage(claim.provenance, fact.provenance)
            ):
                continue
            claimed = _decimal(claim.proposition.value)
            observed = _decimal(fact.proposition.value)
            if claimed is None or observed is None or claimed <= 0:
                continue
            try:
                with localcontext(RECONCILIATION_DECIMAL_CONTEXT):
                    gap = claimed - observed
                    material = (
                        gap > 0 and gap >= claimed * MATERIAL_RECONCILIATION_GAP_RATIO
                    )
            except DecimalException:
                continue
            if not material:
                continue
            matching_revenue_facts = tuple(
                candidate
                for candidate in facts
                if _proposition_key(candidate.proposition)
                == _proposition_key(claim.proposition)
            )
            provenance = _ordered_provenance(
                list(claim.provenance)
                + list(fact.provenance)
                + [
                    item
                    for candidate in matching_revenue_facts
                    for item in candidate.provenance
                ]
            )
            contradiction = Contradiction(
                epistemic_type=EpistemicType.CONTRADICTION,
                confidence=Confidence.DETERMINISTIC_RULE_MATCH,
                contradiction_type=(
                    "MATERIAL_DISAGREEMENT_DECLARED_REVENUE_EXCEEDS_"
                    "BANK_VISIBLE_INFLOWS"
                ),
                propositions=(claim.proposition, fact.proposition),
                materiality=Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT,
                materiality_threshold_ratio="0.20",
                materiality_denominator="CLAIMED_REVENUE_VALUE",
                provenance=provenance,
                rule_id="P3-CONTRADICTION-REVENUE-001",
            )
            contradictions.append(contradiction)
            unknowns.append(
                Unknown(
                    epistemic_type=EpistemicType.UNKNOWN,
                    confidence=Confidence.UNRESOLVED,
                    question="What reconciles the claimed revenue with bank-visible inflows?",
                    why_unresolved=(
                        "Overall revenue is proposition-specifically verified, but the "
                        "sealed metadata does not attribute the difference to channels "
                        "or account coverage."
                        if matching_revenue_facts
                        else "The sealed evidence verifies bank-visible inflows but does "
                        "not verify the remaining claimed revenue channels or interpretation."
                    ),
                    evidence_considered=tuple(item.reference_id for item in provenance),
                    evidence_missing=(
                        (
                            "authoritative channel and account-coverage reconciliation"
                            if matching_revenue_facts
                            else "authoritative evidence for remaining claimed revenue channels"
                        ),
                        "authoritative reconciliation of scope and classification",
                    ),
                    materiality=(Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT),
                    provenance=provenance,
                    rule_id="P3-UNKNOWN-REVENUE-001",
                )
            )
            explanations.extend(
                PossibleExplanation(
                    epistemic_type=EpistemicType.POSSIBLE_EXPLANATION,
                    confidence=Confidence.HYPOTHETICAL,
                    explanation_family=family,
                    status="HYPOTHESIS",
                    contradiction_rule_id=contradiction.rule_id,
                    provenance=provenance,
                    rule_id="P3-EXPLANATION-REVENUE-001",
                )
                for family in (
                    explanation_families[:-1]
                    if matching_revenue_facts
                    else explanation_families
                )
            )

    same_value_explanations = (
        "REPORTING_OR_CLASSIFICATION_DIFFERENCE",
        "SOURCE_REPORTING_ERROR",
    )
    for claim in claims:
        for fact in facts:
            if not (
                _same_supported_interpretation(claim.proposition, fact.proposition)
                and claim.proposition.value != fact.proposition.value
                and _material_numeric_disagreement(
                    claim.proposition.value, fact.proposition.value
                )
                and _has_distinct_original_lineage(claim.provenance, fact.provenance)
            ):
                continue
            provenance = _ordered_provenance(
                list(claim.provenance) + list(fact.provenance)
            )
            contradiction = Contradiction(
                epistemic_type=EpistemicType.CONTRADICTION,
                confidence=Confidence.DETERMINISTIC_RULE_MATCH,
                contradiction_type="MATERIAL_DISAGREEMENT_SAME_PROPOSITION",
                propositions=(claim.proposition, fact.proposition),
                materiality=Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT,
                materiality_threshold_ratio="0.20",
                materiality_denominator="MAX_ABSOLUTE_COMPARED_VALUE",
                provenance=provenance,
                rule_id="P3-CONTRADICTION-SAME-PROPOSITION-001",
            )
            contradictions.append(contradiction)
            unknowns.append(
                Unknown(
                    epistemic_type=EpistemicType.UNKNOWN,
                    confidence=Confidence.UNRESOLVED,
                    question="Which reported value for the proposition is correct?",
                    why_unresolved=(
                        "Compatible sealed proposition metadata contains materially "
                        "different values from distinct original lineages."
                    ),
                    evidence_considered=tuple(item.reference_id for item in provenance),
                    evidence_missing=(
                        "authoritative reconciliation of the conflicting values",
                    ),
                    materiality=(Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT),
                    provenance=provenance,
                    rule_id="P3-UNKNOWN-SAME-PROPOSITION-001",
                )
            )
            explanations.extend(
                PossibleExplanation(
                    epistemic_type=EpistemicType.POSSIBLE_EXPLANATION,
                    confidence=Confidence.HYPOTHETICAL,
                    explanation_family=family,
                    status="HYPOTHESIS",
                    contradiction_rule_id=contradiction.rule_id,
                    provenance=provenance,
                    rule_id="P3-EXPLANATION-SAME-PROPOSITION-001",
                )
                for family in same_value_explanations
            )

    for first, second in combinations(facts, 2):
        if not (
            _same_supported_interpretation(first.proposition, second.proposition)
            and first.proposition.value != second.proposition.value
            and _material_numeric_disagreement(
                first.proposition.value, second.proposition.value
            )
            and _has_distinct_original_lineage(first.provenance, second.provenance)
        ):
            continue
        provenance = _ordered_provenance(
            list(first.provenance) + list(second.provenance)
        )
        contradiction = Contradiction(
            epistemic_type=EpistemicType.CONTRADICTION,
            confidence=Confidence.DETERMINISTIC_RULE_MATCH,
            contradiction_type="MATERIAL_DISAGREEMENT_SAME_VERIFIED_PROPOSITION",
            propositions=(first.proposition, second.proposition),
            materiality=Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT,
            materiality_threshold_ratio="0.20",
            materiality_denominator="MAX_ABSOLUTE_COMPARED_VALUE",
            provenance=provenance,
            rule_id="P3-CONTRADICTION-VERIFIED-PROPOSITION-001",
        )
        contradictions.append(contradiction)
        unknowns.append(
            Unknown(
                epistemic_type=EpistemicType.UNKNOWN,
                confidence=Confidence.UNRESOLVED,
                question="Which verified proposition value is current and correct?",
                why_unresolved=(
                    "Distinct original authoritative lineages materially disagree "
                    "under the same supported interpretation."
                ),
                evidence_considered=tuple(item.reference_id for item in provenance),
                evidence_missing=(
                    "authoritative reconciliation or superseding correction",
                ),
                materiality=Materiality.RECONCILIATION_GAP_AT_LEAST_20_PERCENT,
                provenance=provenance,
                rule_id="P3-UNKNOWN-VERIFIED-PROPOSITION-001",
            )
        )
        explanations.extend(
            PossibleExplanation(
                epistemic_type=EpistemicType.POSSIBLE_EXPLANATION,
                confidence=Confidence.HYPOTHETICAL,
                explanation_family=family,
                status="HYPOTHESIS",
                contradiction_rule_id=contradiction.rule_id,
                provenance=provenance,
                rule_id="P3-EXPLANATION-VERIFIED-PROPOSITION-001",
            )
            for family in same_value_explanations
        )

    contradicted_claim_references = {
        provenance.reference_id
        for contradiction in contradictions
        for provenance in contradiction.provenance
        if provenance.confidence is Confidence.CLAIM_ONLY
    }
    for claim in claims:
        claim_reference_ids = tuple(
            provenance.reference_id for provenance in claim.provenance
        )
        if any(
            reference_id in contradicted_claim_references
            for reference_id in claim_reference_ids
        ):
            continue
        exact_fact_exists = any(
            _proposition_key(fact.proposition) == _proposition_key(claim.proposition)
            for fact in facts
        )
        if exact_fact_exists:
            continue
        unknowns.append(
            Unknown(
                epistemic_type=EpistemicType.UNKNOWN,
                confidence=Confidence.UNRESOLVED,
                question=(
                    "Is the asserted proposition established by authoritative "
                    "proposition-specific evidence?"
                ),
                why_unresolved=(
                    "The sealed evidence contains the assertion but no matching "
                    "authoritative proposition-specific verification."
                ),
                evidence_considered=claim_reference_ids,
                evidence_missing=(
                    "matching authoritative proposition-specific verification",
                ),
                materiality=Materiality.NOT_CLASSIFIED,
                provenance=claim.provenance,
                rule_id="P3-UNKNOWN-CLAIM-001",
            )
        )

    unknown_tuple = tuple(sorted(unknowns, key=lambda item: item.evidence_considered))
    contradiction_tuple = tuple(
        sorted(
            contradictions,
            key=lambda item: tuple(
                str(provenance.reference_id) for provenance in item.provenance
            ),
        )
    )
    explanation_tuple = tuple(
        sorted(
            explanations,
            key=lambda item: (
                item.contradiction_rule_id,
                item.explanation_family,
                tuple(str(value.reference_id) for value in item.provenance),
            ),
        )
    )
    return ClaimsAssessment(
        schema_version=PHASE3_SCHEMA_VERSION,
        rules_version=PHASE3_RULES_VERSION,
        tenant_id=ready.tenant_id,
        case_id=ready.case_id,
        snapshot_id=ready.snapshot_id,
        snapshot_digest=ready.snapshot_digest,
        authority_revision=ready.authority_revision,
        authority_digest=ready.authority_state_digest,
        evidence_state_digest=ready.evidence_state_digest,
        verified_facts=facts,
        claims=claims,
        unknowns=unknown_tuple,
        contradictions=contradiction_tuple,
        possible_explanations=explanation_tuple,
    )


__all__ = [
    "EXTERNAL_ASSERTION_PROFILE",
    "MERCHANT_ASSERTION_PROFILE",
    "PHASE3_RULES_VERSION",
    "PHASE3_SCHEMA_VERSION",
    "Claim",
    "ClaimsAssessment",
    "Confidence",
    "Contradiction",
    "DimensionalScope",
    "EpistemicType",
    "Materiality",
    "PossibleExplanation",
    "Proposition",
    "Provenance",
    "Unknown",
    "VerifiedFact",
]
