"""Evidence Passport v2: case-bound, consent-bound evidence routing.

The passport never verifies a payload merely because a caller says it is
verified. Evidence is registered server-side after a trusted provider or
controlled review produces an attested record. The passport then tells a
partner which evidence route is complete or what can be supplied next. It is
not a credit decision, KYC service, bureau authorization, or loan offer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .models import BusinessType
from .source_trust import assess_source


ENGINE_VERSION = "evidence-passport-2.0.0"
DECISION_USE = "verified_evidence_routing_for_human_partner_review_only"
LEGAL_FORMS = frozenset({"individual_business_owner", "legal_entity"})


@dataclass(frozen=True)
class EvidenceRoute:
    route_id: str
    label: str
    proves: str
    accepted_evidence: tuple[str, ...]
    minimum_independent_sources: int
    eligible_business_types: tuple[str, ...] = ()
    limitation: str = "Requires partner verification and bank policy approval."


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    evidence_type: str
    source_id: str
    origin_id: str
    subject_key: str
    subject_hash: str
    verification_method: str
    source_reference: str
    attestation_id: str
    consent_id: str
    observed_at: str
    expires_at: str


IDENTITY_TYPE = "government_identity_verified"
AUTHORITY_BY_LEGAL_FORM = {
    "individual_business_owner": "individual_business_ownership_verified",
    "legal_entity": "legal_representative_authority_verified",
}

# The registry stores hashes, never underlying RFC/CURP/document/account values.
EVIDENCE_SUBJECT_KEYS = {
    IDENTITY_TYPE: "applicant_person",
    "individual_business_ownership_verified": "applicant_business",
    "legal_representative_authority_verified": "applicant_business",
    "beneficial_owner_verified": "applicant_business",
    "account_holder_match": "applicant_business",
    "verified_bank_feed": "applicant_business",
    "partner_bank_feature_contract": "applicant_business",
    "verified_pos_settlements": "applicant_business",
    "verified_marketplace_settlements": "applicant_business",
    "verified_cfdi_feed": "applicant_business",
    "sat_authorized_fiscal_feed": "applicant_business",
    "verified_supplier_feed": "applicant_business",
    "supplier_confirmed_invoices": "applicant_business",
    "buyer_confirmed_invoices": "applicant_business",
    "verified_receivables_ledger": "applicant_business",
    "cash_sales_log_observed": "applicant_business",
    "site_visit_verified": "applicant_business",
    "inventory_count_verified": "applicant_business",
    "denue_match": "applicant_business",
    "google_places_match": "applicant_business",
    "lease_or_utility_match": "applicant_business",
    "supplier_relationship_confirmed": "applicant_business",
    "historical_supplier_records": "applicant_business",
    "historical_settlements": "applicant_business",
    "historical_bank_activity": "applicant_business",
    "dated_lease_or_tax_records": "applicant_business",
    "collateral_title_verified": "collateral_asset",
    "collateral_valuation_verified": "collateral_asset",
    "security_interest_perfection_verified": "collateral_asset",
    "insurance_verified": "collateral_asset",
}


CAPACITY_ROUTES: tuple[EvidenceRoute, ...] = (
    EvidenceRoute(
        "bank_flow_led", "Flujo bancario",
        "Entradas, salidas, saldos, deuda observada y variación",
        ("verified_bank_feed", "partner_bank_feature_contract"), 1,
        limitation="Una carga manual sin verificación sirve para revisión, no para automatización.",
    ),
    EvidenceRoute(
        "tpv_led", "Liquidaciones TPV o plataforma",
        "Ventas liquidadas, devoluciones, concentración y tendencia",
        ("verified_pos_settlements", "verified_marketplace_settlements"), 1,
        eligible_business_types=(
            "restaurant", "taqueria", "jugueria", "retail", "ecommerce",
            "hospitality", "health_beauty", "services", "healthcare",
        ),
        limitation="Debe cubrir suficiente actividad; las ventas en efectivo permanecen faltantes.",
    ),
    EvidenceRoute(
        "fiscal_led", "CFDI y evidencia fiscal",
        "Ingresos facturados, gastos, clientes y continuidad",
        ("verified_cfdi_feed", "sat_authorized_fiscal_feed"), 1,
        limitation="La facturación puede no capturar todas las ventas y debe reconciliarse con cobros.",
    ),
    EvidenceRoute(
        "supplier_led", "Compras a proveedores",
        "Cadencia, volumen, continuidad e inventario aproximado",
        ("verified_supplier_feed", "supplier_confirmed_invoices"), 1,
        eligible_business_types=(
            "abarrotes", "retail", "wholesale", "pharmacy", "restaurant",
            "taqueria", "jugueria", "light_manufacturing", "agriculture",
        ),
        limitation="Las compras prueban actividad, no ventas ni margen.",
    ),
    EvidenceRoute(
        "receivables_led", "Facturas y cuentas por cobrar",
        "Ventas B2B, concentración, antigüedad y cobro",
        ("buyer_confirmed_invoices", "verified_receivables_ledger"), 1,
        eligible_business_types=(
            "professional", "construction", "services", "wholesale",
            "light_manufacturing", "transport", "logistics",
        ),
        limitation="Una factura no prueba cobro; se requiere confirmación o liquidación histórica.",
    ),
    EvidenceRoute(
        "cash_business_observed", "Negocio intensivo en efectivo",
        "Actividad y capacidad aproximada mediante triangulación",
        (
            "cash_sales_log_observed", "supplier_confirmed_invoices",
            "site_visit_verified", "inventory_count_verified",
        ), 3,
        limitation="Sólo comité, límites conservadores y tres orígenes independientes.",
    ),
)


SUPPORTING_EVIDENCE = {
    "business_existence": (
        "denue_match", "google_places_match", "lease_or_utility_match",
        "site_visit_verified", "supplier_relationship_confirmed",
    ),
    "continuity": (
        "historical_supplier_records", "historical_settlements",
        "historical_bank_activity", "dated_lease_or_tax_records",
    ),
    "authority_context_not_authority": (
        "beneficial_owner_verified", "account_holder_match",
    ),
    "collateral": (
        "collateral_title_verified", "collateral_valuation_verified",
        "security_interest_perfection_verified", "insurance_verified",
    ),
}


def evidence_catalog() -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "decision_use": DECISION_USE,
        "legal_forms": sorted(LEGAL_FORMS),
        "non_substitutable": {
            "identity": [IDENTITY_TYPE],
            "consent": ["active_case_consent_from_system_of_record"],
            "authority": AUTHORITY_BY_LEGAL_FORM,
        },
        "capacity_routes": [asdict(route) for route in CAPACITY_ROUTES],
        "supporting_evidence": SUPPORTING_EVIDENCE,
        "record_requirements": [
            "case and tenant binding", "active purpose-specific consent",
            "trusted source attestation", "source reference", "independent origin",
            "subject hash", "observation and expiry timestamps",
        ],
        "guardrails": [
            "No evidence route is a loan approval or offer.",
            "A caller cannot self-assert that evidence is verified.",
            "Account ownership and beneficial ownership do not prove authority to act.",
            "Collateral cannot replace identity, consent, authority, or repayment capacity.",
            "Public web and registry data can support existence but not prove revenue.",
            "Cash-observed cases remain committee-only.",
        ],
    }


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _clean_identifier(value: object, field: str, maximum: int = 240) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or len(cleaned) > maximum:
        raise ValueError(f"{field} is required and must be at most {maximum} characters")
    return cleaned


def register_verified_evidence(
    db_path: str,
    *,
    application_id: str,
    owner_actor: str,
    evidence_type: str,
    source_id: str,
    origin_id: str,
    subject_key: str,
    subject_hash: str,
    verification_method: str,
    source_reference: str,
    consent_id: str,
    observed_at: str,
    expires_at: str,
    created_by: str,
    metadata: Mapping[str, Any] | None = None,
    evidence_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Register evidence after a trusted adapter has verified it.

    This is deliberately not a partner-facing HTTP route. Signed provider
    webhooks or controlled bank-review adapters call it after their own checks.
    """
    evidence_type = _clean_identifier(evidence_type, "evidence_type", 100).lower()
    expected_subject = EVIDENCE_SUBJECT_KEYS.get(evidence_type)
    if not expected_subject:
        raise ValueError("evidence_type is not supported by Evidence Passport")
    if subject_key != expected_subject:
        raise ValueError(f"{evidence_type} must use subject_key={expected_subject}")
    subject_hash = str(subject_hash or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", subject_hash):
        raise ValueError("subject_hash must be a 64-character SHA-256 hex digest")

    source_id = _clean_identifier(source_id, "source_id", 120).lower()
    trust = assess_source(source_id, evidence_type)
    if not trust.trusted:
        raise PermissionError(f"source is not trusted for {evidence_type}: {trust.reason}")

    observed = _parse_timestamp(observed_at, "observed_at")
    expires = _parse_timestamp(expires_at, "expires_at")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed > current:
        raise ValueError("observed_at cannot be in the future")
    if expires <= current or expires <= observed:
        raise ValueError("expires_at must be after observed_at and in the future")

    application_id = _clean_identifier(application_id, "application_id", 120)
    owner_actor = _clean_identifier(owner_actor, "owner_actor", 120)
    consent_id = _clean_identifier(consent_id, "consent_id", 120)
    origin_id = _clean_identifier(origin_id, "origin_id", 160)
    source_reference = _clean_identifier(source_reference, "source_reference", 240)
    verification_method = _clean_identifier(verification_method, "verification_method", 160)
    created_by = _clean_identifier(created_by, "created_by", 120)
    record_id = _clean_identifier(evidence_id or uuid4().hex, "evidence_id", 120)
    metadata_digest = sha256(json.dumps(
        dict(metadata or {}), sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()

    from .store import ScoringLog
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        case = log.conn.execute(
            "SELECT owner_actor FROM scoring_log WHERE application_id=?", (application_id,),
        ).fetchone()
        if not case:
            raise LookupError("Application not found")
        case_owner = str(case[0] or "")
        if not case_owner or case_owner != owner_actor:
            raise PermissionError("Evidence owner does not match the case tenant")
        consent = log.conn.execute(
            "SELECT 1 FROM consent_record WHERE consent_id=? AND application_id=? "
            "AND purpose='credit_assessment' AND status='active'",
            (consent_id, application_id),
        ).fetchone()
        if not consent:
            raise PermissionError("Evidence requires active case consent")
        existing = log.conn.execute(
            "SELECT * FROM evidence_record WHERE source_id=? AND source_reference=?",
            (source_id, source_reference),
        ).fetchone()
        if existing:
            replay_fields = {
                "application_id": application_id,
                "owner_actor": owner_actor,
                "evidence_type": evidence_type,
                "origin_id": origin_id,
                "subject_key": subject_key,
                "subject_hash": subject_hash,
                "verification_method": verification_method,
                "attestation_id": trust.attestation_id,
                "consent_id": consent_id,
                "observed_at": observed.isoformat(),
                "expires_at": expires.isoformat(),
                "metadata_sha256": metadata_digest,
                "status": "verified",
            }
            if any(str(existing[key]) != str(value) for key, value in replay_fields.items()):
                raise ValueError("source_reference replay conflicts with the stored evidence record")
            return {
                "evidence_id": str(existing["evidence_id"]), "status": "verified",
                "evidence_type": evidence_type, "source_id": source_id,
                "attestation_id": trust.attestation_id,
                "expires_at": expires.isoformat(), "duplicate": True,
            }
        try:
            log.conn.execute(
                "INSERT INTO evidence_record "
                "(evidence_id,application_id,owner_actor,evidence_type,source_id,origin_id,"
                "subject_key,subject_hash,verification_method,source_reference,attestation_id,"
                "consent_id,status,observed_at,expires_at,metadata_sha256,created_at,created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id, application_id, owner_actor, evidence_type, source_id,
                    origin_id, subject_key, subject_hash, verification_method,
                    source_reference, trust.attestation_id, consent_id, "verified",
                    observed.isoformat(), expires.isoformat(), metadata_digest,
                    current.isoformat(), created_by,
                ),
            )
        except Exception:
            log.conn.rollback()
            raise
        log._append_audit(application_id, "evidence_registered", created_by, {
            "evidence_id": record_id, "evidence_type": evidence_type,
            "source_id": source_id, "origin_id": origin_id,
            "subject_key": subject_key, "subject_hash": subject_hash,
            "source_reference": source_reference, "attestation_id": trust.attestation_id,
            "consent_id": consent_id, "observed_at": observed.isoformat(),
            "expires_at": expires.isoformat(), "metadata_sha256": metadata_digest,
        })
        log.conn.commit()
    return {
        "evidence_id": record_id, "status": "verified",
        "evidence_type": evidence_type, "source_id": source_id,
        "attestation_id": trust.attestation_id, "expires_at": expires.isoformat(),
        "duplicate": False,
    }


def revoke_evidence(
    db_path: str, *, application_id: str, evidence_id: str,
    owner_actor: str, reason: str, actor: str,
) -> dict[str, str]:
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise ValueError("revocation reason must contain at least 5 characters")
    when = datetime.now(timezone.utc).isoformat()
    from .store import ScoringLog
    with ScoringLog(db_path) as log:
        cursor = log.conn.execute(
            "UPDATE evidence_record SET status='revoked',revoked_at=?,revocation_reason=? "
            "WHERE evidence_id=? AND application_id=? AND owner_actor=? AND status='verified'",
            (when, reason[:1000], evidence_id, application_id, owner_actor),
        )
        if cursor.rowcount != 1:
            log.conn.rollback()
            raise LookupError("Verified evidence record not found")
        log._append_audit(application_id, "evidence_revoked", actor, {
            "evidence_id": evidence_id, "reason": reason[:1000],
        })
        log.conn.commit()
    return {"evidence_id": evidence_id, "status": "revoked", "revoked_at": when}


def _record_from_row(row: Any) -> EvidenceRecord:
    return EvidenceRecord(**{
        field: str(row[field]) for field in EvidenceRecord.__dataclass_fields__
    })


def _assess(
    business_type: str,
    legal_form: str,
    records: Iterable[EvidenceRecord],
    *,
    consent_active: bool,
    invalid_records: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    try:
        normalized_type = BusinessType(str(business_type).strip().lower()).value
    except ValueError as exc:
        raise ValueError("business_type is not supported") from exc
    legal_form = str(legal_form or "").strip().lower()
    if legal_form not in LEGAL_FORMS:
        raise ValueError("legal_form must be individual_business_owner or legal_entity")
    records = list(records)
    invalid_records = list(invalid_records or [])

    subject_values: dict[str, set[str]] = {}
    for record in records:
        subject_values.setdefault(record.subject_key, set()).add(record.subject_hash)
    conflicts = [
        {"subject_key": key, "distinct_subject_hashes": len(values)}
        for key, values in sorted(subject_values.items()) if len(values) > 1
    ]

    types_present = {record.evidence_type for record in records}
    required_authority = AUTHORITY_BY_LEGAL_FORM[legal_form]
    hard_gaps: list[str] = []
    if IDENTITY_TYPE not in types_present:
        hard_gaps.append("identity")
    if not consent_active:
        hard_gaps.append("consent")
    if required_authority not in types_present:
        hard_gaps.append("authority")

    route_results = []
    for route in CAPACITY_ROUTES:
        if route.eligible_business_types and normalized_type not in route.eligible_business_types:
            continue
        matched = [r for r in records if r.evidence_type in route.accepted_evidence]
        present_types = sorted({record.evidence_type for record in matched})
        independent_origins = sorted({record.origin_id for record in matched})
        independent_count = min(len(present_types), len(independent_origins))
        missing_count = max(0, route.minimum_independent_sources - independent_count)
        route_results.append({
            **asdict(route), "present_evidence_types": present_types,
            "independent_origin_count": len(independent_origins),
            "missing_count": missing_count, "ready": missing_count == 0,
            "next_options": [item for item in route.accepted_evidence if item not in present_types],
        })

    ready_routes = [item for item in route_results if item["ready"]]
    if invalid_records:
        status = "BLOCKED_EVIDENCE_INTEGRITY"
    elif conflicts:
        status = "BLOCKED_SUBJECT_CONFLICT"
    elif hard_gaps:
        status = "BLOCKED_NON_SUBSTITUTABLE_CONTROL"
    elif ready_routes:
        status = "READY_FOR_HUMAN_PARTNER_REVIEW"
    else:
        status = "BUILD_EVIDENCE_FIRST"
    ranked = sorted(
        route_results,
        key=lambda item: (item["missing_count"], len(item["next_options"]), item["route_id"]),
    )
    supporting_types = {
        evidence_type for values in SUPPORTING_EVIDENCE.values() for evidence_type in values
    }
    return {
        "engine_version": ENGINE_VERSION, "decision_use": DECISION_USE,
        "business_type": normalized_type, "legal_form": legal_form, "status": status,
        "verified_record_count": len(records), "hard_control_gaps": hard_gaps,
        "hard_control_requirements": {
            "identity": IDENTITY_TYPE,
            "consent": "active_case_consent_from_system_of_record",
            "authority": required_authority,
        },
        "invalid_records": invalid_records, "subject_conflicts": conflicts,
        "ready_routes": [item["route_id"] for item in ready_routes],
        "routes": route_results,
        "recommended_next_routes": ranked[:3],
        "supporting_only": sorted(types_present.intersection(supporting_types)),
        "collateral_note": (
            "Collateral is loss-mitigation evidence only after title, valuation, "
            "perfection and insurance checks; it does not prove repayment capacity."
        ),
        "requires_human_credit_decision": True,
    }


def assess_evidence_passport(
    business_type: str,
    evidence_records: Iterable[EvidenceRecord],
    *,
    legal_form: str,
    consent_active: bool,
) -> dict[str, Any]:
    """Pure assessment interface for already validated server records."""
    records = list(evidence_records)
    if any(not isinstance(record, EvidenceRecord) for record in records):
        raise ValueError("Evidence Passport requires server-registered EvidenceRecord objects")
    return _assess(business_type, legal_form, records, consent_active=consent_active)


def assess_case_evidence_passport(
    db_path: str,
    *,
    application_id: str,
    evidence_ids: Iterable[str],
    legal_form: str,
    owner_actor: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve IDs server-side and assess only current, trusted case evidence."""
    application_id = _clean_identifier(application_id, "application_id", 120)
    raw_ids = list(evidence_ids)
    if any(not isinstance(item, str) for item in raw_ids):
        raise ValueError("every evidence_id must be a string")
    ids = [item.strip() for item in raw_ids]
    if not ids or len(ids) > 100 or any(not item or len(item) > 120 for item in ids):
        raise ValueError("evidence_ids must contain between 1 and 100 non-empty IDs")
    if len(set(ids)) != len(ids):
        raise ValueError("evidence_ids must not contain duplicates")
    legal_form = str(legal_form or "").strip().lower()
    if legal_form not in LEGAL_FORMS:
        raise ValueError("legal_form must be individual_business_owner or legal_entity")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    from .store import ScoringLog
    with ScoringLog(db_path) as log:
        if not getattr(log.conn, "is_postgres", False):
            log.conn.row_factory = sqlite3.Row
        case = log.conn.execute(
            "SELECT business_type,owner_actor FROM scoring_log WHERE application_id=? "
            "AND (? IS NULL OR owner_actor=?)",
            (application_id, owner_actor, owner_actor),
        ).fetchone()
        if not case:
            raise LookupError("Application not found")
        case_owner = str(case[1] or "")
        active_consents = {
            str(row[0]) for row in log.conn.execute(
                "SELECT consent_id FROM consent_record WHERE application_id=? "
                "AND purpose='credit_assessment' AND status='active'", (application_id,),
            ).fetchall()
        }
        placeholders = ",".join("?" for _ in ids)
        rows = log.conn.execute(
            "SELECT * FROM evidence_record WHERE application_id=? AND owner_actor=? "
            f"AND evidence_id IN ({placeholders})", (application_id, case_owner, *ids),
        ).fetchall()

    by_id = {str(row["evidence_id"]): row for row in rows}
    valid: list[EvidenceRecord] = []
    invalid: list[dict[str, str]] = []
    for evidence_id in ids:
        row = by_id.get(evidence_id)
        if row is None:
            invalid.append({"evidence_id": evidence_id, "reason": "not_found_or_not_accessible"})
            continue
        reason = ""
        if str(row["status"]) != "verified":
            reason = "revoked"
        else:
            try:
                if _parse_timestamp(str(row["expires_at"]), "expires_at") <= current:
                    reason = "expired"
            except ValueError:
                reason = "invalid_expiry"
        if not reason and str(row["consent_id"]) not in active_consents:
            reason = "consent_not_active"
        trust = assess_source(str(row["source_id"]), str(row["evidence_type"]))
        if not reason and not trust.trusted:
            reason = f"source_not_currently_trusted:{trust.reason}"
        if not reason and str(row["attestation_id"]) != trust.attestation_id:
            reason = "source_attestation_changed"
        if reason:
            invalid.append({"evidence_id": evidence_id, "reason": reason})
        else:
            valid.append(_record_from_row(row))

    result = _assess(
        str(case[0]), legal_form, valid,
        consent_active=bool(active_consents), invalid_records=invalid,
    )
    result["application_id"] = application_id
    result["requested_record_count"] = len(ids)
    return result
