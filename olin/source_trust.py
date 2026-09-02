"""Server-controlled evidence trust registry.

Payload fields can describe provenance, but cannot make themselves trusted.
Trust comes only from an operator-managed registry keyed by provider identity.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import date
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
        source: entry for source, entry in registry.items()
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
        return TrustAssessment(normalized, evidence_type, False, "source_not_registered")
    if str(entry.get("status", "")).lower() != "active":
        return TrustAssessment(normalized, evidence_type, False, "source_not_active")
    allowed = entry.get("evidence_types") or []
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        return TrustAssessment(normalized, evidence_type, False, "invalid_evidence_type_registry")
    if evidence_type not in allowed and "*" not in allowed:
        return TrustAssessment(normalized, evidence_type, False, "evidence_type_not_authorized")
    valid_until = str(entry.get("valid_until", "")).strip()
    if not valid_until:
        return TrustAssessment(normalized, evidence_type, False, "attestation_expiry_missing")
    try:
        if date.fromisoformat(valid_until) < date.today():
            return TrustAssessment(normalized, evidence_type, False, "attestation_expired")
    except ValueError:
        return TrustAssessment(normalized, evidence_type, False, "invalid_attestation_expiry")
    attestation = str(entry.get("attestation_id", "")).strip()
    if not attestation:
        return TrustAssessment(normalized, evidence_type, False, "attestation_missing")
    return TrustAssessment(normalized, evidence_type, True, "registered_and_attested", attestation)
