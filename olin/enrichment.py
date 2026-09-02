"""Automatic, deterministic case enrichment and evidence reconciliation."""
from __future__ import annotations

from typing import Any

from .models import Application, BusinessType
from .source_trust import assess_source
from .business_segments import operating_metrics_for


def build_enrichment_report(application: Application) -> dict[str, Any]:
    required = ["identity_consent", "credit_bureau", "bank_feature_contract_v2", "operating_profile", "geo_continuity"]
    pharmacy_findings: dict[str, Any] | None = None
    pharmacy_trust = (
        assess_source(application.pharmacy.source, "pharmacy_evidence")
        if application.pharmacy else None
    )
    if application.business_type is BusinessType.PHARMACY:
        required += ["pharmacy_classification", "supplier_inventory", "regulatory_status"]
        pharmacy = application.pharmacy
        if pharmacy is None:
            pharmacy_findings = {
                "status": "missing",
                "scian_code": None,
                "risks": ["pharmacy_subtype_not_supplied", "regulatory_scope_unknown"],
            }
        else:
            regulatory_required = pharmacy.sells_controlled_medicines
            license_fact_ok = (not regulatory_required) or pharmacy.license_status == "active"
            license_ok = bool(license_fact_ok and pharmacy_trust and pharmacy_trust.trusted)
            pharmacy_findings = {
                "status": "classified",
                "subtype": pharmacy.subtype,
                "scian_code": pharmacy.scian_code,
                "regulatory_license_required": regulatory_required,
                "regulatory_status_claimed_sufficient": license_fact_ok,
                "regulatory_status_sufficient": license_ok,
                "inventory_metrics": {
                    "inventory_days": pharmacy.inventory_days,
                    "expiry_writeoff_ratio": pharmacy.expiry_writeoff_ratio,
                    "stockout_rate": pharmacy.stockout_rate,
                    "supplier_count": pharmacy.supplier_count,
                    "top_supplier_share": pharmacy.top_supplier_share,
                },
                "risks": [
                    risk for risk, present in {
                        "controlled_medicine_license_missing": regulatory_required and not license_ok,
                        "supplier_concentration_high": (pharmacy.top_supplier_share or 0) > 0.60,
                        "expiry_losses_high": (pharmacy.expiry_writeoff_ratio or 0) > 0.05,
                        "stockouts_high": (pharmacy.stockout_rate or 0) > 0.10,
                    }.items() if present
                ],
            }

    trust = {}
    if application.bank_features_v2:
        trust["bank_feature_contract_v2"] = assess_source(
            application.bank_features_v2.source, "bank_feature_contract_v2"
        ).to_dict()
    if application.pharmacy:
        trust["pharmacy_evidence"] = pharmacy_trust.to_dict()
    if application.operating_profile:
        trust["operating_profile"] = assess_source(
            application.operating_profile.source, "operating_profile"
        ).to_dict()
    required_operating = set(operating_metrics_for(application.business_type))
    supplied_operating = set(
        application.operating_profile.metrics if application.operating_profile else {}
    )
    operating_complete = bool(
        application.operating_profile
        and required_operating.issubset(supplied_operating)
        and trust.get("operating_profile", {}).get("trusted")
    )
    provider_results = {
        "bank_features": {
            "status": "observed" if application.bank_features_v2 else "missing",
            "trusted": bool(trust.get("bank_feature_contract_v2", {}).get("trusted")),
        },
        "bureau": {"status": "observed" if application.buro and application.buro.checked else "missing"},
        "geo": {"status": "observed" if application.maps or application.tenure else "missing"},
        "pharmacy": {
            "status": "observed" if application.pharmacy else "not_applicable",
            "trusted": bool(trust.get("pharmacy_evidence", {}).get("trusted")),
        },
        "operating_profile": {
            "status": "observed" if application.operating_profile else "missing",
            "trusted": bool(trust.get("operating_profile", {}).get("trusted")),
            "required_metrics": sorted(required_operating),
            "supplied_metrics": sorted(supplied_operating),
        },
    }
    observed = {
        "credit_bureau": bool(application.buro and application.buro.checked),
        "bank_feature_contract_v2": application.bank_features_v2 is not None,
        "operating_profile": operating_complete,
        "geo_continuity": application.maps is not None or application.tenure is not None,
        "pharmacy_classification": application.pharmacy is not None,
        "supplier_inventory": bool(application.pharmacy and application.pharmacy.supplier_count),
        "regulatory_status": bool(application.pharmacy and application.pharmacy.license_status != "not_supplied"),
    }
    missing = [item for item in required if item not in {"identity_consent"} and not observed.get(item, False)]
    return {
        "orchestrator_version": "enrichment-1.0.0",
        "business_type": application.business_type.value,
        "required_evidence": required,
        "missing_evidence": missing,
        "provider_sequence": ["bank_features", "bureau", "geo", "pharmacy_registry_or_bank_attestation"],
        "provider_results": provider_results,
        "reconciliation_controls": [
            "internal_transfers_excluded_from_operating_inflows",
            "debt_proceeds_excluded_from_operating_inflows",
            "refunds_reported_separately",
            "account_coverage_and_holder_match_required",
        ],
        "source_trust": trust,
        "pharmacy": pharmacy_findings,
    }
