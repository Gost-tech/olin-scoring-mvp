#!/usr/bin/env python3
"""Bank-style synthetic acceptance across every supported SME business type."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from olin.api.cases import build_application, create_case, get_case
from olin.business_segments import business_policy_catalog, operating_metrics_for
from olin.capacity_v2 import calculate_capacity
from olin.models import BusinessType
from olin.store import ScoringLog


NOW = "2026-08-21T12:00:00+00:00"
TRUST_REGISTRY = json.dumps({
    "bank_cashflow_service": {
        "status": "active", "evidence_types": ["bank_feature_contract_v2", "legacy_bank_cash_flow"],
        "valid_until": "2030-01-01", "attestation_id": "BANK-CASHFLOW-ATTESTATION-1",
    },
    "bank_supplier_feed": {"status": "active", "evidence_types": ["supplier_purchases"], "valid_until": "2030-01-01", "attestation_id": "BANK-SUPPLIER-ATTESTATION-1"},
    "bank_acquirer_feed": {"status": "active", "evidence_types": ["pos_settlements"], "valid_until": "2030-01-01", "attestation_id": "BANK-POS-ATTESTATION-1"},
    "circulo_credito": {"status": "active", "evidence_types": ["credit_bureau"], "valid_until": "2030-01-01", "attestation_id": "BANK-BUREAU-ATTESTATION-1"},
    "google_places": {"status": "active", "evidence_types": ["geo_continuity"], "valid_until": "2030-01-01", "attestation_id": "GOOGLE-ATTESTATION-1"},
    "bank_operating_review": {"status": "active", "evidence_types": ["operating_profile"], "valid_until": "2030-01-01", "attestation_id": "BANK-OPERATING-ATTESTATION-1"},
    "bank_core": {
        "status": "active", "evidence_types": ["repayment_outcome"],
        "valid_until": "2030-01-01", "attestation_id": "BANK-OUTCOME-ATTESTATION-1",
    },
    "bank_pharmacy_review": {
        "status": "active", "evidence_types": ["pharmacy_evidence"],
        "valid_until": "2030-01-01", "attestation_id": "BANK-PHARMACY-ATTESTATION-1",
    },
})


def build_synthetic_case_payload(business_type: BusinessType, index: int) -> dict:
    body = {
        "merchant_name": f"Synthetic {business_type.value} SME",
        "business_type": business_type.value,
        "requested_mxn": 50_000,
        "business_description": f"Synthetic bank acceptance case for {business_type.value}.",
        "funding_purpose": "working_capital",
        "project_description": "Bank-controlled synthetic acceptance; no real customer data or money movement.",
        "evidence_route": "hybrid",
        "case_mode": "shadow",
        "cohort_id": "all-business-synthetic-uat-v1",
        "partner_case_reference": f"BANK-ALL-{index:03d}",
        "consent": {"channel": "in_person", "text": "Synthetic UAT consent only.", "policy_version": "uat-v1"},
        "bank": {
            "months_connected": 12, "avg_daily_balance_mxn": 28_000,
            "monthly_deposit_count": 42, "monthly_deposit_volume_mxn": 190_000,
            "monthly_outflow_volume_mxn": 125_000, "deposit_regularity": .91,
            "overdrafts_90d": 0, "balance_trend_90d": .08,
            "min_daily_balance_mxn": 5_500, "source": "bank_cashflow_service",
            "verified": True, "evidence_reference": f"BANK-{index:03d}", "observed_at": NOW,
        },
        "bank_features_v2": {
            "contract_version": "bank-feature-contract-2.0",
            "calculation_version": "bank-cashflow-2.0",
            "normalization_basis": "monthly_average", "currency": "MXN",
            "period_start": "2026-02-01", "period_end": "2026-07-31",
            "account_count": 2, "account_coverage_ratio": .98,
            "account_holder_match": True, "classification_coverage_ratio": .96,
            "operating_inflows_mxn": 190_000, "operating_outflows_mxn": 125_000,
            "internal_transfer_inflows_mxn": 25_000, "debt_proceeds_mxn": 15_000,
            "refunds_mxn": 2_000, "existing_monthly_debt_service_mxn": 3_000,
            "end_of_day_avg_balance_mxn": 28_000, "end_of_day_min_balance_mxn": 5_500,
            "inflow_volatility": .18, "top_payer_share": .12,
            "source": "bank_cashflow_service", "evidence_reference": f"BFC2-{index:03d}",
            "observed_at": NOW,
        },
        "facility": {
            "term_months": 12, "monthly_rate": .03,
            "existing_monthly_debt_service_mxn": 3_000,
            "policy_max_amount_mxn": 45_000, "target_dscr": 1.25,
            "revenue_stress_pct": .15, "cost_stress_pct": .10,
        },
        "operating_profile": {
            "metrics": {
                metric: float(index * 100 + position)
                for position, metric in enumerate(operating_metrics_for(business_type), 1)
            },
            "source": "bank_operating_review",
            "evidence_reference": f"OPERATING-{index:03d}",
            "observed_at": NOW,
        },
        "fmcg": {
            "months_of_history": 12, "weekly_purchase_rate": .94,
            "missed_weeks_last_12": 1, "avg_weekly_purchase_mxn": 22_000,
            "distributor_confirmed": True, "trend_3m": .08,
            "source": "bank_supplier_feed", "verified": True,
            "evidence_reference": f"SUP-{index:03d}", "observed_at": NOW,
        },
        "pos": {
            "months_of_history": 12, "avg_monthly_volume_mxn": 120_000,
            "volume_consistency": .90, "trend_3m": .06,
            "source": "bank_acquirer_feed", "verified": True,
            "evidence_reference": f"POS-{index:03d}", "observed_at": NOW,
        },
        "tenure": {"years_on_google_maps": 5, "years_in_imss": 3, "address_consistent": True},
        "maps": {
            "rating": 4.5, "review_count": 85, "review_velocity_6m": 8,
            "source": "google_places", "verified": True,
            "evidence_reference": f"PLACE-{index:03d}", "observed_at": NOW,
        },
        "buro": {
            "checked": True, "active_delinquencies": 0, "active_loans_count": 1,
            "worst_mob_status": "01", "score": 710, "source": "circulo_credito",
            "verified": True, "evidence_reference": f"BURO-{index:03d}", "observed_at": NOW,
        },
        "fraud": {
            "phone_mx": "5500000000", "rfc": "ABC850101AB1",
            "curp": "GABC850101HDFRRL09",
            "ine_checked": True, "address_stated": "Synthetic UAT address",
        },
    }
    if business_type is BusinessType.PHARMACY:
        body["pharmacy"] = {
            "subtype": "community_pharmacy", "scian_code": "464111",
            "sells_controlled_medicines": True, "license_status": "active",
            "license_reference": f"LIC-{index:03d}", "supplier_count": 4,
            "top_supplier_share": .44, "inventory_days": 38,
            "expiry_writeoff_ratio": .018, "gross_margin_pct": .27,
            "stockout_rate": .05, "source": "bank_pharmacy_review",
            "evidence_reference": f"PHARM-{index:03d}", "observed_at": NOW,
        }
    return body


def run_all_business_acceptance() -> dict:
    previous = {key: os.environ.get(key) for key in ("OLIN_MODE", "OLIN_TRUSTED_SOURCE_REGISTRY", "OLIN_REAL_DATA_ENABLED", "OLIN_VALIDATED_AUTO_APPROVE_TYPES")}
    os.environ.update({
        "OLIN_MODE": "production",
        "OLIN_TRUSTED_SOURCE_REGISTRY": TRUST_REGISTRY,
        "OLIN_REAL_DATA_ENABLED": "0",
        "OLIN_VALIDATED_AUTO_APPROVE_TYPES": "",
    })
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = handle.name
    handle.close()
    results = []
    try:
        for index, business_type in enumerate(BusinessType, 1):
            payload = build_synthetic_case_payload(business_type, index)
            response = create_case(payload, db_path, "bank_all_business_uat")
            failures = []
            requested = response["requested_amount_mxn"]
            evaluated = response["amount_evaluated_mxn"]
            proposed = response["proposed_amount_mxn"]
            if not (0 <= proposed <= evaluated <= requested):
                failures.append("amount_ordering_invalid")
            if response["capacity_v2"].get("status") != "capacity_supported":
                failures.append("trusted_capacity_not_supported")
            if not response["capacity_v2"].get("source_trust", {}).get("trusted"):
                failures.append("bank_feature_source_not_trusted")
            if response["statistical_confidence_interval"] is not None:
                failures.append("fake_statistical_interval_exposed")
            if response["enrichment_report"]["missing_evidence"]:
                failures.append("required_evidence_missing")
            if response["recommendation"] == "AUTO_APPROVE":
                failures.append("unvalidated_business_auto_approved")
            if response["recommendation"] == "DECLINE":
                failures.append("complete_positive_synthetic_case_unexpectedly_declined")
            with ScoringLog(db_path) as log:
                log.record_partner_outcome(
                    response["application_id"], "approved",
                    "Synthetic bank committee outcome for acceptance testing", NOW,
                    "bank_all_business_uat",
                )
                outcome = log.record_shadow_performance(
                    response["application_id"], {
                        "event_id": f"PERF-{index:03d}", "event_type": "scheduled_observation",
                        "observed_at": "2026-10-01T00:00:00+00:00",
                        "period_end": "2026-09-30T00:00:00+00:00", "days_past_due": 0,
                        "outstanding_balance_mxn": proposed, "scheduled_payment_mxn": 4_500,
                        "amount_paid_mxn": 4_500, "source": "bank_core",
                        "evidence_reference": f"LOAN-{index:03d}-M1",
                    }, "bank_all_business_uat",
                )
            persisted = get_case(db_path, response["application_id"], "bank_all_business_uat")
            if not persisted or len(persisted.get("performance_events", [])) != 1:
                failures.append("outcome_not_persisted")
            results.append({
                "business_type": business_type.value,
                "segment_id": response["business_policy"]["segment_id"],
                "recommendation": response["recommendation"],
                "requested_amount_mxn": requested,
                "evaluated_amount_mxn": evaluated,
                "proposed_amount_mxn": proposed,
                "outcome_status": outcome["status"],
                "missing_evidence": response["enrichment_report"]["missing_evidence"],
                "passed": not failures, "failures": failures,
            })

        base = build_synthetic_case_payload(BusinessType.RETAIL, 999)
        adversarial = {}
        untrusted = deepcopy(base)
        untrusted["bank_features_v2"]["source"] = "self_asserted_upload"
        adversarial["untrusted_source"] = calculate_capacity(build_application(untrusted))
        incomplete = deepcopy(base)
        incomplete["bank_features_v2"]["account_coverage_ratio"] = .50
        adversarial["incomplete_accounts"] = calculate_capacity(build_application(incomplete))
        loss = deepcopy(base)
        loss["bank_features_v2"]["operating_outflows_mxn"] = 220_000
        adversarial["negative_cash_flow"] = calculate_capacity(build_application(loss))
        negative_tests_passed = (
            adversarial["untrusted_source"]["proposed_amount_mxn"] is None
            and adversarial["incomplete_accounts"]["proposed_amount_mxn"] is None
            and adversarial["negative_cash_flow"]["proposed_amount_mxn"] == 0
        )
        return {
            "test": "all-supported-business bank acceptance",
            "mode": "production-code-path-with-synthetic-data",
            "business_type_count": len(results),
            "passed": all(item["passed"] for item in results) and negative_tests_passed,
            "results": results,
            "negative_tests": {
                "passed": negative_tests_passed,
                "untrusted_source_status": adversarial["untrusted_source"]["status"],
                "incomplete_accounts_status": adversarial["incomplete_accounts"]["status"],
                "negative_cash_flow_status": adversarial["negative_cash_flow"]["status"],
            },
            "policy_catalog": business_policy_catalog(),
            "limitations": [
                "Synthetic acceptance validates software behavior, not default prediction.",
                "No business type is auto-eligible until bank/model-risk validation explicitly enables it.",
                "Real-data use remains blocked until the managed PostgreSQL deployment passes Olin preflight and the bank's external approvals.",
            ],
        }
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    report = run_all_business_acceptance()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
