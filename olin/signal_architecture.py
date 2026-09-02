"""Olin 28-signal evidence architecture for heterogeneous Mexican SMEs.

This module implements the signal catalogue described in the June 2026 deck,
including the POS signal omitted from the deck's 27 enumerated rows.  It does
not replace the calibrated bank policy or make an official credit decision.
Every indicator is a transparent, versioned heuristic until outcome data
supports empirical calibration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import Application, ExternalSignalEvidence
from .evidence_governance import evidence_governance, governance_summary


ENGINE_VERSION = "alternative-signals-1.0.0"
DECISION_USE = "context_only_not_default_probability"


@dataclass(frozen=True)
class SignalDefinition:
    signal_id: str
    label: str
    layer_id: str
    layer_label: str
    pdf_weight: float | None
    phase: str
    source_strategy: str
    metric_schema: tuple[str, ...]
    applicable_segments: tuple[str, ...] = ()
    limitation: str = "Designed heuristic; requires outcome validation."


L1 = "financial_transactional"
L2 = "geospatial_intelligence"
L3 = "business_permanence"
L4 = "behavioral_psychometric"
L5 = "payment_rails"
L6 = "external_macro"

LAYER_LABELS = {
    L1: "Financial & Transactional",
    L2: "Geospatial Intelligence",
    L3: "Business Permanence & Survival",
    L4: "Behavioral & Psychometric",
    L5: "Payment Rail Signals",
    L6: "External & Macro",
}

INVENTORY_SEGMENTS = (
    "abarrotes", "jugueria", "taqueria", "restaurant", "retail",
    "wholesale", "light_manufacturing", "agriculture", "hospitality",
    "healthcare",
    "pharmacy",
)
LOCATION_SEGMENTS = (
    "abarrotes", "jugueria", "taqueria", "restaurant", "retail",
    "wholesale", "services", "health_beauty", "transport",
    "light_manufacturing", "construction", "agriculture", "hospitality",
    "education", "healthcare", "pharmacy", "logistics",
)
WEATHER_SEGMENTS = (
    "agriculture", "transport", "logistics", "construction", "hospitality",
    "restaurant", "taqueria", "jugueria", "retail", "abarrotes",
)


def _d(
    signal_id: str,
    label: str,
    layer: str,
    weight: float | None,
    phase: str,
    source: str,
    metrics: tuple[str, ...],
    applicable: tuple[str, ...] = (),
    limitation: str = "Designed heuristic; requires outcome validation.",
) -> SignalDefinition:
    return SignalDefinition(
        signal_id, label, layer, LAYER_LABELS[layer], weight, phase, source,
        metrics, applicable, limitation,
    )


SIGNAL_DEFINITIONS: tuple[SignalDefinition, ...] = (
    _d("fmcg_purchase_volume", "Supplier purchase volume", L1, .06, "P1",
       "Distributor feed or verified invoices", ("avg_weekly_purchase_mxn", "months_of_history", "trend_3m"), INVENTORY_SEGMENTS),
    _d("fmcg_cadence", "Supplier purchase cadence", L1, .08, "P1",
       "Distributor feed or verified invoices", ("weekly_purchase_rate", "missed_weeks_last_12"), INVENTORY_SEGMENTS),
    _d("fmcg_supplier_diversity", "Supplier diversity", L1, .04, "P1",
       "Multiple distributor feeds or verified invoices", ("supplier_count", "top_supplier_share"), INVENTORY_SEGMENTS),
    _d("bank_cash_flow_snapshot", "Bank cash-flow snapshot", L1, .07, "P0",
       "Syncfy, bank API, or controlled statement review", ("months_connected", "deposit_regularity", "overdrafts_90d", "monthly_deposit_volume_mxn")),
    _d("bank_flow_90d_trend", "Bank-flow 90-day trend", L1, .05, "P1",
       "Syncfy or bank transaction feed", ("balance_trend_90d", "min_daily_balance_mxn")),
    _d("pos_transaction_volume", "POS transaction volume", L1, None, "P0",
       "Acquirer, PSP, or bank settlement feed", ("months_of_history", "volume_consistency", "trend_3m", "avg_monthly_volume_mxn"),
       limitation="Present in the original six-signal model but omitted from the deck's 27-row table; no 28-signal weight was specified."),
    _d("zone_commerce_density", "Zone commerce density", L2, .04, "P1",
       "INEGI DENUE radius query", ("establishment_count", "radius_m", "same_activity_count"), LOCATION_SEGMENTS),
    _d("foot_traffic_delta", "Foot-traffic delta", L2, .04, "P1",
       "Bank or merchant-authorized mobility/footfall provider", ("foot_traffic_change_90d",), LOCATION_SEGMENTS,
       "Google Places does not expose a supported historical Popular Times API; requires an authorized alternative source."),
    _d("neighborhood_permanence", "Neighborhood permanence index", L2, .05, "P1",
       "Derived from DENUE snapshots and authorized public aggregates", ("active_business_change_12m", "closure_rate_12m", "employment_change_12m"), LOCATION_SEGMENTS),
    _d("night_time_light_trend", "Night-time light trend", L2, .03, "P2",
       "NASA/NOAA VIIRS dataset pipeline", ("radiance_change_12m",), LOCATION_SEGMENTS),
    _d("neighborhood_closure_rate", "Neighborhood closure rate", L2, .02, "P2",
       "Versioned DENUE snapshots", ("closure_rate_12m", "comparison_count"), LOCATION_SEGMENTS),
    _d("business_age_category_risk", "Business age by category", L3, .05, "P0",
       "Documentary continuity, Google openingDate when available, and bank records", ("years_in_operation", "category_benchmark_years")),
    _d("google_maps_activity", "Google Maps activity", L3, .04, "P1",
       "Google Places live display", ("rating", "review_count", "recent_review_sample_count"), LOCATION_SEGMENTS,
       "Google returns at most a small relevance-ranked review sample; activity is supporting evidence only."),
    _d("hours_consistency", "Operating-hours consistency", L3, .04, "P1",
       "Repeated Google Places observations or merchant operating records", ("scheduled_hours_weekly", "observed_open_ratio"), LOCATION_SEGMENTS),
    _d("whatsapp_business_verification", "WhatsApp business-account evidence", L3, .03, "P0",
       "Consented first-party WhatsApp onboarding", ("business_account_present", "phone_matches_application"),
       limitation="A WhatsApp business account is not independent legal-entity verification."),
    _d("commercial_neighbor_ecosystem", "Commercial-neighbor ecosystem", L3, .02, "P2",
       "INEGI DENUE radius query and versioned snapshots", ("active_neighbor_count", "complementary_business_count", "closure_rate_12m"), LOCATION_SEGMENTS),
    _d("psychometric_conscientiousness", "Conscientiousness questionnaire", L4, .04, "P0",
       "Consented first-party questionnaire", ("questionnaire_score", "answered_count"),
       limitation="Must be validated for the target population and reviewed for adverse impact before decision use."),
    _d("psychometric_integrity", "Integrity questionnaire", L4, .03, "P0",
       "Consented first-party questionnaire", ("scenario_score", "answered_count"),
       limitation="Self-reported psychometrics are context only until independently validated."),
    _d("whatsapp_response_time", "Onboarding response time", L4, .03, "P0",
       "Consented Olin message metadata", ("median_response_minutes", "response_count"),
       limitation="Response speed may reflect connectivity or accessibility, not repayment willingness."),
    _d("onboarding_message_timing", "Onboarding timing consistency", L4, .02, "P0",
       "Consented Olin message metadata", ("within_declared_hours_ratio", "message_count"),
       limitation="Time-of-day is not proof that an applicant is physically at the business."),
    _d("onboarding_consistency", "Onboarding answer consistency", L4, .02, "P0",
       "Olin application validation", ("contradiction_count", "fields_compared")),
    _d("codi_dimo_frequency", "CoDi/DiMo transaction frequency", L5, .04, "P1",
       "Contracted bank, PSP, or consented aggregation feed", ("monthly_transaction_count", "regularity"),
       limitation="Banco de Mexico aggregate information is not merchant-level transaction evidence."),
    _d("oxxo_pay_deposit_frequency", "OXXO/Spin deposit frequency", L5, .03, "P1",
       "Contracted Spin/OXXO or consented wallet feed", ("monthly_deposit_count", "regularity"),
       limitation="Requires a commercial or consented provider relationship; no public merchant-history API is assumed."),
    _d("spei_inbound_regularity", "SPEI inbound regularity", L5, .03, "P1",
       "Syncfy or bank transaction feed with transaction-type classification", ("monthly_inbound_count", "regularity")),
    _d("weather_risk", "Weather exposure", L6, .04, "P0",
       "Open-Meteo historical/forecast API", ("extreme_weather_days_30d", "temperature_anomaly_c", "precipitation_anomaly_pct"), WEATHER_SEGMENTS,
       "Weather sensitivity is sector-specific and must not be used as a universal penalty."),
    _d("fmcg_inflation_proxy", "Input-price inflation pressure", L6, .03, "P1",
       "INEGI price-index series", ("relevant_inflation_yoy", "estimated_margin_pct"), INVENTORY_SEGMENTS),
    _d("imss_payroll_trajectory", "Payroll trajectory", L6, .02, "P1",
       "Consented payroll/tax evidence or bank-provided records", ("employee_count", "employee_change_12m"),
       limitation="Public IMSS releases are aggregated and cannot identify a specific employer without authorized evidence."),
    _d("seasonal_adjustment", "Sector seasonal adjustment", L6, .01, "P1",
       "Bank-flow history plus versioned sector calendar", ("observed_to_expected_revenue_ratio", "history_months")),
)

BY_ID = {definition.signal_id: definition for definition in SIGNAL_DEFINITIONS}
SIGNAL_IDS = frozenset(BY_ID)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _num(metrics: dict[str, Any], name: str) -> float | None:
    value = metrics.get(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(metrics: dict[str, Any], name: str) -> bool | None:
    value = metrics.get(name)
    return value if isinstance(value, bool) else None


def _fmcg_volume(m: dict[str, Any]) -> tuple[float | None, str]:
    months, trend = _num(m, "months_of_history"), _num(m, "trend_3m")
    if months is None or trend is None:
        return None, "Purchase history depth and trend are required"
    return _clamp(min(months / 18, 1) * 60 + (trend + 1) / 2 * 40), "History depth and recent purchase trend"


def _fmcg_cadence(m: dict[str, Any]) -> tuple[float | None, str]:
    cadence, missed = _num(m, "weekly_purchase_rate"), _num(m, "missed_weeks_last_12")
    if cadence is None or missed is None:
        return None, "Weekly cadence and missed weeks are required"
    return _clamp(cadence * 100 - missed * 7), "Restock regularity less recent gaps"


def _supplier_diversity(m: dict[str, Any]) -> tuple[float | None, str]:
    count, top = _num(m, "supplier_count"), _num(m, "top_supplier_share")
    if count is None:
        return None, "Supplier count is required"
    penalty = max(0.0, (top or 0.0) - .5) * 80
    return _clamp(min(count, 4) / 4 * 100 - penalty), "Supplier count adjusted for concentration"


def _bank_snapshot(m: dict[str, Any]) -> tuple[float | None, str]:
    regularity, overdrafts, months = _num(m, "deposit_regularity"), _num(m, "overdrafts_90d"), _num(m, "months_connected")
    if regularity is None or overdrafts is None or months is None:
        return None, "Bank history, regularity, and overdrafts are required"
    return _clamp(regularity * 65 + min(months / 12, 1) * 35 - overdrafts * 8), "Deposit regularity, history depth, and overdrafts"


def _bank_trend(m: dict[str, Any]) -> tuple[float | None, str]:
    trend = _num(m, "balance_trend_90d")
    return (None, "90-day balance trend is required") if trend is None else (_clamp(50 + trend * 50), "Direction of the 90-day balance trend")


def _pos_volume(m: dict[str, Any]) -> tuple[float | None, str]:
    consistency, trend, months = _num(m, "volume_consistency"), _num(m, "trend_3m"), _num(m, "months_of_history")
    if consistency is None or trend is None or months is None:
        return None, "POS history, consistency, and trend are required"
    return _clamp(consistency * 55 + min(months / 12, 1) * 30 + trend * 15 + 15), "POS settlement consistency, history, and trend"


def _zone_density(m: dict[str, Any]) -> tuple[float | None, str]:
    count, same, radius = _num(m, "establishment_count"), _num(m, "same_activity_count"), _num(m, "radius_m")
    if count is None or same is None or not radius:
        return None, "Establishment counts and radius are required"
    density = count / max(1.0, 3.14159 * (radius / 1000) ** 2)
    diversity = 1 - min(1.0, same / max(count, 1))
    return _clamp(min(density / 500, 1) * 60 + diversity * 40), "Commercial density and same-activity concentration"


def _single_delta(m: dict[str, Any], key: str, label: str) -> tuple[float | None, str]:
    delta = _num(m, key)
    return (None, f"{label} is required") if delta is None else (_clamp(50 + delta * 100), label)


def _neighborhood_permanence(m: dict[str, Any]) -> tuple[float | None, str]:
    active, closure, employment = _num(m, "active_business_change_12m"), _num(m, "closure_rate_12m"), _num(m, "employment_change_12m")
    if active is None or closure is None:
        return None, "Business-stock change and closure rate are required"
    return _clamp(55 + active * 80 - closure * 100 + (employment or 0) * 30), "Business-stock, closure, and employment trends"


def _closure_rate(m: dict[str, Any]) -> tuple[float | None, str]:
    rate, count = _num(m, "closure_rate_12m"), _num(m, "comparison_count")
    if rate is None or count is None:
        return None, "Closure rate and comparison count are required"
    return _clamp((1 - rate) * 100 * min(count / 20, 1)), "Observed survival rate adjusted for sample depth"


def _business_age(m: dict[str, Any]) -> tuple[float | None, str]:
    years, benchmark = _num(m, "years_in_operation"), _num(m, "category_benchmark_years")
    if years is None:
        return None, "Documented years in operation are required"
    return _clamp(years / max(benchmark or 5, 1) * 75 + 25), "Tenure relative to a configurable category benchmark"


def _maps_activity(m: dict[str, Any]) -> tuple[float | None, str]:
    rating, count, recent = _num(m, "rating"), _num(m, "review_count"), _num(m, "recent_review_sample_count")
    if rating is None or count is None:
        return None, "Rating and review count are required"
    score = max(0, rating - 3) / 2 * 55 + min(count / 100, 1) * 35 + min((recent or 0) / 5, 1) * 10
    return _clamp(score), "Rating and visible review activity"


def _hours_consistency(m: dict[str, Any]) -> tuple[float | None, str]:
    observed = _num(m, "observed_open_ratio")
    return (None, "Repeated open/closed observations are required") if observed is None else (_clamp(observed * 100), "Share of observations consistent with declared hours")


def _whatsapp_business(m: dict[str, Any]) -> tuple[float | None, str]:
    business, phone = _bool(m, "business_account_present"), _bool(m, "phone_matches_application")
    if business is None or phone is None:
        return None, "Business-account and phone-match observations are required"
    return (100.0 if business and phone else 50.0 if phone else 0.0), "Account type and applicant phone consistency"


def _neighbor_ecosystem(m: dict[str, Any]) -> tuple[float | None, str]:
    active, complementary, closure = _num(m, "active_neighbor_count"), _num(m, "complementary_business_count"), _num(m, "closure_rate_12m")
    if active is None or complementary is None:
        return None, "Active and complementary neighbor counts are required"
    score = min(active / 50, 1) * 45 + min(complementary / 15, 1) * 35 + (1 - (closure or 0)) * 20
    return _clamp(score), "Active, complementary, and surviving nearby businesses"


def _questionnaire(m: dict[str, Any], score_key: str, minimum: int, reason: str) -> tuple[float | None, str]:
    score, answered = _num(m, score_key), _num(m, "answered_count")
    if score is None or answered is None or answered < minimum:
        return None, reason
    return _clamp(score * 100 if score <= 1 else score), "First-party result; unvalidated for credit use"


def _response_time(m: dict[str, Any]) -> tuple[float | None, str]:
    minutes, count = _num(m, "median_response_minutes"), _num(m, "response_count")
    if minutes is None or count is None or count < 2:
        return None, "At least two response observations are required"
    return _clamp(100 - min(minutes, 1440) / 14.4), "Median consented response time"


def _message_timing(m: dict[str, Any]) -> tuple[float | None, str]:
    ratio, count = _num(m, "within_declared_hours_ratio"), _num(m, "message_count")
    if ratio is None or count is None or count < 2:
        return None, "Declared-hours ratio and at least two messages are required"
    return _clamp(ratio * 100), "Share of messages within declared business hours"


def _onboarding_consistency(m: dict[str, Any]) -> tuple[float | None, str]:
    contradictions, fields = _num(m, "contradiction_count"), _num(m, "fields_compared")
    if contradictions is None or not fields:
        return None, "Compared fields and contradiction count are required"
    return _clamp((1 - contradictions / fields) * 100), "Cross-source answer consistency"


def _payment_frequency(m: dict[str, Any], count_key: str) -> tuple[float | None, str]:
    count, regularity = _num(m, count_key), _num(m, "regularity")
    if count is None or regularity is None:
        return None, "Monthly frequency and regularity are required"
    return _clamp(min(count / 20, 1) * 40 + regularity * 60), "Frequency and temporal regularity"


def _weather(m: dict[str, Any]) -> tuple[float | None, str]:
    days, temp, precip = _num(m, "extreme_weather_days_30d"), _num(m, "temperature_anomaly_c"), _num(m, "precipitation_anomaly_pct")
    if days is None:
        return None, "Extreme-weather days are required"
    penalty = days * 3 + abs(temp or 0) * 4 + min(abs(precip or 0), 100) * .15
    return _clamp(100 - penalty), "Sector-context weather exposure, not a borrower trait"


def _inflation(m: dict[str, Any]) -> tuple[float | None, str]:
    inflation, margin = _num(m, "relevant_inflation_yoy"), _num(m, "estimated_margin_pct")
    if inflation is None:
        return None, "Relevant annual input inflation is required"
    buffer = max(0.0, (margin or 0) - inflation)
    return _clamp(50 - inflation * 2 + buffer * 2), "Input inflation relative to estimated margin buffer"


def _payroll(m: dict[str, Any]) -> tuple[float | None, str]:
    employees, change = _num(m, "employee_count"), _num(m, "employee_change_12m")
    if employees is None or change is None:
        return None, "Current payroll and 12-month change are required"
    return _clamp(50 + change * 100 + min(employees, 20)), "Authorized payroll trajectory; zero employees is not automatically adverse"


def _seasonality(m: dict[str, Any]) -> tuple[float | None, str]:
    ratio, months = _num(m, "observed_to_expected_revenue_ratio"), _num(m, "history_months")
    if ratio is None or months is None or months < 12:
        return None, "At least 12 months and an expected-season ratio are required"
    return _clamp(100 - abs(1 - ratio) * 100), "Observed revenue relative to the sector-season expectation"


INDICATOR_EVALUATORS = {
    "fmcg_purchase_volume": _fmcg_volume,
    "fmcg_cadence": _fmcg_cadence,
    "fmcg_supplier_diversity": _supplier_diversity,
    "bank_cash_flow_snapshot": _bank_snapshot,
    "bank_flow_90d_trend": _bank_trend,
    "pos_transaction_volume": _pos_volume,
    "zone_commerce_density": _zone_density,
    "foot_traffic_delta": lambda m: _single_delta(m, "foot_traffic_change_90d", "Observed 90-day footfall change"),
    "neighborhood_permanence": _neighborhood_permanence,
    "night_time_light_trend": lambda m: _single_delta(m, "radiance_change_12m", "VIIRS 12-month radiance change"),
    "neighborhood_closure_rate": _closure_rate,
    "business_age_category_risk": _business_age,
    "google_maps_activity": _maps_activity,
    "hours_consistency": _hours_consistency,
    "whatsapp_business_verification": _whatsapp_business,
    "commercial_neighbor_ecosystem": _neighbor_ecosystem,
    "psychometric_conscientiousness": lambda m: _questionnaire(m, "questionnaire_score", 5, "A complete five-question response is required"),
    "psychometric_integrity": lambda m: _questionnaire(m, "scenario_score", 3, "Three completed scenario responses are required"),
    "whatsapp_response_time": _response_time,
    "onboarding_message_timing": _message_timing,
    "onboarding_consistency": _onboarding_consistency,
    "codi_dimo_frequency": lambda m: _payment_frequency(m, "monthly_transaction_count"),
    "oxxo_pay_deposit_frequency": lambda m: _payment_frequency(m, "monthly_deposit_count"),
    "spei_inbound_regularity": lambda m: _payment_frequency(m, "monthly_inbound_count"),
    "weather_risk": _weather,
    "fmcg_inflation_proxy": _inflation,
    "imss_payroll_trajectory": _payroll,
    "seasonal_adjustment": _seasonality,
}


def _indicator(signal_id: str, metrics: dict[str, Any]) -> tuple[float | None, str]:
    """Return a transparent 0-100 operational indicator, never PD."""
    return INDICATOR_EVALUATORS[signal_id](metrics)


def _core_evidence(app: Application, signal_id: str) -> ExternalSignalEvidence | None:
    now = ""
    if signal_id in {"fmcg_purchase_volume", "fmcg_cadence"} and app.fmcg:
        metrics = {
            "avg_weekly_purchase_mxn": app.fmcg.avg_weekly_purchase_mxn,
            "months_of_history": app.fmcg.months_of_history,
            "trend_3m": app.fmcg.trend_3m,
            "weekly_purchase_rate": app.fmcg.weekly_purchase_rate,
            "missed_weeks_last_12": app.fmcg.missed_weeks_last_12,
        }
        return ExternalSignalEvidence(metrics, app.fmcg.source, app.fmcg.verified, app.fmcg.evidence_reference, app.fmcg.observed_at)
    if signal_id in {"bank_cash_flow_snapshot", "bank_flow_90d_trend"} and app.bank:
        metrics = {
            "months_connected": app.bank.months_connected,
            "deposit_regularity": app.bank.deposit_regularity,
            "overdrafts_90d": app.bank.overdrafts_90d,
            "monthly_deposit_volume_mxn": app.bank.monthly_deposit_volume_mxn,
            "balance_trend_90d": app.bank.balance_trend_90d,
            "min_daily_balance_mxn": app.bank.min_daily_balance_mxn,
        }
        return ExternalSignalEvidence(metrics, app.bank.source, app.bank.verified, app.bank.evidence_reference, app.bank.observed_at)
    if signal_id == "pos_transaction_volume" and app.pos:
        metrics = {
            "months_of_history": app.pos.months_of_history,
            "volume_consistency": app.pos.volume_consistency,
            "trend_3m": app.pos.trend_3m,
            "avg_monthly_volume_mxn": app.pos.avg_monthly_volume_mxn,
        }
        return ExternalSignalEvidence(metrics, app.pos.source, app.pos.verified, app.pos.evidence_reference, app.pos.observed_at)
    if signal_id == "business_age_category_risk" and app.tenure:
        metrics = {"years_in_operation": max(app.tenure.years_on_google_maps, app.tenure.years_in_imss), "category_benchmark_years": 5.0}
        return ExternalSignalEvidence(metrics, "documented_continuity", False, "", now)
    if signal_id == "google_maps_activity" and app.maps:
        metrics = {"rating": app.maps.rating, "review_count": app.maps.review_count, "recent_review_sample_count": app.maps.review_velocity_6m}
        return ExternalSignalEvidence(metrics, app.maps.source, app.maps.verified, app.maps.evidence_reference, app.maps.observed_at)
    if signal_id == "imss_payroll_trajectory" and app.imss and app.imss.registered_employees is not None:
        return ExternalSignalEvidence({"employee_count": app.imss.registered_employees}, "application_record", False, "", now)
    return None


def _confidence(evidence: ExternalSignalEvidence, status: str) -> str:
    if status not in {"observed", "partial"}:
        return "none"
    if evidence.verified and evidence.evidence_reference and evidence.observed_at:
        return "high"
    if evidence.verified and evidence.evidence_reference:
        return "medium"
    return "low"


def _combined_evidence(
    definition: SignalDefinition,
    core: ExternalSignalEvidence | None,
    supplied: ExternalSignalEvidence | None,
) -> ExternalSignalEvidence | None:
    """Prefer complete evidence and never let a weaker block hide canonical data."""
    required = set(definition.metric_schema)
    supplied_complete = bool(supplied and required.issubset(supplied.metrics))
    core_complete = bool(core and required.issubset(core.metrics))
    if supplied_complete and supplied and supplied.verified:
        return supplied
    if core_complete and core and core.verified:
        return core
    if core_complete and core:
        return core
    if supplied_complete and supplied:
        return supplied
    if core and supplied:
        metrics = dict(core.metrics)
        metrics.update(supplied.metrics)
        return ExternalSignalEvidence(
            metrics=metrics,
            source=f"{core.source}+{supplied.source}",
            verified=core.verified and supplied.verified,
            evidence_reference=" | ".join(
                item for item in (core.evidence_reference, supplied.evidence_reference)
                if item
            ),
            observed_at=supplied.observed_at or core.observed_at,
        )
    return supplied or core


def evaluate_signal_architecture(app: Application) -> dict[str, Any]:
    """Evaluate all 28 signals without modifying the legacy recommendation."""
    business_type = app.business_type.value
    evaluations: list[dict[str, Any]] = []
    for definition in SIGNAL_DEFINITIONS:
        supplied = app.signal_evidence.get(definition.signal_id)
        core = _core_evidence(app, definition.signal_id)
        evidence = _combined_evidence(definition, core, supplied)
        applicable = not definition.applicable_segments or business_type in definition.applicable_segments
        if not applicable and evidence is None:
            status, indicator, rationale = "not_applicable", None, "Not a core signal for this SME segment"
            evidence = ExternalSignalEvidence()
        elif evidence is None:
            status, indicator, rationale = "missing", None, f"Requires {definition.source_strategy}"
            evidence = ExternalSignalEvidence()
        else:
            indicator, rationale = _indicator(definition.signal_id, evidence.metrics)
            status = "observed" if indicator is not None else "partial"
        evaluations.append({
            "signal_id": definition.signal_id,
            "label": definition.label,
            "layer_id": definition.layer_id,
            "layer_label": definition.layer_label,
            "status": status,
            "applicable": applicable,
            "indicator_score": round(indicator, 1) if indicator is not None else None,
            "indicator_meaning": rationale,
            "confidence": _confidence(evidence, status),
            "source": evidence.source,
            "source_strategy": definition.source_strategy,
            "verified": evidence.verified,
            "evidence_reference": evidence.evidence_reference,
            "observed_at": evidence.observed_at,
            "metrics": dict(evidence.metrics),
            "pdf_weight": definition.pdf_weight,
            "phase": definition.phase,
            "decision_use": DECISION_USE,
            "limitation": definition.limitation,
            "governance": evidence_governance(
                definition.signal_id,
                verified=evidence.verified,
                evidence_reference=evidence.evidence_reference,
            ),
        })

    applicable_rows = [row for row in evaluations if row["status"] != "not_applicable"]
    observed = [row for row in applicable_rows if row["status"] in {"observed", "partial"}]
    verified = [row for row in observed if row["verified"] and row["evidence_reference"]]
    layers = []
    for layer_id, label in LAYER_LABELS.items():
        rows = [row for row in evaluations if row["layer_id"] == layer_id]
        relevant = [row for row in rows if row["status"] != "not_applicable"]
        layer_observed = [row for row in relevant if row["status"] in {"observed", "partial"}]
        layers.append({
            "layer_id": layer_id,
            "label": label,
            "signal_count": len(rows),
            "applicable_count": len(relevant),
            "observed_count": len(layer_observed),
            "coverage": round(len(layer_observed) / len(relevant), 3) if relevant else 1.0,
        })
    return {
        "engine_version": ENGINE_VERSION,
        "business_type": business_type,
        "decision_use": DECISION_USE,
        "predictive_model": False,
        "signal_count": len(evaluations),
        "applicable_count": len(applicable_rows),
        "observed_count": len(observed),
        "verified_count": len(verified),
        "coverage": round(len(observed) / len(applicable_rows), 3) if applicable_rows else 1.0,
        "verified_coverage": round(len(verified) / len(applicable_rows), 3) if applicable_rows else 1.0,
        "layers": layers,
        "governance": governance_summary(),
        "signals": evaluations,
        "warnings": [
            "Indicator scores are designed heuristics, not probabilities of default",
            "Missing signals are never treated as favorable and do not increase the legacy score",
            "The bank retains the official credit decision",
        ],
    }


def signal_catalog(
    filter_text: str = "",
    limit: int = 28,
    offset: int = 0,
) -> dict[str, Any]:
    query = str(filter_text or "").strip().lower()
    matched = [
        definition for definition in SIGNAL_DEFINITIONS
        if not query or query in " ".join((
            definition.signal_id,
            definition.label,
            definition.layer_id,
            definition.layer_label,
            definition.source_strategy,
        )).lower()
    ]
    bounded_limit = max(1, min(int(limit), 28))
    bounded_offset = max(0, int(offset))
    selected = matched[bounded_offset:bounded_offset + bounded_limit]
    return {
        "engine_version": ENGINE_VERSION,
        "signal_count": len(selected),
        "total_signal_count": len(SIGNAL_DEFINITIONS),
        "decision_use": DECISION_USE,
        "signals": [asdict(definition) for definition in selected],
        "meta": {
            "matched": len(matched),
            "limit": bounded_limit,
            "offset": bounded_offset,
        },
    }
