"""Three deterministic, internally coherent cases for the isolated demo."""
from __future__ import annotations

from copy import deepcopy

from .cases import create_case
from ..store import ScoringLog


CONSENT_TEXT = (
    "Autorizo el uso de mis datos exclusivamente para esta demostración "
    "sintética del piloto sombra de Olin."
)


SYNTHETIC_CASES = [
    {
        "merchant_name": "Abarrotes La Esperanza",
        "business_type": "abarrotes",
        "requested_mxn": 20_000,
        "colonia": "Iztapalapa",
        "case_mode": "shadow",
        "cohort_id": "demo_sintetica_01",
        "partner_case_reference": "SYN-001",
        "consent": {"channel": "in_person", "text": CONSENT_TEXT},
        "bank": {
            "months_connected": 12,
            "avg_daily_balance_mxn": 24_000,
            "min_daily_balance_mxn": 10_000,
            "monthly_deposit_count": 28,
            "monthly_deposit_volume_mxn": 112_000,
            "monthly_outflow_volume_mxn": 58_000,
            "deposit_regularity": 0.93,
            "overdrafts_90d": 0,
            "balance_trend_90d": 0.12,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-BANK-001",
        },
        "fmcg": {
            "months_of_history": 24,
            "weekly_purchase_rate": 0.98,
            "missed_weeks_last_12": 0,
            "avg_weekly_purchase_mxn": 9_200,
            "distributor_confirmed": True,
            "trend_3m": 0.11,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-FMCG-001",
        },
        "tenure": {
            "years_on_google_maps": 9,
            "years_in_imss": 5,
            "address_consistent": True,
        },
        "pos": {
            "months_of_history": 18,
            "avg_monthly_volume_mxn": 48_000,
            "volume_consistency": 0.91,
            "trend_3m": 0.08,
        },
        "maps": {
            "rating": 4.7,
            "review_count": 126,
            "review_velocity_6m": 11,
        },
        "buro": {
            "checked": True,
            "active_delinquencies": 0,
            "active_loans_count": 1,
            "worst_mob_status": "01",
            "score": 720,
        },
        "fraud": {
            "phone_mx": "5511111111",
            "rfc": "SYN850101AB1",
            "curp": "",
            "ine_checked": True,
            "address_stated": "Iztapalapa, CDMX",
        },
    },
    {
        "merchant_name": "Abarrotes San Miguel",
        "business_type": "abarrotes",
        "requested_mxn": 30_000,
        "colonia": "Gustavo A. Madero",
        "case_mode": "shadow",
        "cohort_id": "demo_sintetica_01",
        "partner_case_reference": "SYN-002",
        "consent": {"channel": "whatsapp", "text": CONSENT_TEXT},
        "bank": {
            "months_connected": 8,
            "avg_daily_balance_mxn": 11_000,
            "min_daily_balance_mxn": 2_800,
            "monthly_deposit_count": 18,
            "monthly_deposit_volume_mxn": 68_000,
            "monthly_outflow_volume_mxn": 43_000,
            "deposit_regularity": 0.72,
            "overdrafts_90d": 1,
            "balance_trend_90d": -0.04,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-BANK-002",
        },
        "fmcg": {
            "months_of_history": 14,
            "weekly_purchase_rate": 0.82,
            "missed_weeks_last_12": 2,
            "avg_weekly_purchase_mxn": 6_100,
            "distributor_confirmed": True,
            "trend_3m": -0.03,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-FMCG-002",
        },
        "tenure": {
            "years_on_google_maps": 5,
            "years_in_imss": 0,
            "address_consistent": True,
        },
        "maps": {
            "rating": 4.2,
            "review_count": 39,
            "review_velocity_6m": 3,
        },
        "buro": {
            "checked": True,
            "active_delinquencies": 0,
            "active_loans_count": 2,
            "worst_mob_status": "01",
            "score": 632,
        },
        "fraud": {
            "phone_mx": "5522222222",
            "rfc": "SYN860202AB2",
            "curp": "",
            "ine_checked": True,
            "address_stated": "Gustavo A. Madero, CDMX",
        },
    },
    {
        "merchant_name": "Abarrotes La Unión",
        "business_type": "abarrotes",
        "requested_mxn": 25_000,
        "colonia": "Ecatepec",
        "case_mode": "shadow",
        "cohort_id": "demo_sintetica_01",
        "partner_case_reference": "SYN-003",
        "consent": {"channel": "sms", "text": CONSENT_TEXT},
        "bank": {
            "months_connected": 4,
            "avg_daily_balance_mxn": 2_200,
            "min_daily_balance_mxn": -3_800,
            "monthly_deposit_count": 9,
            "monthly_deposit_volume_mxn": 31_000,
            "monthly_outflow_volume_mxn": 30_200,
            "deposit_regularity": 0.38,
            "overdrafts_90d": 5,
            "balance_trend_90d": -0.42,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-BANK-003",
        },
        "fmcg": {
            "months_of_history": 5,
            "weekly_purchase_rate": 0.48,
            "missed_weeks_last_12": 6,
            "avg_weekly_purchase_mxn": 2_900,
            "distributor_confirmed": False,
            "trend_3m": -0.36,
            "source": "synthetic",
            "verified": True,
            "evidence_reference": "SYN-FMCG-003",
        },
        "tenure": {
            "years_on_google_maps": 1.4,
            "years_in_imss": 0,
            "address_consistent": False,
        },
        "maps": {
            "rating": 3.7,
            "review_count": 9,
            "review_velocity_6m": 1,
        },
        "buro": {
            "checked": True,
            "active_delinquencies": 1,
            "active_loans_count": 4,
            "worst_mob_status": "04",
            "score": 558,
        },
        "fraud": {
            "phone_mx": "5533333333",
            "rfc": "SYN870303AB3",
            "curp": "",
            "ine_checked": True,
            "address_stated": "Ecatepec, Estado de México",
        },
    },
]


def seed_synthetic_demo(db_path: str) -> list[dict]:
    """Seed an empty demo DB through the same service used by partner intake."""
    with ScoringLog(db_path) as log:
        if log.conn.execute("SELECT COUNT(*) FROM scoring_log").fetchone()[0]:
            return []
    created = [
        create_case(deepcopy(payload), db_path, actor="sistema_demo")
        for payload in SYNTHETIC_CASES
    ]
    # The third case demonstrates a completed comparison.  The first two remain
    # actionable for the five-minute analyst walkthrough.
    with ScoringLog(db_path) as log:
        log.record_partner_outcome(
            created[2]["application_id"],
            "declined",
            "La institución confirma capacidad insuficiente.",
            actor="analista_demo",
        )
    return created


def demo_scenarios() -> list[dict]:
    """Return safe payloads that the demo intake can load in the browser."""
    return [
        {
            "id": payload["partner_case_reference"],
            "title": payload["merchant_name"],
            "payload": deepcopy(payload),
        }
        for payload in SYNTHETIC_CASES
    ]
