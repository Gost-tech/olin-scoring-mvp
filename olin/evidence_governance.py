"""Bank-facing permitted-use policy for Olin alternative evidence.

This module does not decide credit.  It prevents experimental or contextual
signals from drifting into a partner policy merely because an observation is
present.  The bank remains the decision owner and must approve any shadow
policy before an eligible signal is used in a pilot.
"""
from __future__ import annotations

from collections import Counter
from typing import Final


GOVERNANCE_VERSION: Final = "evidence-governance-1.0.0"

CAPACITY_EVIDENCE: Final = "candidate_capacity_evidence"
CORROBORATING_EVIDENCE: Final = "corroborating_evidence"
CONTEXT_ONLY: Final = "context_or_stress_only"
RESEARCH_ONLY: Final = "research_only"

PERMITTED_USES: Final = {
    CAPACITY_EVIDENCE: (
        "shadow_capacity_review",
        "analyst_evidence",
        "missing_document_alternative",
    ),
    CORROBORATING_EVIDENCE: (
        "identity_or_permanence_corroboration",
        "analyst_evidence",
    ),
    CONTEXT_ONLY: (
        "portfolio_context",
        "sector_stress_scenario",
        "analyst_context",
    ),
    RESEARCH_ONLY: (
        "offline_research",
        "fairness_and_outcome_validation",
    ),
}

_CAPACITY_SIGNALS: Final = frozenset({
    "fmcg_purchase_volume",
    "fmcg_cadence",
    "fmcg_supplier_diversity",
    "bank_cash_flow_snapshot",
    "bank_flow_90d_trend",
    "pos_transaction_volume",
    "codi_dimo_frequency",
    "oxxo_pay_deposit_frequency",
    "spei_inbound_regularity",
})

_CORROBORATING_SIGNALS: Final = frozenset({
    "business_age_category_risk",
    "google_maps_activity",
    "hours_consistency",
    "whatsapp_business_verification",
    "onboarding_consistency",
    "imss_payroll_trajectory",
})

_CONTEXT_SIGNALS: Final = frozenset({
    "zone_commerce_density",
    "foot_traffic_delta",
    "neighborhood_permanence",
    "night_time_light_trend",
    "neighborhood_closure_rate",
    "commercial_neighbor_ecosystem",
    "weather_risk",
    "fmcg_inflation_proxy",
    "seasonal_adjustment",
})

_RESEARCH_SIGNALS: Final = frozenset({
    "psychometric_conscientiousness",
    "psychometric_integrity",
    "whatsapp_response_time",
    "onboarding_message_timing",
})

SIGNAL_CLASS: Final = {
    **{signal_id: CAPACITY_EVIDENCE for signal_id in _CAPACITY_SIGNALS},
    **{signal_id: CORROBORATING_EVIDENCE for signal_id in _CORROBORATING_SIGNALS},
    **{signal_id: CONTEXT_ONLY for signal_id in _CONTEXT_SIGNALS},
    **{signal_id: RESEARCH_ONLY for signal_id in _RESEARCH_SIGNALS},
}


def evidence_governance(
    signal_id: str,
    *,
    verified: bool = False,
    evidence_reference: str = "",
) -> dict:
    """Return the immutable permitted-use envelope for one signal."""
    try:
        evidence_class = SIGNAL_CLASS[signal_id]
    except KeyError as exc:
        raise ValueError(f"Unknown governed signal: {signal_id}") from exc

    blocking_reasons: list[str] = []
    if evidence_class != CAPACITY_EVIDENCE:
        blocking_reasons.append("class_not_permitted_in_credit_policy")
    if not verified:
        blocking_reasons.append("verified_provider_or_bank_evidence_required")
    if not str(evidence_reference or "").strip():
        blocking_reasons.append("retrievable_evidence_reference_required")

    return {
        "governanceVersion": GOVERNANCE_VERSION,
        "evidenceClass": evidence_class,
        "permittedUses": list(PERMITTED_USES[evidence_class]),
        "eligibleForShadowPolicy": not blocking_reasons,
        "mayAutoDecide": False,
        "mayBeSoleDeclineReason": False,
        "bankPolicyApprovalRequired": True,
        "blockingReasons": blocking_reasons,
    }


def governance_summary() -> dict:
    """Describe coverage without exposing applicant or provider data."""
    counts = Counter(SIGNAL_CLASS.values())
    return {
        "governanceVersion": GOVERNANCE_VERSION,
        "signalCount": len(SIGNAL_CLASS),
        "classCounts": dict(sorted(counts.items())),
        "invariants": [
            "No alternative signal may auto-approve, auto-decline, or move money",
            "Only verified, referenced capacity evidence can enter a bank-approved shadow policy",
            "Context and research signals cannot be a sole adverse reason",
            "Missing optional evidence is neutral and routes to a next-best evidence path",
        ],
    }
