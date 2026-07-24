"""
Olin Credit Scoring MVP - Signal sub-scores
Each function maps raw signal data to 0..100 with a plain-language explanation.
Returns (score, explanation) or (None, reason) when the signal is unusable.
Every rule here must be explainable to the borrower and the CNBV.
"""
from __future__ import annotations

from typing import Optional, Tuple

from .models import (
    FMCGData, BankData, TenureData, POSData, MapsRatingData, IMSSPayrollData,
)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1. FMCG purchase history (25%)
# ---------------------------------------------------------------------------

def score_fmcg(d: Optional[FMCGData]) -> Tuple[Optional[float], str]:
    if d is None or d.months_of_history < 1:
        return None, "No distributor purchase history available"

    # History depth: 18+ months = full credit
    history = _clamp(d.months_of_history / 18 * 100)
    # Cadence: buying every week is the strongest operating-business signal
    cadence = _clamp(d.weekly_purchase_rate * 100)
    # Missed restocks = early stress signal, penalize hard
    gaps_penalty = min(40.0, d.missed_weeks_last_12 * 8.0)
    # Trend bonus/malus
    trend = d.trend_3m * 10.0

    score = _clamp(0.35 * history + 0.65 * cadence - gaps_penalty + trend)
    expl = (
        f"{d.months_of_history:.0f} months of purchase history, "
        f"{d.weekly_purchase_rate * 100:.0f}% weekly restock cadence, "
        f"{d.missed_weeks_last_12} missed weeks in last 12"
    )
    return score, expl


# ---------------------------------------------------------------------------
# 2. Bank cash flow via Syncfy (25%)
# ---------------------------------------------------------------------------

def score_bank(d: Optional[BankData]) -> Tuple[Optional[float], str]:
    if d is None or d.months_connected <= 0:
        return None, "No bank data: not on a Syncfy-covered bank and no manual upload"

    regularity = _clamp(d.deposit_regularity * 100)
    # Deposit frequency: 20+ deposits/month = healthy daily-cash business
    frequency = _clamp(d.monthly_deposit_count / 20 * 100)
    overdraft_penalty = min(30.0, d.overdrafts_90d * 10.0)
    trend = d.balance_trend_90d * 10.0

    score = _clamp(0.5 * regularity + 0.5 * frequency - overdraft_penalty + trend)

    # Manual uploads and Spin/OXXO data are less verifiable: 15% haircut
    # Direct API connections (belvo, syncfy) get full weight.
    fallback = None
    _TRUSTED_SOURCES = {"belvo", "syncfy"}
    if d.source not in _TRUSTED_SOURCES:
        score *= 0.85
        fallback = d.source

    expl = (
        f"{d.monthly_deposit_count:.0f} deposits/month, "
        f"regularity {d.deposit_regularity:.2f}, "
        f"{d.overdrafts_90d} overdrafts in 90d, source: {d.source}"
    )
    return score, expl


# ---------------------------------------------------------------------------
# 3. Business tenure (20%)
# ---------------------------------------------------------------------------

def score_tenure(d: Optional[TenureData]) -> Tuple[Optional[float], str]:
    if d is None:
        return None, "No tenure data from Google Maps or IMSS"

    years = max(d.years_on_google_maps, d.years_in_imss)
    if years <= 0:
        return None, "Business not found on Google Maps or IMSS"

    # Default risk drops sharply after year 5. 10y = ~92, 5y = 75, 2y = 40.
    if years >= 10:
        base = 92.0
    elif years >= 5:
        base = 75.0 + (years - 5) / 5 * 17.0
    elif years >= 2:
        base = 40.0 + (years - 2) / 3 * 35.0
    else:
        base = years / 2 * 40.0

    if not d.address_consistent:
        base -= 15.0  # location mismatch across sources

    expl = f"{years:.1f} years in operation (Maps/IMSS), address consistent: {d.address_consistent}"
    return _clamp(base), expl


# ---------------------------------------------------------------------------
# 4. POS transaction volume (15%) - weighted signal, never a hard filter
# ---------------------------------------------------------------------------

def score_pos(d: Optional[POSData]) -> Tuple[Optional[float], str]:
    if d is None or d.months_of_history < 1:
        # Cash-only merchant: signal missing, weight gets redistributed
        return None, "Cash-only merchant, no POS terminal (28% of CDMX segment)"

    consistency = _clamp(d.volume_consistency * 100)
    history = _clamp(d.months_of_history / 12 * 100)
    trend = d.trend_3m * 15.0  # trend matters more than volume

    score = _clamp(0.55 * consistency + 0.45 * history + trend)
    expl = (
        f"{d.months_of_history:.0f} months of Clip history, "
        f"MXN {d.avg_monthly_volume_mxn:,.0f}/month, "
        f"consistency {d.volume_consistency:.2f}, trend {d.trend_3m:+.2f}"
    )
    return score, expl


# ---------------------------------------------------------------------------
# 5. Google Maps rating (10%)
# ---------------------------------------------------------------------------

def score_maps(d: Optional[MapsRatingData]) -> Tuple[Optional[float], str]:
    if d is None or d.review_count == 0:
        return None, "No Google Maps reviews"

    # Rating quality: 4.5+ = excellent, below 3.5 = warning
    rating_score = _clamp((d.rating - 3.0) / 2.0 * 100)
    # Volume credibility: 100+ reviews = community anchor
    volume_score = _clamp(d.review_count / 100 * 100)
    # Recent activity: active customer base
    velocity_bonus = min(10.0, d.review_velocity_6m * 1.0)

    score = _clamp(0.6 * rating_score + 0.4 * volume_score + velocity_bonus)
    expl = f"{d.rating:.1f} stars, {d.review_count} reviews, {d.review_velocity_6m} new in 6m"
    return score, expl


# ---------------------------------------------------------------------------
# 6. IMSS payroll (5%) - zero employees is neutral, not negative
# ---------------------------------------------------------------------------

def score_imss(d: Optional[IMSSPayrollData]) -> Tuple[Optional[float], str]:
    if d is None or d.registered_employees is None:
        return None, "IMSS payroll status unknown"

    n = d.registered_employees
    if n == 0:
        return 50.0, "No registered employees (neutral, typical for segment)"
    score = _clamp(50.0 + min(n, 10) * 5.0)
    return score, f"{n} registered IMSS employees (formality multiplier)"
