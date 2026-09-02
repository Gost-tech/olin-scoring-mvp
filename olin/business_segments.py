"""Conservative evidence policies for heterogeneous small businesses.

This module does not claim that one scorecard is calibrated for every sector.
It maps each supported business type to the cash-flow evidence a reviewer should
seek and keeps uncalibrated sectors in bank/committee review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import BusinessType
from .config import validated_auto_approve_types


@dataclass(frozen=True)
class SegmentPolicy:
    segment_id: str
    label: str
    business_types: tuple[BusinessType, ...]
    cash_flow_pattern: str
    primary_evidence: tuple[str, ...]
    secondary_evidence: tuple[str, ...]
    key_risks: tuple[str, ...]
    operating_metrics: tuple[str, ...]
    stress_factors: tuple[str, ...]
    policy_status: str = "committee_only_until_calibrated"


POLICIES = (
    SegmentPolicy(
        "pharmacy_inventory", "Community and specialist pharmacies",
        (BusinessType.PHARMACY,),
        "Regulated inventory retail with repeat demand, expiry, stockout and supplier risks",
        ("bank_cash_flow", "supplier_purchases", "regulatory_status"),
        ("pos_settlements", "geo_continuity", "credit_bureau"),
        ("expiry_losses", "stockouts", "supplier_concentration", "regulated_product_compliance"),
        ("inventory_days", "gross_margin", "expiry_writeoffs", "stockout_rate"),
        ("supplier_disruption", "margin_compression", "expiry_shock"),
    ),
    SegmentPolicy(
        "inventory_retail", "Inventory retail and wholesale",
        (BusinessType.ABARROTES, BusinessType.RETAIL, BusinessType.WHOLESALE),
        "Frequent stock purchases converted into daily or weekly sales",
        ("supplier_purchases", "bank_cash_flow"),
        ("pos_settlements", "geo_continuity"),
        ("inventory_turnover", "supplier_concentration", "cash_sales_visibility"),
        ("inventory_turnover", "gross_margin", "supplier_concentration", "cash_sales_share"),
        ("supplier_price_increase", "sales_decline", "inventory_obsolescence"),
    ),
    SegmentPolicy(
        "food_hospitality", "Food service and hospitality",
        (BusinessType.JUGUERIA, BusinessType.TAQUERIA, BusinessType.RESTAURANT,
         BusinessType.HOSPITALITY),
        "High-frequency sales with seasonality and spoilage or occupancy risk",
        ("pos_settlements", "bank_cash_flow"),
        ("supplier_purchases", "geo_continuity"),
        ("seasonality", "spoilage_or_occupancy", "platform_concentration"),
        ("daily_sales", "food_cost_or_occupancy", "ticket_size", "platform_share"),
        ("sales_decline", "input_cost_increase", "seasonal_trough"),
    ),
    SegmentPolicy(
        "recurring_services", "Recurring local services",
        (BusinessType.SERVICES, BusinessType.HEALTH_BEAUTY,
         BusinessType.EDUCATION, BusinessType.HEALTHCARE),
        "Appointments, subscriptions, or repeat customer receipts",
        ("bank_cash_flow", "pos_settlements"),
        ("geo_continuity", "credit_bureau"),
        ("customer_concentration", "professional_dependency", "seasonality"),
        ("repeat_revenue_share", "customer_concentration", "gross_margin", "cancellations"),
        ("customer_loss", "utilization_decline", "owner_unavailability"),
    ),
    SegmentPolicy(
        "professional_project", "Professional and project businesses",
        (BusinessType.PROFESSIONAL, BusinessType.CONSTRUCTION),
        "Milestone or invoice-based collections with uneven working-capital needs",
        ("bank_cash_flow", "identity_consent"),
        ("credit_bureau", "geo_continuity"),
        ("project_concentration", "collection_delay", "cost_overrun"),
        ("contracted_backlog", "receivable_days", "project_margin", "largest_project_share"),
        ("payment_delay", "cost_overrun", "project_cancellation"),
    ),
    SegmentPolicy(
        "asset_route", "Transport and logistics",
        (BusinessType.TRANSPORT, BusinessType.LOGISTICS),
        "Route or contract revenue constrained by asset uptime and fuel cost",
        ("bank_cash_flow", "identity_consent"),
        ("credit_bureau", "geo_continuity"),
        ("asset_downtime", "fuel_volatility", "contract_concentration"),
        ("route_revenue", "asset_utilization", "fuel_share", "maintenance_cost"),
        ("fuel_increase", "asset_downtime", "contract_loss"),
    ),
    SegmentPolicy(
        "production_agri", "Manufacturing and agriculture",
        (BusinessType.LIGHT_MANUFACTURING, BusinessType.AGRICULTURE),
        "Production-cycle receipts with input, yield, and seasonal timing risk",
        ("bank_cash_flow", "supplier_purchases"),
        ("credit_bureau", "geo_continuity"),
        ("input_cost", "yield_or_production", "seasonality"),
        ("production_volume", "unit_margin", "input_cost_share", "cycle_length"),
        ("input_cost_increase", "yield_decline", "collection_delay"),
    ),
    SegmentPolicy(
        "digital_commerce", "Digital commerce",
        (BusinessType.ECOMMERCE,),
        "Platform settlements net of refunds, fees, and advertising spend",
        ("pos_settlements", "bank_cash_flow"),
        ("identity_consent", "credit_bureau"),
        ("platform_concentration", "returns", "paid_acquisition_dependency"),
        ("net_settlements", "refund_rate", "platform_share", "advertising_share"),
        ("platform_suspension", "refund_increase", "acquisition_cost_increase"),
    ),
    SegmentPolicy(
        "manual_other", "Other or not yet classified",
        (BusinessType.OTHER,),
        "Unknown until the bank records a business model and repayment source",
        ("bank_cash_flow", "identity_consent"),
        ("credit_bureau", "geo_continuity"),
        ("unclassified_business_model", "unverified_repayment_source"),
        ("verified_revenue", "verified_costs", "customer_concentration", "cash_conversion_cycle"),
        ("bank_defined_downside", "revenue_interruption"),
    ),
)

_BY_TYPE = {
    business_type: policy
    for policy in POLICIES
    for business_type in policy.business_types
}


def assess_business_policy(
    business_type: str | BusinessType,
    evidence_layers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a transparent evidence plan, never an official credit decision."""
    normalized = (
        business_type if isinstance(business_type, BusinessType)
        else BusinessType(str(business_type or "other").lower())
    )
    policy = _BY_TYPE[normalized]
    states = {str(item.get("key")): str(item.get("status")) for item in evidence_layers}
    required = policy.primary_evidence
    missing_primary = [key for key in required if states.get(key) != "verified"]
    auto_eligible = normalized.value in validated_auto_approve_types()
    return {
        "business_type": normalized.value,
        "segment_id": policy.segment_id,
        "segment_label": policy.label,
        "cash_flow_pattern": policy.cash_flow_pattern,
        "primary_evidence": list(policy.primary_evidence),
        "secondary_evidence": list(policy.secondary_evidence),
        "missing_primary_evidence": missing_primary,
        "key_risks_to_review": list(policy.key_risks),
        "required_operating_metrics": list(policy.operating_metrics),
        "required_stress_factors": list(policy.stress_factors),
        "policy_status": "pilot_auto_eligible" if auto_eligible else policy.policy_status,
        "routing": (
            "scorecard_route_subject_to_all_safety_gates"
            if auto_eligible and not missing_primary
            else "bank_committee_review"
        ),
        "calibration_note": (
            "No business type is auto-eligible by default. Model risk must add a type to "
            "OLIN_VALIDATED_AUTO_APPROVE_TYPES only after approved outcome validation."
        ),
    }


def unmapped_business_types() -> set[BusinessType]:
    """Expose a testable completeness invariant for future enum additions."""
    return set(BusinessType) - set(_BY_TYPE)


def operating_metrics_for(business_type: str | BusinessType) -> tuple[str, ...]:
    normalized = (
        business_type if isinstance(business_type, BusinessType)
        else BusinessType(str(business_type).lower())
    )
    return _BY_TYPE[normalized].operating_metrics


def business_policy_catalog() -> list[dict[str, Any]]:
    """Return one bank-integration contract for every supported business type."""
    return [
        assess_business_policy(
            business_type,
            [{"key": key, "status": "missing"} for key in _BY_TYPE[business_type].primary_evidence],
        )
        for business_type in BusinessType
    ]
