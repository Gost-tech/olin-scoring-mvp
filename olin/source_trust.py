"""Server-controlled evidence trust registry.

Payload fields can describe provenance, but cannot make themselves trusted.
Trust comes only from an operator-managed registry keyed by provider identity.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrustAssessment:
    source: str
    evidence_type: str
    trusted: bool
    reason: str
    attestation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceAttestationAssessment:
    """Proposition-scoped Phase 2 view of operator-managed source authority."""

    source: str
    issuer_id: str
    acquisition_method: str
    source_class: str
    proposition_type: str
    trusted: bool
    reason: str
    attestation_id: str = ""
    attestation_version: str = ""
    registry_digest: str = ""
    valid_until: str = ""
    freshness_max_age_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _registry() -> dict[str, Any]:
    raw = os.getenv("OLIN_TRUSTED_SOURCE_REGISTRY", "").strip()
    registry_file = os.getenv("OLIN_TRUSTED_SOURCE_REGISTRY_FILE", "").strip()
    if not raw and registry_file:
        try:
            path = Path(registry_file).expanduser().resolve()
            if path.stat().st_size > 262_144:
                return {}
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return {}
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def trust_registry_readiness() -> dict[str, Any]:
    registry = _registry()
    active = {
        source: entry
        for source, entry in registry.items()
        if isinstance(entry, dict) and str(entry.get("status", "")).lower() == "active"
    }
    covered = {
        evidence_type
        for entry in active.values()
        for evidence_type in (entry.get("evidence_types") or [])
    }
    required = {"bank_feature_contract_v2", "repayment_outcome"}
    return {
        "configured": bool(registry),
        "active_source_count": len(active),
        "required_evidence_types": sorted(required),
        "missing_evidence_types": sorted(required - covered),
        "ready": bool(active) and not (required - covered),
    }


def assess_source(source: str, evidence_type: str) -> TrustAssessment:
    normalized = str(source or "unknown").strip().lower()
    entry = _registry().get(normalized)
    if not isinstance(entry, dict):
        return TrustAssessment(
            normalized, evidence_type, False, "source_not_registered"
        )
    if str(entry.get("status", "")).lower() != "active":
        return TrustAssessment(normalized, evidence_type, False, "source_not_active")
    allowed = entry.get("evidence_types") or []
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) for item in allowed
    ):
        return TrustAssessment(
            normalized, evidence_type, False, "invalid_evidence_type_registry"
        )
    if evidence_type not in allowed and "*" not in allowed:
        return TrustAssessment(
            normalized, evidence_type, False, "evidence_type_not_authorized"
        )
    valid_until = str(entry.get("valid_until", "")).strip()
    if not valid_until:
        return TrustAssessment(
            normalized, evidence_type, False, "attestation_expiry_missing"
        )
    try:
        if date.fromisoformat(valid_until) < datetime.now(timezone.utc).date():
            return TrustAssessment(
                normalized, evidence_type, False, "attestation_expired"
            )
    except ValueError:
        return TrustAssessment(
            normalized, evidence_type, False, "invalid_attestation_expiry"
        )
    attestation = str(entry.get("attestation_id", "")).strip()
    if not attestation:
        return TrustAssessment(normalized, evidence_type, False, "attestation_missing")
    return TrustAssessment(
        normalized, evidence_type, True, "registered_and_attested", attestation
    )


def assess_source_attestation(
    source: str,
    *,
    issuer_id: str,
    acquisition_method: str,
    proposition_type: str,
    tenant_id: str,
    subject_controller_id: str,
    as_of: date,
    production: bool,
) -> SourceAttestationAssessment:
    """Resolve narrow Phase 2 trust without accepting caller trust labels.

    Legacy ``assess_source`` remains unchanged for existing flows. This stricter
    projection requires an exact proposition, issuer, acquisition method,
    environment, tenant scope, and versioned attestation. Wildcards and
    example/placeholder entries can never establish production trust.
    """
    normalized = str(source or "unknown").strip().lower()
    registry = _registry()
    entry = registry.get(normalized)
    digest = sha256(
        json.dumps(
            {
                "attestation": entry if isinstance(entry, dict) else None,
                "registry_schema_version": 1,
                "source_id": normalized,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    def denied(reason: str, entry: dict[str, Any] | None = None):
        item = entry or {}
        return SourceAttestationAssessment(
            normalized,
            str(item.get("issuer_id", "")).strip(),
            str(acquisition_method or "").strip(),
            str(item.get("source_class", "")).strip(),
            str(proposition_type or "").strip(),
            False,
            reason,
            str(item.get("attestation_id", "")).strip(),
            str(item.get("attestation_version", "")).strip(),
            digest,
            str(item.get("valid_until", "")).strip(),
            0,
        )

    if not isinstance(entry, dict):
        return denied("source_not_registered")
    lowered_identity = " ".join(
        str(entry.get(field, "")).lower()
        for field in ("environment", "source_class", "issuer_id", "attestation_id")
    )
    if production and any(
        marker in lowered_identity
        for marker in ("example", "placeholder", "synthetic", "demo")
    ):
        return denied("non_production_source", entry)
    if str(entry.get("status", "")).lower() != "active":
        return denied("source_not_active", entry)
    environment = str(entry.get("environment", "")).lower()
    if production and environment != "production":
        return denied("source_not_production_qualified", entry)
    if str(entry.get("issuer_id", "")).strip() != str(issuer_id or "").strip():
        return denied("issuer_identity_mismatch", entry)
    methods = entry.get("acquisition_methods")
    if not isinstance(methods, list) or acquisition_method not in methods:
        return denied("acquisition_method_not_authorized", entry)
    propositions = entry.get("proposition_types")
    if (
        not isinstance(propositions, list)
        or "*" in propositions
        or proposition_type not in propositions
    ):
        return denied("proposition_not_authorized", entry)
    tenants = entry.get("tenant_ids")
    if not isinstance(tenants, list) or (
        "*" not in tenants and tenant_id not in tenants
    ):
        return denied("tenant_not_authorized", entry)
    valid_until = str(entry.get("valid_until", "")).strip()
    try:
        if not valid_until or date.fromisoformat(valid_until) < as_of:
            return denied("attestation_expired", entry)
    except ValueError:
        return denied("invalid_attestation_expiry", entry)
    required = (
        "attestation_id",
        "attestation_version",
        "attestation_issuer_id",
        "controller_id",
        "source_class",
    )
    if any(not str(entry.get(field, "")).strip() for field in required):
        return denied("attestation_metadata_incomplete", entry)
    if str(entry.get("independence_class", "")).strip() != "independent_from_subject":
        return denied("source_not_independent_from_subject", entry)
    controller_id = str(entry.get("controller_id", "")).strip()
    attestation_issuer_id = str(entry.get("attestation_issuer_id", "")).strip()
    subject_controller_id = str(subject_controller_id or "").strip()
    if not subject_controller_id:
        return denied("subject_controller_identity_missing", entry)
    if controller_id in {subject_controller_id, attestation_issuer_id}:
        return denied("source_controller_not_independent", entry)
    if attestation_issuer_id == subject_controller_id:
        return denied("attestation_issuer_not_independent", entry)
    if str(entry.get("source_class", "")).strip() not in {
        "accredited_data_provider",
        "government_registry",
        "independent_auditor",
        "regulated_financial_institution",
    }:
        return denied("source_class_not_authorized_for_verification", entry)
    freshness_max_age_days = entry.get("freshness_max_age_days")
    if (
        type(freshness_max_age_days) is not int
        or freshness_max_age_days < 1
        or freshness_max_age_days > 3650
    ):
        return denied("freshness_policy_invalid", entry)
    if entry.get("revoked_at"):
        return denied("attestation_revoked", entry)
    return SourceAttestationAssessment(
        normalized,
        str(entry["issuer_id"]).strip(),
        str(acquisition_method).strip(),
        str(entry["source_class"]).strip(),
        str(proposition_type).strip(),
        True,
        "registered_for_proposition",
        str(entry["attestation_id"]).strip(),
        str(entry["attestation_version"]).strip(),
        digest,
        valid_until,
        freshness_max_age_days,
    )
