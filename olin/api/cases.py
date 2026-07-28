"""Canonical case application service for the Olin shadow MVP."""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from dataclasses import asdict
from typing import Any

from ..config import is_production
from ..graduation import get_graduation_offer
from ..models import (
    Application,
    BankData,
    BuroData,
    BusinessType,
    FMCGData,
    FraudData,
    IMSSPayrollData,
    MapsRatingData,
    POSData,
    TenureData,
)
from ..portfolio import check_portfolio
from ..scorecard import score_application
from ..store import ScoringLog

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
    ) if pos_raw else None

    maps_raw = sub("maps")
    maps = MapsRatingData(
        rating=float(maps_raw.get("rating", 0)),
        review_count=int(maps_raw.get("review_count", 0)),
        review_velocity_6m=int(maps_raw.get("review_velocity_6m", 0)),
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
    ) if bureau_raw else None

    fraud_raw = sub("fraud")
    fraud = FraudData(
        phone_mx=str(fraud_raw.get("phone_mx", "")),
        rfc=str(fraud_raw.get("rfc", "")),
        curp=str(fraud_raw.get("curp", "")),
        ine_checked=boolean(fraud_raw, "ine_checked"),
        address_stated=str(fraud_raw.get("address_stated", "")),
    ) if fraud_raw else None

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
    )


def validate_submission_metadata(body: dict[str, Any]) -> None:
    """Fail closed on pilot identity, consent and mode metadata."""
    consent = body.get("consent") or {}
    if not isinstance(consent, dict):
        raise ValueError("consent must be a JSON object")
    supplied = bool(consent.get("channel") or consent.get("text"))
    if supplied:
        channel = str(consent.get("channel", "")).strip().lower()
        text = str(consent.get("text", "")).strip()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError(
                "consent.channel must be whatsapp, sms, or in_person"
            )
        if not text:
            raise ValueError("consent.text is required when consent is supplied")
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
    if is_production():
        if case_mode != "shadow":
            raise ValueError("case_mode must be shadow in production pilot")
        if not supplied:
            raise ValueError("consent is required in production")
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


def format_score_result(app: Application, result: Any) -> dict[str, Any]:
    """Return the stable API representation of a newly scored case."""
    repayment = result.repayment
    return {
        "application_id": result.application_id,
        "merchant_name": result.merchant_name,
        "score": round(result.score, 2),
        "ci_low": round(result.ci_low, 2),
        "ci_high": round(result.ci_high, 2),
        "tier": result.tier,
        "recommendation": result.decision.value,
        # Kept during the compatibility window for existing clients.
        "decision": result.decision.value,
        "amount_evaluated_mxn": result.approved_amount_mxn,
        "approved_amount_mxn": result.approved_amount_mxn,
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
    }


def record_submission_metadata(
    log: ScoringLog,
    application_id: str,
    body: dict[str, Any],
    actor: str,
) -> None:
    consent = body.get("consent") or {}
    if consent.get("channel") or consent.get("text"):
        log.record_consent(
            application_id,
            str(consent.get("channel", "")),
            str(consent.get("text", "")),
            actor=actor,
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


def create_case(
    body: dict[str, Any],
    db_path: str,
    actor: str,
) -> dict[str, Any]:
    """Create, score and persist one case through the canonical workflow."""
    validate_submission_metadata(body)
    app = build_application(body)
    portfolio = check_portfolio(app, db_path)
    graduation = get_graduation_offer(app.clabe or "", db_path)
    result = score_application(
        app,
        portfolio_block=portfolio,
        graduation=graduation,
    )
    with ScoringLog(db_path) as log:
        log.log(app, result)
        record_submission_metadata(
            log,
            result.application_id,
            body,
            actor=actor,
        )
    return format_score_result(app, result)


def get_case(
    db_path: str,
    application_id: str,
    owner_actor: str | None = None,
) -> dict[str, Any] | None:
    with closing(sqlite3.connect(db_path)) as conn:
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
    return {
        "application_id": row["application_id"],
        "merchant_name": row["merchant_name"],
        "score": row["score"],
        "tier": row["tier"],
        "recommendation": row["decision"],
        "decision": row["decision"],
        "amount_evaluated_mxn": row["approved_mxn"],
        "approved_amount_mxn": row["approved_mxn"],
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
        "evidence": {
            "bank": raw_application.get("bank"),
            "fmcg": raw_application.get("fmcg"),
            "bureau": raw_application.get("buro"),
            "identity": raw_application.get("fraud"),
            "tenure": raw_application.get("tenure"),
            "pos": raw_application.get("pos"),
            "maps": raw_application.get("maps"),
            "imss": raw_application.get("imss"),
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


def list_cases(
    db_path: str,
    owner_actor: str | None = None,
) -> list[dict[str, Any]]:
    """Build the analyst queue from persisted cases, newest first."""
    with closing(sqlite3.connect(db_path)) as conn:
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
        }
        case["mitigation_menu"] = None
        cases.append(case)
    return cases
