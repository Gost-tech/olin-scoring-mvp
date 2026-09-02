"""Transparent repayment-capacity calculation for bank shadow decisions."""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from .models import Application
from .source_trust import assess_source

VERSION = "capacity-2.0.0"


def _payment(principal: float, rate: float, months: int) -> float:
    if principal <= 0:
        return 0.0
    if rate == 0:
        return principal / months
    factor = (rate * (1 + rate) ** months) / ((1 + rate) ** months - 1)
    return principal * factor


def _principal(payment: float, rate: float, months: int) -> float:
    if payment <= 0:
        return 0.0
    if rate == 0:
        return payment * months
    return payment * ((1 + rate) ** months - 1) / (rate * (1 + rate) ** months)


def calculate_capacity(application: Application) -> dict[str, Any]:
    features = application.bank_features_v2
    terms = application.facility
    if features is None:
        return {
            "version": VERSION,
            "status": "insufficient_data",
            "proposed_amount_mxn": None,
            "blocks": ["bank_feature_contract_v2_missing"],
            "limitations": ["No capacity recommendation is produced from aggregate legacy bank fields."],
        }

    trust = assess_source(features.source, "bank_feature_contract_v2")
    blocks: list[str] = []
    if features.contract_version != "bank-feature-contract-2.0":
        blocks.append("unsupported_contract_version")
    if features.normalization_basis != "monthly_average":
        blocks.append("unsupported_normalization_basis")
    if features.currency != "MXN":
        blocks.append("currency_must_be_mxn")
    if features.account_coverage_ratio < 0.90:
        blocks.append("account_coverage_below_90_percent")
    if features.classification_coverage_ratio < 0.90:
        blocks.append("transaction_classification_below_90_percent")
    if not features.account_holder_match:
        blocks.append("account_holder_mismatch")
    if not trust.trusted:
        blocks.append(f"untrusted_source:{trust.reason}")

    debt_service = max(
        terms.existing_monthly_debt_service_mxn,
        features.existing_monthly_debt_service_mxn,
    )
    base_cash = features.operating_inflows_mxn - features.operating_outflows_mxn - debt_service
    stress_cash = (
        features.operating_inflows_mxn * (1 - terms.revenue_stress_pct)
        - features.operating_outflows_mxn * (1 + terms.cost_stress_pct)
        - debt_service
    )
    requested_payment = _payment(
        application.requested_amount_mxn, terms.monthly_rate, terms.term_months
    )
    base_dscr = base_cash / requested_payment if requested_payment else None
    stress_dscr = stress_cash / requested_payment if requested_payment else None
    max_new_payment = max(0.0, stress_cash / terms.target_dscr)
    capacity_principal = _principal(max_new_payment, terms.monthly_rate, terms.term_months)
    amount_evaluated = min(application.requested_amount_mxn, terms.policy_max_amount_mxn)
    proposed = min(amount_evaluated, capacity_principal)
    proposed = math.floor(max(0.0, proposed) / 1000) * 1000
    if blocks:
        proposed_output = None
        status = "manual_review_required"
    else:
        proposed_output = proposed
        status = "capacity_supported" if proposed > 0 else "no_demonstrated_capacity"

    reasons = []
    if application.requested_amount_mxn > terms.policy_max_amount_mxn:
        reasons.append("requested_amount_exceeds_policy_ceiling")
    if proposed < amount_evaluated:
        reasons.append("stress_adjusted_cash_flow_limits_principal")
    if proposed == amount_evaluated and not blocks:
        reasons.append("requested_evaluated_amount_supported_under_stress")
    return {
        "version": VERSION,
        "status": status,
        "requested_amount_mxn": round(application.requested_amount_mxn, 2),
        "amount_evaluated_mxn": round(amount_evaluated, 2),
        "proposed_amount_mxn": proposed_output,
        "policy_ceiling_mxn": round(terms.policy_max_amount_mxn, 2),
        "term_months": terms.term_months,
        "monthly_rate": terms.monthly_rate,
        "target_dscr": terms.target_dscr,
        "existing_monthly_debt_service_mxn": round(debt_service, 2),
        "normalized_monthly_cash_flow_mxn": round(base_cash, 2),
        "stressed_monthly_cash_flow_mxn": round(stress_cash, 2),
        "requested_payment_mxn": round(requested_payment, 2),
        "base_dscr": round(base_dscr, 3) if base_dscr is not None else None,
        "stress_dscr": round(stress_dscr, 3) if stress_dscr is not None else None,
        "stress_scenario": {
            "revenue_decline_pct": terms.revenue_stress_pct,
            "cost_increase_pct": terms.cost_stress_pct,
        },
        "source_trust": trust.to_dict(),
        "blocks": blocks,
        "amount_rationale": reasons,
        "input_contract": asdict(features),
    }
