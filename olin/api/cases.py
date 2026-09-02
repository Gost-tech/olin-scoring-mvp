"""Canonical case application service for the Olin shadow MVP."""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ..config import is_production, is_synthetic_source
from ..config import validated_auto_approve_types
from ..business_segments import assess_business_policy, operating_metrics_for
from ..graduation import get_graduation_offer
from ..models import (
    Application,
    BankData,
    BankFeatureContractV2,
    BuroData,
    BusinessType,
    Decision,
    FMCGData,
    FraudData,
    ExternalSignalEvidence,
    IMSSPayrollData,
    MapsRatingData,
    FacilityTerms,
    PharmacyData,
    OperatingProfile,
    POSData,
    TenureData,
)
from ..signal_architecture import BY_ID, SIGNAL_IDS
from ..portfolio import check_portfolio
from ..scorecard import score_application
from ..store import ScoringLog, connect_database
from ..capacity_v2 import calculate_capacity
from ..enrichment import build_enrichment_report
from ..source_trust import assess_source
from ..production_storage import assert_real_data_storage_ready

FUNDING_PURPOSES = frozenset(
    {
        "working_capital",
        "inventory",
        "equipment",
        "expansion",
        "renovation",
        "technology",
    }
)
EVIDENCE_ROUTES = frozenset(
    {"inventory_led", "tpv_led", "bank_flow_led", "hybrid"}
)


def evidence_layers(
    application: dict[str, Any],
    *,
    consent_recorded: bool = False,
) -> list[dict[str, Any]]:
    """Describe evidence layers without changing score weights.

    ``verified`` means the dossier contains both a provider/manual verification
    state and a retrievable reference.  ``available`` is useful evidence that
    still needs verification.  These labels are intentionally independent of
    the credit recommendation.
    """
    fraud = application.get("fraud") or {}
    bureau = application.get("buro") or {}
    bank = application.get("bank") or {}
    pos = application.get("pos") or {}
    supplier = application.get("fmcg") or {}
    maps = application.get("maps") or {}
    tenure = application.get("tenure") or {}
    pharmacy = application.get("pharmacy") or {}

    def referenced(block: dict[str, Any]) -> bool:
        return bool(block.get("verified") and str(block.get("evidence_reference", "")).strip())

    identity_ready = bool(
        consent_recorded
        and fraud.get("ine_checked")
        and str(fraud.get("rfc", "")).strip()
    )
    google_ready = bool(
        maps.get("verified")
        and maps.get("source") == "google_places"
        and str(maps.get("evidence_reference", "")).strip()
        and tenure.get("address_consistent") is True
    )
    denue_ready = bool(
        maps.get("denue_verified")
        and str(maps.get("denue_id", "")).strip()
        and tenure.get("address_consistent") is True
    )
    geo_ready = google_ready or denue_ready
    geo_reference = " | ".join(filter(None, (
        str(maps.get("evidence_reference", "")).strip(),
        f"denue:{maps.get('denue_id')}" if maps.get("denue_id") else "",
    )))
    definitions = [
        ("identity_consent", "Identidad y consentimiento", identity_ready,
         bool(consent_recorded or fraud), "manual_control",
         "case-consent+manual-ine" if identity_ready else ""),
        ("credit_bureau", "Círculo de Crédito",
         bool(bureau.get("checked") and bureau.get("verified")
              and str(bureau.get("evidence_reference", "")).strip()),
         bool(bureau), bureau.get("source", "missing"),
         bureau.get("evidence_reference", "")),
        ("bank_cash_flow", "Flujo bancario", referenced(bank), bool(bank),
         bank.get("source", "missing"), bank.get("evidence_reference", "")),
        ("pos_settlements", "Ventas y liquidaciones TPV", referenced(pos), bool(pos),
         pos.get("source", "missing"), pos.get("evidence_reference", "")),
        ("supplier_purchases", "Compras a proveedores", referenced(supplier), bool(supplier),
         supplier.get("source", "missing"), supplier.get("evidence_reference", "")),
        ("geo_continuity", "Presencia y continuidad geográfica", geo_ready,
         bool(maps or tenure),
         "google_places+inegi_denue" if google_ready and denue_ready else (
             "inegi_denue" if denue_ready else maps.get("source", "missing")
         ), geo_reference),
    ]
    if application.get("business_type") in {"pharmacy", BusinessType.PHARMACY}:
        regulatory_required = bool(pharmacy.get("sells_controlled_medicines"))
        regulatory_trust = assess_source(
            str(pharmacy.get("source", "")), "pharmacy_evidence"
        )
        regulatory_verified = bool(
            regulatory_trust.trusted
            and ((not regulatory_required and pharmacy.get("license_status") == "not_required")
            or (
                regulatory_required
                and pharmacy.get("license_status") == "active"
                and pharmacy.get("license_reference")
            ))
        )
        definitions.append((
            "regulatory_status", "Estatus regulatorio de farmacia",
            regulatory_verified, bool(pharmacy), pharmacy.get("source", "missing"),
            pharmacy.get("license_reference", ""),
        ))
    layers: list[dict[str, Any]] = []
    for key, label, verified, available, source, reference in definitions:
        status = "verified" if verified else ("available" if available else "missing")
        evidence_type = {
            "credit_bureau": "credit_bureau",
            "bank_cash_flow": "legacy_bank_cash_flow",
            "pos_settlements": "pos_settlements",
            "supplier_purchases": "supplier_purchases",
            "geo_continuity": "geo_continuity",
            "regulatory_status": "pharmacy_evidence",
        }.get(key, "manual_control")
        trust = (
            {"trusted": bool(verified), "reason": "internal_manual_control"}
            if evidence_type == "manual_control"
            else assess_source(str(source or ""), evidence_type).to_dict()
        )
        layers.append({
            "key": key,
            "label": label,
            "status": status,
            "source": str(source or "missing"),
            "evidence_reference": str(reference or ""),
            "verification_basis": "registry_attested" if trust.get("trusted") else "partner_asserted_or_untrusted",
            "independently_trusted": bool(trust.get("trusted")),
            "trust_reason": trust.get("reason", ""),
        })
    return layers


