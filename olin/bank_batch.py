"""Controlled batch intake for a bank-provided historical shadow cohort."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
import re
from pathlib import Path
from typing import Any

from .api.cases import build_application, create_case, validate_data_authorization
from .api.cases import validate_submission_metadata
from .config import is_production
from .production_preflight import assert_production_preflight
from .store import ScoringLog


SCHEMA_VERSION = "olin-bank-shadow-batch-1.0"
HISTORICAL_CLASSIFICATIONS = frozenset({
    "pseudonymized_historical", "identifiable_historical",
})
FORBIDDEN_KEYS = frozenset({
    "password", "passwords", "credential", "credentials", "transaction",
    "transactions", "rawtransaction", "rawtransactions", "accesstoken",
    "refreshtoken", "privatekey", "secret", "secrets",
})


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            current = f"{path}.{key}"
            if _normalized_key(key) in FORBIDDEN_KEYS:
                found.append(current)
            found.extend(_find_forbidden_keys(nested, current))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_find_forbidden_keys(nested, f"{path}[{index}]"))
    return found


def canonical_batch_sha256(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def validate_bank_batch(payload: Any) -> dict[str, Any]:
    """Validate and normalize a maximum ten-case historical batch in memory."""
    if not isinstance(payload, dict):
        raise ValueError("Bank batch must be a JSON object")
    forbidden = _find_forbidden_keys(payload)
    if forbidden:
        raise ValueError("Forbidden raw credential/transaction fields: " + ", ".join(forbidden[:5]))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    batch_id = str(payload.get("batch_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,80}", batch_id):
        raise ValueError("batch_id must be 8-80 safe characters")
    cohort_id = str(payload.get("cohort_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,80}", cohort_id):
        raise ValueError("cohort_id must be 3-80 safe characters")
    institution_reference = str(payload.get("institution_reference", "")).strip()
    if not 5 <= len(institution_reference) <= 160:
        raise ValueError("institution_reference must be 5-160 characters")
    classification = str(payload.get("data_classification", "")).strip().lower()
    if classification not in HISTORICAL_CLASSIFICATIONS:
        raise ValueError(
            "Batch intake is historical only; prospective cases must use the hosted intake flow"
        )
    configured_classification = os.getenv("OLIN_DATA_CLASSIFICATION", "").strip().lower()
    if is_production() and configured_classification != classification:
        raise ValueError("Batch data_classification does not match the deployed environment")
    authorization = validate_data_authorization(payload.get("data_authorization"))
    if not authorization:
        raise ValueError("A documented data_authorization is required for a historical batch")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10:
        raise ValueError("cases must contain between 1 and 10 records")

    normalized_cases: list[dict[str, Any]] = []
    references: set[str] = set()
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be a JSON object")
        case = deepcopy(item)
        case["case_mode"] = "shadow"
        case["cohort_id"] = cohort_id
        case["data_authorization"] = deepcopy(authorization)
        reference = str(case.get("partner_case_reference", "")).strip()
        if not reference:
            raise ValueError(f"cases[{index}].partner_case_reference is required")
        if reference in references:
            raise ValueError(f"Duplicate partner_case_reference: {reference}")
        references.add(reference)
        validate_submission_metadata(case)
        build_application(case)
        normalized_cases.append(case)
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "cohort_id": cohort_id,
        "institution_reference": institution_reference,
        "data_classification": classification,
        "data_authorization": authorization,
        "cases": normalized_cases,
        "case_count": len(normalized_cases),
    }


def load_bank_batch(path: str | Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    source = Path(path)
    raw = source.read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError("Bank batch exceeds the 5 MB pilot limit")
    digest = canonical_batch_sha256(raw)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256.lower()):
        raise ValueError("expected_sha256 must be a SHA-256 hex digest")
    if digest != expected_sha256.lower():
        raise ValueError("Bank batch checksum does not match the approved transfer manifest")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Bank batch must be UTF-8 JSON") from exc
    return validate_bank_batch(payload), digest


def import_bank_batch(batch: dict[str, Any], db_path: str, actor: str) -> dict[str, Any]:
    """Persist a prevalidated batch; return identifiers and never echo source rows."""
    assert_production_preflight(db_path)
    actor = str(actor).strip()
    if not actor:
        raise ValueError("actor is required")
    with ScoringLog(db_path) as log:
        existing = {
            row[0] for row in log.conn.execute(
                "SELECT partner_case_reference FROM scoring_log WHERE owner_actor=? "
                "AND partner_case_reference IS NOT NULL",
                (actor,),
            ).fetchall()
        }
    collisions = sorted(
        str(case["partner_case_reference"])
        for case in batch["cases"]
        if str(case["partner_case_reference"]) in existing
    )
    if collisions:
        raise ValueError("Batch contains previously imported references: " + ", ".join(collisions))

    created: list[dict[str, str]] = []
    for case in batch["cases"]:
        result = create_case(case, db_path, actor)
        with ScoringLog(db_path) as log:
            log._append_audit(result["application_id"], "bank_batch_case_imported", actor, {
                "batch_id": batch["batch_id"],
                "cohort_id": batch["cohort_id"],
                "institution_reference": batch["institution_reference"],
                "data_classification": batch["data_classification"],
            })
            log.conn.commit()
        created.append({
            "application_id": result["application_id"],
            "partner_case_reference": str(case["partner_case_reference"]),
        })
    return {
        "batch_id": batch["batch_id"],
        "cohort_id": batch["cohort_id"],
        "case_count": len(created),
        "created": created,
        "status": "imported",
    }
