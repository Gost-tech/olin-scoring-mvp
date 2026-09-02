"""Replaceable KYC adapter boundary for Evidence Passport.

Olin stores only provider result references and subject hashes here. Raw ID
images, biometric templates, liveness video, and credentials stay in the
provider- or bank-hosted flow approved for the pilot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .config import mocks_allowed
from .evidence_passport import (
    AUTHORITY_BY_LEGAL_FORM,
    IDENTITY_TYPE,
    LEGAL_FORMS,
    register_verified_evidence,
)


@dataclass(frozen=True)
class KYCVerification:
    source_id: str
    session_id: str
    status: str
    legal_form: str
    identity_subject_hash: str
    business_subject_hash: str
    observed_at: str
    expires_at: str
    identity_verified: bool
    authority_evidence_type: str = ""
    beneficial_owner_verified: bool = False


class KYCVerifier(Protocol):
    def fetch_verification(self, session_id: str) -> KYCVerification:
        """Fetch one authoritative, already-authenticated provider result."""


class SyntheticKYCVerifier:
    """Deterministic non-production adapter for contract and UAT testing."""

    def __init__(self, sessions: Mapping[str, KYCVerification]):
        self._sessions = dict(sessions)

    def fetch_verification(self, session_id: str) -> KYCVerification:
        if not mocks_allowed():
            raise RuntimeError("Synthetic KYC is disabled in pilot and production modes")
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise LookupError("KYC session not found") from exc


def ingest_kyc_verification(
    db_path: str,
    *,
    application_id: str,
    owner_actor: str,
    consent_id: str,
    legal_form: str,
    session_id: str,
    verifier: KYCVerifier,
    actor: str = "kyc_adapter",
) -> dict:
    """Convert an authoritative KYC result into Passport evidence records."""
    legal_form = str(legal_form or "").strip().lower()
    if legal_form not in LEGAL_FORMS:
        raise ValueError("legal_form must be individual_business_owner or legal_entity")
    verification = verifier.fetch_verification(str(session_id or "").strip())
    if verification.legal_form != legal_form:
        raise ValueError("KYC legal form conflicts with the case")
    if verification.status != "passed":
        return {
            "status": "not_verified",
            "provider_status": verification.status,
            "evidence_ids": [],
        }
    if not verification.identity_verified:
        return {
            "status": "not_verified",
            "provider_status": "identity_not_verified",
            "evidence_ids": [],
        }

    origin_id = f"kyc:{verification.source_id}:{verification.session_id}"
    common = {
        "db_path": db_path,
        "application_id": application_id,
        "owner_actor": owner_actor,
        "source_id": verification.source_id,
        "origin_id": origin_id,
        "verification_method": "provider_hosted_kyc_result",
        "consent_id": consent_id,
        "observed_at": verification.observed_at,
        "expires_at": verification.expires_at,
        "created_by": actor,
        "metadata": {
            "provider_session_id": verification.session_id,
            "provider_status": verification.status,
            "legal_form": verification.legal_form,
        },
    }
    records = [register_verified_evidence(
        **common,
        evidence_type=IDENTITY_TYPE,
        subject_key="applicant_person",
        subject_hash=verification.identity_subject_hash,
        source_reference=f"{verification.session_id}:identity",
    )]

    expected_authority = AUTHORITY_BY_LEGAL_FORM[legal_form]
    supplied_authority = str(verification.authority_evidence_type or "").strip()
    if supplied_authority:
        if supplied_authority != expected_authority:
            raise ValueError("KYC authority result is not valid for the case legal form")
        records.append(register_verified_evidence(
            **common,
            evidence_type=expected_authority,
            subject_key="applicant_business",
            subject_hash=verification.business_subject_hash,
            source_reference=f"{verification.session_id}:authority",
        ))

    if verification.beneficial_owner_verified:
        records.append(register_verified_evidence(
            **common,
            evidence_type="beneficial_owner_verified",
            subject_key="applicant_business",
            subject_hash=verification.business_subject_hash,
            source_reference=f"{verification.session_id}:beneficial-owner",
        ))

    return {
        "status": "verified_evidence_registered",
        "provider_status": verification.status,
        "evidence_ids": [record["evidence_id"] for record in records],
        "duplicate": all(record["duplicate"] for record in records),
        "authority_verified": any(
            record["evidence_type"] == expected_authority for record in records
        ),
        "requires_human_credit_decision": True,
    }