def _has_verified_reference(body: dict[str, Any], source: str) -> bool:
    block = body.get(source) or {}
    return (
        isinstance(block, dict)
        and block.get("verified") is True
        and bool(str(block.get("evidence_reference", "")).strip())
    )


def _validate_evidence_route(body: dict[str, Any], route: str) -> None:
    """Make the selected evidence route an enforceable control, not a label."""
    verified = {
        source: _has_verified_reference(body, source)
        for source in ("bank", "fmcg", "pos")
    }
    required = {
        "inventory_led": "fmcg",
        "tpv_led": "pos",
        "bank_flow_led": "bank",
    }
    if route in required and not verified[required[route]]:
        source = required[route]
        raise ValueError(
            f"{route} requires verified {source} evidence and an "
            "evidence_reference"
        )
    if route == "hybrid" and sum(verified.values()) < 2:
        raise ValueError(
            "hybrid requires at least two verified evidence sources with "
            "evidence_reference values"
        )


def build_application(body: dict[str, Any]) -> Application:
    """Validate an authenticated partner payload and build an application."""
    merchant_name = str(body["merchant_name"]).strip()
    if not merchant_name:
        raise ValueError("merchant_name is required")
    try:
        business_type = BusinessType(str(body["business_type"]).lower())
    except ValueError as exc:
        valid = [item.value for item in BusinessType]
        raise ValueError(f"business_type must be one of {valid}") from exc

    requested = float(body["requested_mxn"])

    def sub(key: str) -> dict[str, Any]:
        value = body.get(key) or {}
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a JSON object")
        return value

    def boolean(block: dict[str, Any], key: str, default: bool = False) -> bool:
        value = block.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a JSON boolean")
        return value

    def number_range(
        name: str,
        value: float,
        minimum: float,
        maximum: float | None = None,
    ) -> None:
        if not math.isfinite(float(value)) or value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{name} must be <= {maximum}")

    def finite(name: str, value: float) -> None:
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number")

    number_range("requested_mxn", requested, 1_000, 80_000)

    bank_raw = sub("bank")
    bank = BankData(
        months_connected=float(bank_raw.get("months_connected", 0)),
        avg_daily_balance_mxn=float(bank_raw.get("avg_daily_balance_mxn", 0)),
        monthly_deposit_count=float(bank_raw.get("monthly_deposit_count", 0)),
        monthly_deposit_volume_mxn=float(
            bank_raw.get("monthly_deposit_volume_mxn", 0)
        ),
        monthly_outflow_volume_mxn=float(
            bank_raw.get("monthly_outflow_volume_mxn", 0)
        ),
        deposit_regularity=float(bank_raw.get("deposit_regularity", 0)),
        overdrafts_90d=int(bank_raw.get("overdrafts_90d", 0)),
        balance_trend_90d=float(bank_raw.get("balance_trend_90d", 0)),
        min_daily_balance_mxn=float(bank_raw.get("min_daily_balance_mxn", 0)),
        source=str(bank_raw.get("source", "api")),
        verified=boolean(bank_raw, "verified"),
        evidence_reference=str(bank_raw.get("evidence_reference", "")),
        observed_at=str(bank_raw.get("observed_at", "")),
    ) if bank_raw else None

    fmcg_raw = sub("fmcg")
    fmcg = FMCGData(
        months_of_history=float(fmcg_raw.get("months_of_history", 0)),
        weekly_purchase_rate=float(fmcg_raw.get("weekly_purchase_rate", 0)),
        missed_weeks_last_12=int(fmcg_raw.get("missed_weeks_last_12", 0)),
        avg_weekly_purchase_mxn=float(
            fmcg_raw.get("avg_weekly_purchase_mxn", 0)
        ),
        distributor_confirmed=boolean(fmcg_raw, "distributor_confirmed"),
        trend_3m=float(fmcg_raw.get("trend_3m", 0)),
        source=str(fmcg_raw.get("source", "api")),
        verified=boolean(fmcg_raw, "verified"),
        evidence_reference=str(fmcg_raw.get("evidence_reference", "")),
        observed_at=str(fmcg_raw.get("observed_at", "")),
    ) if fmcg_raw else None

    tenure_raw = sub("tenure")
    tenure = TenureData(
        years_on_google_maps=float(tenure_raw.get("years_on_google_maps", 0)),
        years_in_imss=float(tenure_raw.get("years_in_imss", 0)),
        address_consistent=boolean(tenure_raw, "address_consistent", True),
    ) if tenure_raw else None

    pos_raw = sub("pos")
    pos = POSData(
        months_of_history=float(pos_raw.get("months_of_history", 0)),
        avg_monthly_volume_mxn=float(pos_raw.get("avg_monthly_volume_mxn", 0)),
        volume_consistency=float(pos_raw.get("volume_consistency", 0)),
        trend_3m=float(pos_raw.get("trend_3m", 0)),
        source=str(pos_raw.get("source", "api")),
        verified=boolean(pos_raw, "verified"),
        evidence_reference=str(pos_raw.get("evidence_reference", "")),
        observed_at=str(pos_raw.get("observed_at", "")),
    ) if pos_raw else None

    maps_raw = sub("maps")
    maps = MapsRatingData(
        rating=float(maps_raw.get("rating", 0)),
        review_count=int(maps_raw.get("review_count", 0)),
        review_velocity_6m=int(maps_raw.get("review_velocity_6m", 0)),
        source=str(maps_raw.get("source", "unknown")),
        verified=boolean(maps_raw, "verified"),
        evidence_reference=str(maps_raw.get("evidence_reference", "")),
        observed_at=str(maps_raw.get("observed_at", "")),
        display_name=str(maps_raw.get("display_name", "")),
        formatted_address=str(maps_raw.get("formatted_address", "")),
        business_status=str(maps_raw.get("business_status", "")),
        primary_type=str(maps_raw.get("primary_type", "")),
        latitude=(float(maps_raw["latitude"]) if maps_raw.get("latitude") is not None else None),
        longitude=(float(maps_raw["longitude"]) if maps_raw.get("longitude") is not None else None),
        google_maps_uri=str(maps_raw.get("google_maps_uri", "")),
        website_uri=str(maps_raw.get("website_uri", "")),
        oldest_visible_review_at=str(maps_raw.get("oldest_visible_review_at", "")),
        review_sample_size=int(maps_raw.get("review_sample_size", 0)),
        denue_id=str(maps_raw.get("denue_id", "")),
        denue_clee=str(maps_raw.get("denue_clee", "")),
        denue_name=str(maps_raw.get("denue_name", "")),
        denue_address=str(maps_raw.get("denue_address", "")),
        denue_activity=str(maps_raw.get("denue_activity", "")),
        denue_size_band=str(maps_raw.get("denue_size_band", "")),
        denue_latitude=(float(maps_raw["denue_latitude"]) if maps_raw.get("denue_latitude") is not None else None),
        denue_longitude=(float(maps_raw["denue_longitude"]) if maps_raw.get("denue_longitude") is not None else None),
        denue_verified=boolean(maps_raw, "denue_verified"),
        denue_observed_at=str(maps_raw.get("denue_observed_at", "")),
    ) if maps_raw else None

    imss_raw = sub("imss")
    imss = IMSSPayrollData(
        registered_employees=imss_raw.get("registered_employees"),
    ) if imss_raw else None

    bureau_raw = sub("buro")
    bureau_score = bureau_raw.get("score")
    bureau_score = (
        int(bureau_score) if bureau_score not in (None, "") else None
    )
    bureau = BuroData(
        checked=boolean(bureau_raw, "checked"),
        active_delinquencies=int(bureau_raw.get("active_delinquencies", 0)),
        active_loans_count=int(bureau_raw.get("active_loans_count", 0)),
        worst_mob_status=str(bureau_raw.get("worst_mob_status", "")),
        score=bureau_score,
        source=str(bureau_raw.get("source", "unknown")),
        verified=boolean(bureau_raw, "verified"),
        evidence_reference=str(bureau_raw.get("evidence_reference", "")),
        observed_at=str(bureau_raw.get("observed_at", "")),
    ) if bureau_raw else None

    fraud_raw = sub("fraud")
    fraud = FraudData(
        phone_mx=str(fraud_raw.get("phone_mx", "")),
        rfc=str(fraud_raw.get("rfc", "")),
        curp=str(fraud_raw.get("curp", "")),
        ine_checked=boolean(fraud_raw, "ine_checked"),
        address_stated=str(fraud_raw.get("address_stated", "")),
    ) if fraud_raw else None

    pharmacy_raw = sub("pharmacy")
    pharmacy = PharmacyData(
        subtype=str(pharmacy_raw.get("subtype", "community_pharmacy")),
        scian_code=str(pharmacy_raw.get("scian_code", "464111")),
        sells_controlled_medicines=boolean(pharmacy_raw, "sells_controlled_medicines"),
        license_status=str(pharmacy_raw.get("license_status", "not_supplied")),
        license_reference=str(pharmacy_raw.get("license_reference", "")),
        supplier_count=int(pharmacy_raw.get("supplier_count", 0)),
        top_supplier_share=(float(pharmacy_raw["top_supplier_share"]) if pharmacy_raw.get("top_supplier_share") is not None else None),
        inventory_days=(float(pharmacy_raw["inventory_days"]) if pharmacy_raw.get("inventory_days") is not None else None),
        expiry_writeoff_ratio=(float(pharmacy_raw["expiry_writeoff_ratio"]) if pharmacy_raw.get("expiry_writeoff_ratio") is not None else None),
        gross_margin_pct=(float(pharmacy_raw["gross_margin_pct"]) if pharmacy_raw.get("gross_margin_pct") is not None else None),
        stockout_rate=(float(pharmacy_raw["stockout_rate"]) if pharmacy_raw.get("stockout_rate") is not None else None),
        source=str(pharmacy_raw.get("source", "partner_supplied")),
        evidence_reference=str(pharmacy_raw.get("evidence_reference", "")),
        observed_at=str(pharmacy_raw.get("observed_at", "")),
    ) if pharmacy_raw else None

    facility_raw = sub("facility")
    facility = FacilityTerms(
        term_months=int(facility_raw.get("term_months", 12)),
        monthly_rate=float(facility_raw.get("monthly_rate", 0.03)),
        existing_monthly_debt_service_mxn=float(facility_raw.get("existing_monthly_debt_service_mxn", 0)),
        policy_max_amount_mxn=float(facility_raw.get("policy_max_amount_mxn", 80_000)),
        target_dscr=float(facility_raw.get("target_dscr", 1.25)),
        revenue_stress_pct=float(facility_raw.get("revenue_stress_pct", 0.15)),
        cost_stress_pct=float(facility_raw.get("cost_stress_pct", 0.10)),
    )

    features_raw = sub("bank_features_v2")
    bank_features_v2 = BankFeatureContractV2(
        contract_version=str(features_raw.get("contract_version", "bank-feature-contract-2.0")),
        calculation_version=str(features_raw.get("calculation_version", "bank-cashflow-2.0")),
        normalization_basis=str(features_raw.get("normalization_basis", "monthly_average")),
        currency=str(features_raw.get("currency", "MXN")),
        period_start=str(features_raw.get("period_start", "")),
        period_end=str(features_raw.get("period_end", "")),
        account_count=int(features_raw.get("account_count", 0)),
        account_coverage_ratio=float(features_raw.get("account_coverage_ratio", 0)),
        account_holder_match=boolean(features_raw, "account_holder_match"),
        classification_coverage_ratio=float(features_raw.get("classification_coverage_ratio", 0)),
        operating_inflows_mxn=float(features_raw.get("operating_inflows_mxn", 0)),
        operating_outflows_mxn=float(features_raw.get("operating_outflows_mxn", 0)),
        internal_transfer_inflows_mxn=float(features_raw.get("internal_transfer_inflows_mxn", 0)),
        debt_proceeds_mxn=float(features_raw.get("debt_proceeds_mxn", 0)),
        refunds_mxn=float(features_raw.get("refunds_mxn", 0)),
        existing_monthly_debt_service_mxn=float(features_raw.get("existing_monthly_debt_service_mxn", 0)),
        end_of_day_avg_balance_mxn=float(features_raw.get("end_of_day_avg_balance_mxn", 0)),
        end_of_day_min_balance_mxn=float(features_raw.get("end_of_day_min_balance_mxn", 0)),
        inflow_volatility=float(features_raw.get("inflow_volatility", 0)),
        top_payer_share=float(features_raw.get("top_payer_share", 0)),
        source=str(features_raw.get("source", "unknown")),
        evidence_reference=str(features_raw.get("evidence_reference", "")),
        observed_at=str(features_raw.get("observed_at", "")),
    ) if features_raw else None

    operating_raw = sub("operating_profile")
    operating_metrics = operating_raw.get("metrics") or {}
    if not isinstance(operating_metrics, dict) or len(operating_metrics) > 12:
        raise ValueError("operating_profile.metrics must be an object with at most 12 values")
    allowed_operating_metrics = set(operating_metrics_for(business_type))
    clean_operating_metrics: dict[str, float] = {}
    for metric_name, metric_value in operating_metrics.items():
        if metric_name not in allowed_operating_metrics:
            raise ValueError(f"operating_profile metric is not allowed for {business_type.value}: {metric_name}")
        if isinstance(metric_value, bool):
            raise ValueError(f"operating_profile.{metric_name} must be numeric")
        numeric_value = float(metric_value)
        finite(f"operating_profile.{metric_name}", numeric_value)
        if numeric_value < 0:
            raise ValueError(f"operating_profile.{metric_name} must be >= 0")
        clean_operating_metrics[metric_name] = numeric_value
    operating_profile = OperatingProfile(
        metrics=clean_operating_metrics,
        source=str(operating_raw.get("source", "unknown")),
        evidence_reference=str(operating_raw.get("evidence_reference", "")),
        observed_at=str(operating_raw.get("observed_at", "")),
    ) if operating_raw else None

    signal_evidence_raw = body.get("signal_evidence") or {}
    if not isinstance(signal_evidence_raw, dict):
        raise ValueError("signal_evidence must be a JSON object")
    if len(signal_evidence_raw) > len(SIGNAL_IDS):
        raise ValueError("signal_evidence contains too many entries")
    signal_evidence: dict[str, ExternalSignalEvidence] = {}
    for signal_id, payload in signal_evidence_raw.items():
        if signal_id not in SIGNAL_IDS:
            raise ValueError(f"Unknown signal_evidence key: {signal_id}")
        if not isinstance(payload, dict):
            raise ValueError(f"signal_evidence.{signal_id} must be a JSON object")
        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict) or len(metrics) > 24:
            raise ValueError(f"signal_evidence.{signal_id}.metrics must be an object with at most 24 values")
        clean_metrics: dict[str, Any] = {}
        allowed_metrics = set(BY_ID[signal_id].metric_schema)
        for metric_name, metric_value in metrics.items():
            if not isinstance(metric_name, str) or not metric_name or len(metric_name) > 80:
                raise ValueError(f"signal_evidence.{signal_id} contains an invalid metric name")
            if isinstance(metric_value, (dict, list)) or metric_value is None:
                raise ValueError(f"signal_evidence.{signal_id}.{metric_name} must be a scalar")
            if isinstance(metric_value, (int, float)) and not isinstance(metric_value, bool):
                finite(f"signal_evidence.{signal_id}.{metric_name}", float(metric_value))
            if isinstance(metric_value, str) and len(metric_value) > 240:
                raise ValueError(f"signal_evidence.{signal_id}.{metric_name} is too long")
            if metric_name not in allowed_metrics:
                raise ValueError(
                    f"signal_evidence.{signal_id}.{metric_name} is not an allowed metric"
                )
            clean_metrics[metric_name] = metric_value
        source = str(payload.get("source", "partner_supplied")).strip()[:80]
        verified = boolean(payload, "verified")
        reference = str(payload.get("evidence_reference", "")).strip()[:240]
        observed_at = str(payload.get("observed_at", "")).strip()[:80]
        if verified and not reference:
            raise ValueError(f"Verified signal_evidence.{signal_id} requires evidence_reference")
        if verified and not observed_at:
            raise ValueError(f"Verified signal_evidence.{signal_id} requires observed_at")
        if verified and not source:
            raise ValueError(f"Verified signal_evidence.{signal_id} requires source")
        if verified:
            try:
                datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    f"Verified signal_evidence.{signal_id}.observed_at must be ISO 8601"
                ) from exc
        if is_production() and is_synthetic_source(source):
            raise ValueError(f"Synthetic signal_evidence.{signal_id} is forbidden in production")
        source_trust = assess_source(source, f"signal:{signal_id}")
        signal_evidence[signal_id] = ExternalSignalEvidence(
            metrics=clean_metrics,
            source=source,
            # A caller may claim verification, but only the server registry can
            # promote the evidence to independently trusted/verified.
            verified=bool(verified and source_trust.trusted),
            evidence_reference=reference,
            observed_at=observed_at,
        )

    if bank:
        number_range("bank.months_connected", bank.months_connected, 0)
        finite("bank.avg_daily_balance_mxn", bank.avg_daily_balance_mxn)
        number_range("bank.monthly_deposit_count", bank.monthly_deposit_count, 0)
        number_range(
            "bank.monthly_deposit_volume_mxn",
            bank.monthly_deposit_volume_mxn,
            0,
        )
        number_range(
            "bank.monthly_outflow_volume_mxn",
            bank.monthly_outflow_volume_mxn,
            0,
        )
        number_range("bank.deposit_regularity", bank.deposit_regularity, 0, 1)
        number_range("bank.overdrafts_90d", bank.overdrafts_90d, 0)
        finite("bank.min_daily_balance_mxn", bank.min_daily_balance_mxn)
        number_range("bank.balance_trend_90d", bank.balance_trend_90d, -1, 1)
    if fmcg:
        number_range("fmcg.months_of_history", fmcg.months_of_history, 0)
        number_range("fmcg.weekly_purchase_rate", fmcg.weekly_purchase_rate, 0, 1)
        number_range(
            "fmcg.missed_weeks_last_12", fmcg.missed_weeks_last_12, 0, 12
        )
        number_range(
            "fmcg.avg_weekly_purchase_mxn", fmcg.avg_weekly_purchase_mxn, 0
        )
        number_range("fmcg.trend_3m", fmcg.trend_3m, -1, 1)
    if tenure:
        number_range(
            "tenure.years_on_google_maps", tenure.years_on_google_maps, 0
        )
        number_range("tenure.years_in_imss", tenure.years_in_imss, 0)
    if pos:
        number_range("pos.months_of_history", pos.months_of_history, 0)
        number_range(
            "pos.avg_monthly_volume_mxn", pos.avg_monthly_volume_mxn, 0
        )
        number_range("pos.volume_consistency", pos.volume_consistency, 0, 1)
        number_range("pos.trend_3m", pos.trend_3m, -1, 1)
    if maps:
        number_range("maps.rating", maps.rating, 0, 5)
        number_range("maps.review_count", maps.review_count, 0)
        number_range(
            "maps.review_velocity_6m", maps.review_velocity_6m, 0
        )
    if bureau:
        number_range(
            "buro.active_delinquencies", bureau.active_delinquencies, 0
        )
        number_range("buro.active_loans_count", bureau.active_loans_count, 0)
        if bureau.score is not None:
            number_range("buro.score", bureau.score, 0, 1000)
    number_range("facility.term_months", facility.term_months, 1, 60)
    number_range("facility.monthly_rate", facility.monthly_rate, 0, 1)
    number_range("facility.existing_monthly_debt_service_mxn", facility.existing_monthly_debt_service_mxn, 0)
    number_range("facility.policy_max_amount_mxn", facility.policy_max_amount_mxn, 1_000)
    number_range("facility.target_dscr", facility.target_dscr, 1, 5)
    number_range("facility.revenue_stress_pct", facility.revenue_stress_pct, 0, 0.9)
    number_range("facility.cost_stress_pct", facility.cost_stress_pct, 0, 0.9)
    if bank_features_v2:
        for field_name in ("account_coverage_ratio", "classification_coverage_ratio", "inflow_volatility", "top_payer_share"):
            number_range(f"bank_features_v2.{field_name}", getattr(bank_features_v2, field_name), 0, 1)
        for field_name in ("account_count", "operating_inflows_mxn", "operating_outflows_mxn", "internal_transfer_inflows_mxn", "debt_proceeds_mxn", "refunds_mxn", "existing_monthly_debt_service_mxn", "end_of_day_avg_balance_mxn"):
            number_range(f"bank_features_v2.{field_name}", getattr(bank_features_v2, field_name), 0)
        finite("bank_features_v2.end_of_day_min_balance_mxn", bank_features_v2.end_of_day_min_balance_mxn)
        if not bank_features_v2.period_start or not bank_features_v2.period_end:
            raise ValueError("bank_features_v2 period_start and period_end are required")
        if not bank_features_v2.evidence_reference or not bank_features_v2.observed_at:
            raise ValueError("bank_features_v2 evidence_reference and observed_at are required")
        if bank_features_v2.normalization_basis != "monthly_average":
            raise ValueError("bank_features_v2.normalization_basis must be monthly_average")
        if bank_features_v2.account_count < 1:
            raise ValueError("bank_features_v2.account_count must be >= 1")
        try:
            period_start = datetime.fromisoformat(bank_features_v2.period_start.replace("Z", "+00:00"))
            period_end = datetime.fromisoformat(bank_features_v2.period_end.replace("Z", "+00:00"))
            datetime.fromisoformat(bank_features_v2.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("bank_features_v2 dates must be ISO 8601") from exc
        if period_start >= period_end:
            raise ValueError("bank_features_v2.period_start must precede period_end")
        lookback_days = (period_end - period_start).days
        if lookback_days < 90 or lookback_days > 400:
            raise ValueError("bank_features_v2 period must cover 90 to 400 days")
    if business_type is BusinessType.PHARMACY and pharmacy is None:
        raise ValueError("pharmacy details are required when business_type is pharmacy")
    if pharmacy:
        if pharmacy.scian_code not in {"464111", "464112"}:
            raise ValueError("pharmacy.scian_code must be 464111 or 464112")
        if pharmacy.license_status not in {"active", "not_required", "pending", "expired", "not_supplied"}:
            raise ValueError("pharmacy.license_status is invalid")
        number_range("pharmacy.supplier_count", pharmacy.supplier_count, 0)
        for field_name in ("top_supplier_share", "expiry_writeoff_ratio", "gross_margin_pct", "stockout_rate"):
            value = getattr(pharmacy, field_name)
            if value is not None:
                number_range(f"pharmacy.{field_name}", value, 0, 1)
        if pharmacy.inventory_days is not None:
            number_range("pharmacy.inventory_days", pharmacy.inventory_days, 0)
    if operating_profile:
        missing_metrics = allowed_operating_metrics - set(operating_profile.metrics)
        if missing_metrics:
            raise ValueError(
                "operating_profile is missing required metrics: " + ", ".join(sorted(missing_metrics))
            )
        if not operating_profile.evidence_reference or not operating_profile.observed_at:
            raise ValueError("operating_profile evidence_reference and observed_at are required")
        try:
            datetime.fromisoformat(operating_profile.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("operating_profile.observed_at must be ISO 8601") from exc

    return Application(
        merchant_name=merchant_name,
        business_type=business_type,
        requested_amount_mxn=requested,
        colonia=str(body.get("colonia", "")),
        clabe=str(body.get("clabe", "")),
        business_description=str(
            body.get("business_description", "")
        ).strip()[:240],
        funding_purpose=str(body.get("funding_purpose", "")).strip()[:80],
        project_description=str(
            body.get("project_description", "")
        ).strip()[:1000],
        evidence_route=str(body.get("evidence_route", "")).strip()[:40],
        bank=bank,
        fmcg=fmcg,
        tenure=tenure,
        pos=pos,
        maps=maps,
        imss=imss,
        buro=bureau,
        fraud=fraud,
        signal_evidence=signal_evidence,
        pharmacy=pharmacy,
        facility=facility,
        bank_features_v2=bank_features_v2,
        operating_profile=operating_profile,
    )


def validate_submission_metadata(
    body: dict[str, Any], *, verified_consent: bool = False,
) -> None:
    """Fail closed on pilot identity, consent and mode metadata."""
    consent = body.get("consent") or {}
    if not isinstance(consent, dict):
        raise ValueError("consent must be a JSON object")
    supplied = bool(
        consent.get("channel") or consent.get("text") or consent.get("text_sha256")
    )
    if supplied:
        channel = str(consent.get("channel", "")).strip().lower()
        text = str(consent.get("text", "")).strip()
        text_sha256 = str(consent.get("text_sha256", "")).strip().lower()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError(
                "consent.channel must be whatsapp, sms, or in_person"
            )
        if not text and not (
            len(text_sha256) == 64
            and all(char in "0123456789abcdef" for char in text_sha256)
        ):
            raise ValueError(
                "consent.text or a valid consent.text_sha256 is required"
            )
    case_mode = str(body.get("case_mode", "")).strip().lower()
    if case_mode and case_mode not in ("shadow", "live"):
        raise ValueError("case_mode must be shadow or live")
    funding_purpose = str(body.get("funding_purpose", "")).strip().lower()
    if funding_purpose and funding_purpose not in FUNDING_PURPOSES:
        raise ValueError(
            "funding_purpose must be working_capital, inventory, equipment, "
            "expansion, renovation, or technology"
        )
    evidence_route = str(body.get("evidence_route", "")).strip().lower()
    if evidence_route and evidence_route not in EVIDENCE_ROUTES:
        raise ValueError(
            "evidence_route must be inventory_led, tpv_led, bank_flow_led, "
            "or hybrid"
        )
    data_authorization = validate_data_authorization(body.get("data_authorization"))
    if is_production():
        if case_mode != "shadow":
            raise ValueError("case_mode must be shadow in production pilot")
        if not supplied and not verified_consent and not data_authorization:
            raise ValueError(
                "verified consent or a documented data authorization is required in production"
            )
        if not str(body.get("cohort_id", "")).strip():
            raise ValueError("cohort_id is required in production")
        if not str(body.get("partner_case_reference", "")).strip():
            raise ValueError("partner_case_reference is required in production")
        if not funding_purpose:
            raise ValueError("funding_purpose is required in production")
        if not str(body.get("project_description", "")).strip():
            raise ValueError("project_description is required in production")
        if not evidence_route:
            raise ValueError("evidence_route is required in production")
        _validate_evidence_route(body, evidence_route)


def validate_data_authorization(value: Any) -> dict[str, str] | None:
    """Validate an approval artifact without deciding its legal sufficiency."""
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("data_authorization must be a JSON object")
    allowed = {
        "bank_documented_instruction",
        "existing_contract",
        "other_counsel_approved",
    }
    basis = str(value.get("basis_label", "")).strip().lower()
    if basis not in allowed:
        raise ValueError(
            "data_authorization.basis_label must be bank_documented_instruction, "
            "existing_contract, or other_counsel_approved"
        )
    normalized = {
        "basis_label": basis,
        "approval_reference": str(value.get("approval_reference", "")).strip(),
        "approved_by": str(value.get("approved_by", "")).strip(),
        "approved_at": str(value.get("approved_at", "")).strip(),
        "scope_sha256": str(value.get("scope_sha256", "")).strip().lower(),
    }
    if not 5 <= len(normalized["approval_reference"]) <= 160:
        raise ValueError("data_authorization.approval_reference must be 5-160 characters")
    if not 3 <= len(normalized["approved_by"]) <= 120:
        raise ValueError("data_authorization.approved_by must be 3-120 characters")
    try:
        approved_at = datetime.fromisoformat(normalized["approved_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("data_authorization.approved_at must be ISO-8601") from exc
    if approved_at.tzinfo is None or approved_at > datetime.now(timezone.utc):
        raise ValueError("data_authorization.approved_at must be a past timezone-aware timestamp")
    digest = normalized["scope_sha256"]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("data_authorization.scope_sha256 must be a SHA-256 hex digest")
    return normalized


def format_score_result(app: Application, result: Any) -> dict[str, Any]:
    """Return the stable API representation of a newly scored case."""
    repayment = result.repayment
    capacity = result.capacity_v2 or {}
    amount_evaluated = capacity.get(
        "amount_evaluated_mxn", min(app.requested_amount_mxn, result.max_ticket_mxn)
    )
    proposed = capacity.get("proposed_amount_mxn")
    return {
        "application_id": result.application_id,
        "merchant_name": result.merchant_name,
        "score": round(result.score, 2),
        "statistical_confidence_interval": None,
        "heuristic_sensitivity_range": {
            "low": round(result.ci_low, 2),
            "high": round(result.ci_high, 2),
            "statistical": False,
            "method": "seeded_input_perturbation",
        },
        "ci_low": round(result.ci_low, 2),  # deprecated compatibility field
        "ci_high": round(result.ci_high, 2),  # deprecated compatibility field
        "tier": result.tier,
        "recommendation": result.decision.value,
        "recommendation_scope": "decision_support_only",
        "requires_bank_decision": True,
        "official_bank_decision": None,
        "requested_amount_mxn": app.requested_amount_mxn,
        "amount_evaluated_mxn": amount_evaluated,
        "proposed_amount_mxn": proposed,
        "recommended_amount_mxn": proposed,  # deprecated alias
        "legacy_engine_amount_mxn": result.approved_amount_mxn,
        "amount_rationale": capacity.get("amount_rationale", [
            "legacy_capacity_path_used; bank_feature_contract_v2_missing"
        ]),
        "data_coverage": round(result.data_coverage, 3),
        "decision_reasons": result.decision_reasons,
        "hard_filter_failures": result.hard_filter_failures,
        "repayment": {
            "dscr": repayment.dscr,
            "burden_ratio": repayment.burden_ratio,
            "hard_declines": repayment.hard_declines,
            "downgrades": repayment.downgrades,
        } if repayment else None,
        "signals": [
            {
                "name": signal.name,
                "available": signal.available,
                "raw_score": signal.raw_score,
                "explanation": signal.explanation,
            }
            for signal in result.signals
        ],
        "scored_at": result.scored_at,
        "engine_version": result.engine_version,
        "alternative_signal_report": result.alternative_signal_report,
        "capacity_v2": capacity,
        "enrichment_report": result.enrichment_report,
        "analyst_ui": "/",
        "case_path": f"/api/applications/{result.application_id}",
    }


def record_submission_metadata(
    log: ScoringLog,
    application_id: str,
    body: dict[str, Any],
    actor: str,
) -> None:
    consent = body.get("consent") or {}
    if consent.get("channel") or consent.get("text") or consent.get("text_sha256"):
        if consent.get("text"):
            log.record_consent(
                application_id,
                str(consent.get("channel", "")),
                str(consent.get("text", "")),
                actor=actor,
                purpose=str(consent.get("purpose", "credit_assessment")),
                policy_version=str(consent.get("policy_version", "v1")),
            )
        else:
            log.record_consent_hash(
                application_id,
                str(consent.get("channel", "")),
                str(consent.get("text_sha256", "")),
                actor=actor,
                purpose=str(consent.get("purpose", "credit_assessment")),
                policy_version=str(consent.get("policy_version", "v1")),
            )
    cohort_id = str(body.get("cohort_id", "")).strip() or None
    case_mode = str(body.get("case_mode", "")).strip().lower() or None
    partner_ref = str(body.get("partner_case_reference", "")).strip() or None
    log.conn.execute(
        "UPDATE scoring_log SET cohort_id=?, case_mode=?, "
        "partner_case_reference=?, owner_actor=? WHERE application_id=?",
        (cohort_id, case_mode, partner_ref, actor, application_id),
    )
    log.conn.commit()
    authorization = validate_data_authorization(body.get("data_authorization"))
    if authorization:
        log.record_data_authorization(application_id, authorization, actor)


def create_case(
    body: dict[str, Any],
    db_path: str,
    actor: str,
    *,
    verified_consent: bool = False,
) -> dict[str, Any]:
    """Create, score and persist one case through the canonical workflow."""
    assert_real_data_storage_ready()
    validate_submission_metadata(body, verified_consent=verified_consent)
    app = build_application(body)
    portfolio = check_portfolio(app, db_path)
    graduation = get_graduation_offer(app.clabe or "", db_path)
    result = score_application(
        app,
        portfolio_block=portfolio,
        graduation=graduation,
    )
    result.capacity_v2 = calculate_capacity(app)
    result.enrichment_report = build_enrichment_report(app)
    if app.business_type is BusinessType.PHARMACY:
        legacy_decision = result.decision.value
        result.decision = Decision.COMMITTEE
        result.decision_reasons.append(
            "Pharmacy vertical remains committee-only until bank outcome calibration is complete; "
            f"the uncalibrated legacy engine returned {legacy_decision}"
        )
    elif result.decision is Decision.AUTO_APPROVE and result.capacity_v2.get("status") != "capacity_supported":
        result.decision = Decision.COMMITTEE
        result.decision_reasons.append(
            "Auto-approval blocked: trusted Bank Feature Contract v2 does not support capacity"
        )
    elif result.decision is Decision.AUTO_APPROVE and app.business_type.value not in validated_auto_approve_types():
        result.decision = Decision.COMMITTEE
        result.decision_reasons.append(
            "Auto-approval blocked: business type has no bank/model-risk validation approval"
        )
    with ScoringLog(db_path) as log:
        log.log(app, result)
        record_submission_metadata(
            log,
            result.application_id,
            body,
            actor=actor,
        )
    response = format_score_result(app, result)
    response["evidence_layers"] = evidence_layers(
        app.to_dict(),
        consent_recorded=verified_consent or bool(
            (body.get("consent") or {}).get("text")
            or (body.get("consent") or {}).get("text_sha256")
        ),
    )
    response["data_use_authorization_recorded"] = bool(
        validate_data_authorization(body.get("data_authorization"))
    )
    response["business_policy"] = assess_business_policy(
        app.business_type, response["evidence_layers"]
    )
    return response


def get_case(
    db_path: str,
    application_id: str,
    owner_actor: str | None = None,
) -> dict[str, Any] | None:
    with closing(connect_database(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT application_id, merchant_name, score, tier, decision, "
            "approved_mxn, data_coverage, analyst_override, analyst_reason, "
            "disbursed, outcome_status, scored_at, raw_result, raw_application, "
            "consent_timestamp, consent_channel, cohort_id, case_mode, "
            "partner_case_reference, partner_decision, partner_reason, "
            "partner_decision_at, recommendation_agreement, owner_actor "
            "FROM scoring_log WHERE application_id=? "
            "AND (? IS NULL OR owner_actor=?)",
            (application_id, owner_actor, owner_actor),
        ).fetchone()
    if not row:
        return None
    raw_result = json.loads(row["raw_result"] or "{}")
    raw_application = json.loads(row["raw_application"] or "{}")
    capacity = raw_result.get("capacity_v2") or {}
    requested_amount = float(raw_application.get("requested_amount_mxn", 0) or 0)
    amount_evaluated = capacity.get(
        "amount_evaluated_mxn", min(requested_amount, float(raw_result.get("max_ticket_mxn", requested_amount) or 0))
    )
    proposed_amount = capacity.get("proposed_amount_mxn")
    case = {
        "application_id": row["application_id"],
        "merchant_name": row["merchant_name"],
        "score": row["score"],
        "tier": row["tier"],
        "recommendation": row["decision"],
        "recommendation_scope": "decision_support_only",
        "requires_bank_decision": True,
        "official_bank_decision": row["partner_decision"],
        "requested_amount_mxn": requested_amount,
        "amount_evaluated_mxn": amount_evaluated,
        "proposed_amount_mxn": proposed_amount,
        "recommended_amount_mxn": proposed_amount,
        "legacy_engine_amount_mxn": row["approved_mxn"],
        "amount_rationale": capacity.get("amount_rationale", ["legacy_capacity_path_used"]),
        "data_coverage": row["data_coverage"],
        "analyst_decision": row["analyst_override"],
        "analyst_reason": row["analyst_reason"],
        "disbursed": bool(row["disbursed"]),
        "outcome_status": row["outcome_status"],
        "scored_at": row["scored_at"],
        "engine_version": raw_result.get("engine_version"),
        "decision_reasons": raw_result.get("decision_reasons", []),
        "hard_filter_failures": raw_result.get("hard_filter_failures", []),
        "signals": raw_result.get("signals", []),
        "alternative_signal_report": raw_result.get("alternative_signal_report", {}),
        "capacity_v2": capacity,
        "enrichment_report": raw_result.get("enrichment_report", {}),
        "statistical_confidence_interval": None,
        "heuristic_sensitivity_range": {
            "low": raw_result.get("ci_low"), "high": raw_result.get("ci_high"),
            "statistical": False, "method": "seeded_input_perturbation",
        },
        "evidence": {
            "bank": raw_application.get("bank"),
            "fmcg": raw_application.get("fmcg"),
            "bureau": raw_application.get("buro"),
            "identity": raw_application.get("fraud"),
            "tenure": raw_application.get("tenure"),
            "pos": raw_application.get("pos"),
            "maps": raw_application.get("maps"),
            "imss": raw_application.get("imss"),
            "pharmacy": raw_application.get("pharmacy"),
            "bank_features_v2": raw_application.get("bank_features_v2"),
        },
        "request": {
            "business_description": raw_application.get(
                "business_description", ""
            ),
            "funding_purpose": raw_application.get("funding_purpose", ""),
            "project_description": raw_application.get(
                "project_description", ""
            ),
            "evidence_route": raw_application.get("evidence_route", ""),
        },
        "consent": {
            "timestamp": row["consent_timestamp"],
            "channel": row["consent_channel"],
        },
        "pilot": {
            "cohort_id": row["cohort_id"],
            "case_mode": row["case_mode"],
            "partner_case_reference": row["partner_case_reference"],
            "owner_actor": row["owner_actor"],
        },
        "partner_outcome": {
            "decision": row["partner_decision"],
            "reason": row["partner_reason"],
            "decided_at": row["partner_decision_at"],
            "recommendation_agreement": row["recommendation_agreement"],
        },
    }
    case["evidence_layers"] = evidence_layers(
        raw_application,
        consent_recorded=bool(row["consent_timestamp"]),
    )
    case["business_policy"] = assess_business_policy(
        raw_application.get("business_type", "other"), case["evidence_layers"]
    )
    with ScoringLog(db_path) as log:
        case["performance_events"] = log.list_shadow_performance(application_id)
    return case


def list_cases(
    db_path: str,
    owner_actor: str | None = None,
) -> list[dict[str, Any]]:
    """Build the analyst queue from persisted cases, newest first."""
    with closing(connect_database(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT application_id, merchant_name, business_type, colonia,
                   requested_mxn, approved_mxn, score, ci_low, ci_high,
                   data_coverage, decision, scored_at,
                   analyst_override, analyst_reason, analyst_decision_at,
                   disbursed, graduation_tier, tier, analyst_note, buro_score,
                   is_demo, outcome_status, payment_1_amount_mxn,
                   payment_2_amount_mxn, consent_timestamp, consent_channel,
                   cohort_id, case_mode, partner_case_reference,
                   partner_decision, partner_reason, partner_decision_at,
                   recommendation_agreement, owner_actor,
                   raw_application, raw_result
            FROM scoring_log
            WHERE (? IS NULL OR owner_actor=?)
            ORDER BY scored_at DESC
            """,
            (owner_actor, owner_actor),
        ).fetchall()
    cases = []
    for row in rows:
        case = dict(row)
        result = json.loads(case.pop("raw_result", "{}"))
        application = json.loads(case.pop("raw_application", "{}"))
        case["recommendation"] = case["decision"]
        case["amount_evaluated_mxn"] = case["approved_mxn"]
        case["signals"] = result.get("signals", [])
        case["decision_reasons"] = result.get("decision_reasons", [])
        case["hard_filter_failures"] = result.get("hard_filter_failures", [])
        case["repayment"] = result.get("repayment")
        case["fraud_assessment"] = result.get("fraud_assessment")
        case["tier_sensitivity"] = result.get("tier_sensitivity", {})
        case["engine_version"] = result.get("engine_version")
        case["environment"] = result.get(
            "environment", application.get("environment", "unspecified")
        )
        case["business_description"] = application.get(
            "business_description", ""
        )
        case["funding_purpose"] = application.get("funding_purpose", "")
        case["project_description"] = application.get(
            "project_description", ""
        )
        case["evidence_route"] = application.get("evidence_route", "")
        case["production_blocks"] = result.get("production_blocks", [])
        case["evidence_layers"] = evidence_layers(
            application,
            consent_recorded=bool(case.get("consent_timestamp")),
        )
        case["business_policy"] = assess_business_policy(
            application.get("business_type", "other"), case["evidence_layers"]
        )
        case["data_sources"] = {
            "bank": (application.get("bank") or {}).get("source", "missing"),
            "bank_verified": bool(
                (application.get("bank") or {}).get("verified", False)
            ),
            "bank_reference": (
                application.get("bank") or {}
            ).get("evidence_reference", ""),
            "fmcg": (application.get("fmcg") or {}).get("source", "missing"),
            "fmcg_verified": bool(
                (application.get("fmcg") or {}).get("verified", False)
            ),
            "fmcg_reference": (
                application.get("fmcg") or {}
            ).get("evidence_reference", ""),
            "pos": (application.get("pos") or {}).get("source", "missing"),
            "pos_verified": bool(
                (application.get("pos") or {}).get("verified", False)
            ),
            "pos_reference": (
                application.get("pos") or {}
            ).get("evidence_reference", ""),
        }
        case["mitigation_menu"] = None
        cases.append(case)
    return cases
