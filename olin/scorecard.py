"""
Olin V2 — 3-Dimension Tier Decision Engine (Círculo de Crédito edition)

Decision is driven by a (Círculo × DSCR × Score) matrix that produces a
single tier number 1–14 and maps it to AUTO_APPROVE / COMMITTEE / DECLINE.

Bureau provider: Círculo de Crédito (circulodecredito.com.mx).
See BUREAU_PROVIDER / CIRCULO_HIGH_BAND / CIRCULO_MID_BAND constants below.

# CALIBRATION REQUIRED: score-band thresholds (670 / 600) must be
# recalibrated after the first 30 repayment outcomes. Refit using observed
# default rates per band; do not adjust before 30 labelled loans exist.

Dimensions
──────────
  Círculo C1 = score ≥ 670              (high band, full auto-approve eligibility)
          C2 = score 600–669            (mid band, COMMITTEE ceiling — never AUTO)
          C3 = no file / unchecked      (thin-file, COMMITTEE ceiling — never AUTO)
          C4 = score < 600 OR delinquency > 0  (always DECLINE)

  DSCR    D1 = high  (≥ 2.5, no repayment downgrades)
          D2 = mid   (1.5–2.5, OR ≥ 2.5 with soft downgrades)
          D3 = low   (< 1.5, OR any repayment hard-decline)
          All 5 repayment filters feed into this band.

  Score   S1 = high  (75+)
          S2 = mid   (50–74)
          S3 = low   (< 50)

Tier map
────────
  Tier  1  C1·D1·S1  →  AUTO_APPROVE   (only path to auto)
  Tier  2  C1·D1·S2  →  COMMITTEE
  Tier  3  C1·D2·S1  →  COMMITTEE
  Tier  4  C1·D2·S2  →  COMMITTEE
  Tier  5  C2·D1·S1  →  COMMITTEE      ← mid-band score = COMMITTEE ceiling
  Tier  6  C2·D1·S2  →  COMMITTEE
  Tier  7  C2·D2·S1  →  COMMITTEE
  Tier  8  C2·D2·S2  →  COMMITTEE
  Tier  9  C3·D1·S1  →  COMMITTEE      ← thin-file = COMMITTEE ceiling
  Tier 10  C3·D1·S2  →  COMMITTEE
  Tier 11  C3·D2·S1  →  COMMITTEE
  Tier 12  C3·D2·S2  →  COMMITTEE
  Tier 13  C4·*·*    →  DECLINE        (bad bureau: <600 or delinquent)
           *·D3·*    →  DECLINE        (can't repay — DSCR hard fail)
           *·*·S3    →  DECLINE        (score below floor)
  Tier 14  —         →  DECLINE        (pre-gate: fraud / portfolio block)

Phase 0 guards on Tier 1 (AUTO_APPROVE)
────────────────────────────────────────
  If any of the following apply, matrix Tier 1 is preserved but decision routes to COMMITTEE:
    • Phase 0 hard-filter failures (tenure, FMCG, Maps)
    • CI low < 70
    • Data coverage < 60 %
    • Fraud risk score ≥ 30
"""
from __future__ import annotations

import random
from typing import Callable, Optional, Tuple

from .models import (
    Application, BuroData, Decision, GraduationOffer, PortfolioBlock,
    RepaymentAssessment, ScoreResult, SignalScore,
)
from . import signals as sig
from .repayment import (
    MIN_DSCR_AUTO, MIN_DSCR_HARD, assess_repayment, suggest_max_affordable_amount,
)
from .fraud import assess_fraud
from .config import is_production, is_synthetic_source, runtime_mode

# Default weights (used for BusinessType.OTHER and as fallback)
WEIGHTS: dict[str, float] = {
    "fmcg_purchase_history": 0.25,
    "bank_cash_flow": 0.25,
    "business_tenure": 0.20,
    "pos_transaction_volume": 0.15,
    "google_maps_rating": 0.10,
    "imss_payroll": 0.05,
}

WEIGHTS_BY_TYPE: dict[str, dict[str, float]] = {
    "abarrotes": {
        "fmcg_purchase_history": 0.30,
        "bank_cash_flow":        0.20,
        "business_tenure":       0.20,
        "pos_transaction_volume":0.10,
        "google_maps_rating":    0.15,
        "imss_payroll":          0.05,
    },
    "taqueria": {
        "fmcg_purchase_history": 0.15,
        "bank_cash_flow":        0.30,
        "business_tenure":       0.20,
        "pos_transaction_volume":0.20,
        "google_maps_rating":    0.10,
        "imss_payroll":          0.05,
    },
    "jugueria": {
        "fmcg_purchase_history": 0.15,
        "bank_cash_flow":        0.30,
        "business_tenure":       0.15,
        "pos_transaction_volume":0.25,
        "google_maps_rating":    0.10,
        "imss_payroll":          0.05,
    },
    "other": WEIGHTS,
}

# ── Bureau provider ──────────────────────────────────────────────────────────
# CALIBRATION: bands must be recalibrated after the first 30 repayment outcomes.
BUREAU_PROVIDER   = "circulo_de_credito"
CIRCULO_HIGH_BAND = 670   # C1: score ≥ 670 → full auto-approve eligibility
CIRCULO_MID_BAND  = 600   # C2: score 600–669 → COMMITTEE ceiling

PHASE0_AUTO_APPROVE_SCORE = 75.0
PHASE0_MAX_TICKET_MXN = 30_000.0
PHASE0_MIN_TENURE_YEARS = 5.0
PHASE0_MIN_MAPS_RATING = 4.0
MANUAL_REVIEW_FLOOR = 50.0
MIN_DATA_COVERAGE = 0.60
MONTHLY_RATE = 0.03
TERM_MONTHS = 2
BOOTSTRAP_ITERATIONS = 500
SIGNAL_NOISE_STD = 6.0

TIER_PREGATED = 14   # fraud / portfolio block — before scorecard runs

# ── 3-Dimension tier matrix (Círculo de Crédito × DSCR × Score) ─────────────

_TIER_MATRIX: dict[tuple[str, str, str], tuple[int, Decision]] = {
    # C1 = Círculo ≥ 670 — full auto-approve eligibility ─────────────────────
    ("C1", "D1", "S1"): (1,  Decision.AUTO_APPROVE),
    ("C1", "D1", "S2"): (2,  Decision.COMMITTEE),
    ("C1", "D2", "S1"): (3,  Decision.COMMITTEE),
    ("C1", "D2", "S2"): (4,  Decision.COMMITTEE),
    # C2 = Círculo 600-669 — COMMITTEE ceiling (mid-band warrants deeper review)
    ("C2", "D1", "S1"): (5,  Decision.COMMITTEE),
    ("C2", "D1", "S2"): (6,  Decision.COMMITTEE),
    ("C2", "D2", "S1"): (7,  Decision.COMMITTEE),
    ("C2", "D2", "S2"): (8,  Decision.COMMITTEE),
    # C3 = thin-file — COMMITTEE ceiling (policy: no bureau file = no auto) ──
    ("C3", "D1", "S1"): (9,  Decision.COMMITTEE),
    ("C3", "D1", "S2"): (10, Decision.COMMITTEE),
    ("C3", "D2", "S1"): (11, Decision.COMMITTEE),
    ("C3", "D2", "S2"): (12, Decision.COMMITTEE),
    # C4 = Círculo < 600 or active delinquency — always DECLINE ───────────────
    **{("C4", d, s): (13, Decision.DECLINE)
       for d in ("D1", "D2", "D3") for s in ("S1", "S2", "S3")},
    # Score below floor — DECLINE regardless of bureau or DSCR ────────────────
    **{(c, d, "S3"): (13, Decision.DECLINE)
       for c in ("C1", "C2", "C3") for d in ("D1", "D2", "D3")},
    # D3 (DSCR hard fail) for non-C4 bureaus falls through to default → tier 13
}

_TIER_LABELS: dict[int, str] = {
    1:  "Tier 1 · Círculo ≥670 · DSCR ≥2.5 · Score ≥75 → AUTO_APPROVE",
    2:  "Tier 2 · Círculo ≥670 · DSCR ≥2.5 · Score 50-74 → COMMITTEE",
    3:  "Tier 3 · Círculo ≥670 · DSCR 1.5-2.5 · Score ≥75 → COMMITTEE",
    4:  "Tier 4 · Círculo ≥670 · DSCR 1.5-2.5 · Score 50-74 → COMMITTEE",
    5:  "Tier 5 · Círculo 600-669 · DSCR ≥2.5 · Score ≥75 → COMMITTEE",
    6:  "Tier 6 · Círculo 600-669 · DSCR ≥2.5 · Score 50-74 → COMMITTEE",
    7:  "Tier 7 · Círculo 600-669 · DSCR 1.5-2.5 · Score ≥75 → COMMITTEE",
    8:  "Tier 8 · Círculo 600-669 · DSCR 1.5-2.5 · Score 50-74 → COMMITTEE",
    9:  "Tier 9 · No Círculo file · DSCR ≥2.5 · Score ≥75 → COMMITTEE",
    10: "Tier 10 · No Círculo file · DSCR ≥2.5 · Score 50-74 → COMMITTEE",
    11: "Tier 11 · No Círculo file · DSCR 1.5-2.5 · Score ≥75 → COMMITTEE",
    12: "Tier 12 · No Círculo file · DSCR 1.5-2.5 · Score 50-74 → COMMITTEE",
    13: "Tier 13 · Círculo <600/delinquent, or DSCR <1.5, or Score <50 → DECLINE",
    14: "Tier 14 · Pre-gate block (fraud / portfolio) → DECLINE",
}


def _buro_dim(buro: Optional[BuroData]) -> str:
    """Map BuroData to Círculo de Crédito dimension (C1/C2/C3/C4).
    A checked report without a numeric score is thin-file C3, never C1."""
    if buro is None or not buro.checked:
        return "C3"   # thin-file: no Círculo file on record
    if buro.active_delinquencies > 0:
        return "C4"   # active delinquency → always decline
    if buro.score is None:
        return "C3"   # score unavailable: cannot infer high bureau quality
    if buro.score >= CIRCULO_HIGH_BAND:
        return "C1"
    if buro.score >= CIRCULO_MID_BAND:
        return "C2"
    return "C4"       # score < 600 → decline


def _dscr_dim(rep: RepaymentAssessment) -> str:
    """Collapse all 5 repayment filters into a single DSCR band.
    Any hard-decline → D3.  Any soft-downgrade OR DSCR 1.5-2.5 → D2.
    Only clean D1 when DSCR ≥ 2.5 AND no downgrades."""
    if rep.hard_declines:
        return "D3"
    if rep.dscr is None:
        return "D3"   # no bank data — can't confirm ≥ 1.5
    if rep.dscr >= MIN_DSCR_AUTO and not rep.downgrades:
        return "D1"
    if rep.dscr >= MIN_DSCR_HARD:
        return "D2"
    return "D3"


def _score_dim(score: float) -> str:
    if score >= PHASE0_AUTO_APPROVE_SCORE:
        return "S1"
    if score >= MANUAL_REVIEW_FLOOR:
        return "S2"
    return "S3"


def _tier_lookup(b: str, d: str, s: str) -> tuple[int, Decision]:
    return _TIER_MATRIX.get((b, d, s), (13, Decision.DECLINE))


def _compute_sensitivity(
    buro_dim: str, dscr_dim: str, score_dim: str,
    tier: int, composite: float, rep: "RepaymentAssessment",
    bank: "Optional[object]",
) -> dict:
    """Compute upgrade-path diagnostics: how far is this application from the next-better tier?
    Used by the analyst UI to answer the credit-committee question 'what would it take?'."""
    from .repayment import suggest_max_affordable_amount

    sensitivity: dict = {
        "buro_blocks_auto": buro_dim in ("C2", "C3"),   # mid-band and thin-file both block auto
        "dscr_gap_to_d1": None,
        "score_gap_to_s1": None,
        "score_gap_to_s2": None,
        "affordable_at_d1": None,
        "path": "",
    }

    # Score gaps
    if score_dim == "S3":
        sensitivity["score_gap_to_s2"] = round(MANUAL_REVIEW_FLOOR - composite, 1)
    if score_dim in ("S2", "S3"):
        sensitivity["score_gap_to_s1"] = round(PHASE0_AUTO_APPROVE_SCORE - composite, 1)

    # DSCR gaps
    if rep.dscr is not None:
        gap = round(MIN_DSCR_AUTO - rep.dscr, 2)
        sensitivity["dscr_gap_to_d1"] = gap  # positive = needs improvement, ≤0 = already there

    # Loan amount that achieves DSCR ≥ 2.5 (for D3 cases — but not C4 where
    # bureau is the real block; suggesting a smaller loan would mislead analysts)
    if dscr_dim == "D3" and buro_dim != "C4" and bank is not None:
        affordable = suggest_max_affordable_amount(bank)
        if affordable:
            sensitivity["affordable_at_d1"] = affordable

    # Human-readable upgrade path
    parts = []
    if buro_dim == "C3":
        parts.append("Círculo de Crédito file required for auto-approve eligibility (no file on record)")
    elif buro_dim == "C2":
        parts.append(f"Círculo score 600-669: needs ≥{CIRCULO_HIGH_BAND} to reach auto-approve band")
    if score_dim == "S3":
        gap_s2 = sensitivity["score_gap_to_s2"]
        parts.append(f"Score +{gap_s2:.0f} pts needed to reach committee band (50)")
    elif score_dim == "S2":
        gap_s1 = sensitivity["score_gap_to_s1"]
        parts.append(f"Score +{gap_s1:.0f} pts needed to reach auto-approve band (75)")
    if buro_dim == "C4":
        parts.append("Resolve Círculo delinquency or low score (<600) to re-enter credit pipeline")
    elif dscr_dim == "D3" and sensitivity["affordable_at_d1"]:
        parts.append(f"Loan ≤ MXN {sensitivity['affordable_at_d1']:,.0f} would achieve DSCR ≥ 2.5")
    elif dscr_dim == "D2":
        if rep.dscr is not None and rep.dscr < MIN_DSCR_AUTO:
            parts.append(f"DSCR needs +{sensitivity['dscr_gap_to_d1']:.2f} to reach D1 threshold (2.5)")
        elif rep.downgrades:
            parts.append("Resolve repayment soft-flags to reach D1")
    if tier == 1:
        parts = ["Optimal — no upgrade path needed"]

    sensitivity["path"] = " · ".join(parts) if parts else ""
    return sensitivity


# ── Signal collection (unchanged) ────────────────────────────────────────────

def _weights_for(app: Application) -> dict[str, float]:
    btype = app.business_type.value if app.business_type else "other"
    return WEIGHTS_BY_TYPE.get(btype, WEIGHTS)


def _collect_signals(app: Application) -> list[SignalScore]:
    weights = _weights_for(app)
    raw = []
    scorers: list[tuple[str, Callable, object]] = [
        ("fmcg_purchase_history", sig.score_fmcg, app.fmcg),
        ("bank_cash_flow", sig.score_bank, app.bank),
        ("business_tenure", sig.score_tenure, app.tenure),
        ("pos_transaction_volume", sig.score_pos, app.pos),
        ("google_maps_rating", sig.score_maps, app.maps),
        ("imss_payroll", sig.score_imss, app.imss),
    ]
    for name, fn, data in scorers:
        score, expl = fn(data)
        fallback = None
        if name == "bank_cash_flow" and data is not None and getattr(data, "source", "syncfy") not in ("syncfy", "belvo"):
            fallback = data.source
        raw.append((name, weights[name], score, expl, fallback))

    available_weight = sum(w for _, w, s, _, _ in raw if s is not None)
    out = []
    for name, w, score, expl, fallback in raw:
        eff = (w / available_weight) if (score is not None and available_weight > 0) else 0.0
        out.append(SignalScore(
            name=name, weight=w,
            raw_score=round(score, 1) if score is not None else None,
            effective_weight=round(eff, 4),
            available=score is not None,
            fallback_used=fallback, explanation=expl,
        ))
    return out


def _composite(signals_list: list[SignalScore]) -> float:
    return sum(s.raw_score * s.effective_weight for s in signals_list if s.raw_score is not None)


def _bootstrap_ci(signals_list: list[SignalScore], seed: int = 7) -> Tuple[float, float]:
    rng = random.Random(seed)
    avail = [s for s in signals_list if s.raw_score is not None]
    if not avail:
        return 0.0, 0.0
    samples = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        total = sum(
            min(100.0, max(0.0, rng.gauss(s.raw_score, SIGNAL_NOISE_STD))) * s.effective_weight
            for s in avail
        )
        samples.append(total)
    samples.sort()
    return round(samples[int(0.05 * len(samples))], 1), round(samples[int(0.95 * len(samples))], 1)


def _phase0_hard_filters(app: Application) -> list[str]:
    """Conservative quality filters. Failures downgrade Tier 1 → Tier 3, never auto-decline."""
    failures = []
    if app.fmcg is None or not app.fmcg.distributor_confirmed:
        failures.append("FMCG distributor delivery not confirmed (FEMSA/Bimbo)")
    tenure_years = 0.0
    if app.tenure is not None:
        tenure_years = max(app.tenure.years_on_google_maps, app.tenure.years_in_imss)
    if tenure_years < PHASE0_MIN_TENURE_YEARS:
        failures.append(f"Business tenure {tenure_years:.1f}y below Phase 0 minimum of {PHASE0_MIN_TENURE_YEARS:.0f}y")
    if app.maps is None or app.maps.rating < PHASE0_MIN_MAPS_RATING:
        rating = app.maps.rating if app.maps else 0.0
        failures.append(f"Google Maps rating {rating:.1f} below Phase 0 minimum of {PHASE0_MIN_MAPS_RATING:.1f}")
    return failures


def _pricing_fixed_cost(amount: float, rate: float = MONTHLY_RATE) -> float:
    return round(amount * rate * TERM_MONTHS, 2)


# ── Main entry point ─────────────────────────────────────────────────────────

def score_application(
    app: Application,
    maps_address: Optional[str] = None,
    bank_stated: Optional[str] = None,
    portfolio_block: Optional[PortfolioBlock] = None,
    graduation: Optional[GraduationOffer] = None,
) -> ScoreResult:
    """
    Score a loan application through the 3-dimension tier matrix.

    Args:
        app:              the full Application object
        maps_address:     full address string from Google Places
        bank_stated:      bank name the merchant claimed
        portfolio_block:  pre-computed portfolio check
        graduation:       pre-computed graduation offer
    """
    app.environment = runtime_mode()

    # ── PRE-GATE: production provenance ─────────────────────────────────────
    # Only block synthetic/mocked data — agent-stated or unverified real data
    # is allowed to contribute (analysts review before any disbursement).
    production_blocks: list[str] = []
    if is_production():
        if app.bank is not None and is_synthetic_source(app.bank.source):
            production_blocks.append(
                "Synthetic bank data is forbidden in production underwriting"
            )
        if app.fmcg is not None and is_synthetic_source(app.fmcg.source):
            production_blocks.append(
                "Synthetic FMCG data is forbidden in production underwriting"
            )
    if production_blocks:
        signals_list = _collect_signals(app)
        composite = _composite(signals_list)
        ci_low, ci_high = _bootstrap_ci(signals_list)
        coverage = sum(s.weight for s in signals_list if s.available)
        fraud_result = assess_fraud(app, maps_address=maps_address, bank_stated=bank_stated)
        rep = assess_repayment(app, 0.0)
        return _result(
            app, signals_list, composite, ci_low, ci_high, coverage,
            Decision.DECLINE, production_blocks, production_blocks,
            fraud_result, rep, PHASE0_MAX_TICKET_MXN, 0.0,
            tier=TIER_PREGATED, production_blocks=production_blocks,
        )

    # ── PRE-GATE: portfolio concentration check ──────────────────────────────
    if portfolio_block and portfolio_block.blocked:
        signals_list = _collect_signals(app)
        composite = _composite(signals_list)
        ci_low, ci_high = _bootstrap_ci(signals_list)
        coverage = sum(s.weight for s in signals_list if s.available)
        fraud_result = assess_fraud(app, maps_address=maps_address, bank_stated=bank_stated)
        rep = assess_repayment(app, 0.0)
        return _result(
            app, signals_list, composite, ci_low, ci_high, coverage,
            Decision.DECLINE, list(portfolio_block.reasons),
            list(portfolio_block.warnings), fraud_result, rep,
            PHASE0_MAX_TICKET_MXN, 0.0, tier=TIER_PREGATED,
        )

    # ── GATE 0: fraud screening ──────────────────────────────────────────────
    fraud_result = assess_fraud(app, maps_address=maps_address, bank_stated=bank_stated)
    if fraud_result.hard_blocks:
        signals_list = _collect_signals(app)
        composite = _composite(signals_list)
        ci_low, ci_high = _bootstrap_ci(signals_list)
        coverage = sum(s.weight for s in signals_list if s.available)
        rep = assess_repayment(app, 0.0)
        return _result(
            app, signals_list, composite, ci_low, ci_high, coverage,
            Decision.DECLINE, list(fraud_result.hard_blocks),
            fraud_result.flags, fraud_result, rep,
            PHASE0_MAX_TICKET_MXN, 0.0, tier=TIER_PREGATED,
        )

    signals_list = _collect_signals(app)
    composite = _composite(signals_list)
    ci_low, ci_high = _bootstrap_ci(signals_list)
    coverage = sum(s.weight for s in signals_list if s.available)
    hard_failures = _phase0_hard_filters(app)

    # Apply graduation tier: repeat borrowers get higher caps / lower rates
    if graduation and graduation.tier > 0:
        max_ticket = graduation.max_ticket_mxn
        reasons_prefix: list[str] = [
            f"Tier {graduation.tier} borrower: max MXN {max_ticket:,.0f} "
            f"at {graduation.pricing_rate:.1%}/month"
        ]
        if graduation.early_repayment_bonus:
            reasons_prefix.append(f"Early repayment bonus applied: rate {graduation.pricing_rate:.1%}/month")
    else:
        max_ticket = PHASE0_MAX_TICKET_MXN
        reasons_prefix = []

    approved_amount = min(app.requested_amount_mxn, max_ticket)
    pricing_rate = graduation.pricing_rate if graduation else MONTHLY_RATE

    # ── GATE 2: repayment layer ──────────────────────────────────────────────
    rep = assess_repayment(app, approved_amount)

    # Counter-offer: if requested amount fails, find what they can carry
    counter_offer_note: Optional[str] = None
    if rep.hard_declines and app.bank is not None:
        affordable = suggest_max_affordable_amount(app.bank)
        if affordable and affordable < approved_amount:
            rep_retry = assess_repayment(app, affordable)
            if not rep_retry.hard_declines:
                counter_offer_note = (
                    f"Requested MXN {app.requested_amount_mxn:,.0f} exceeds repayment "
                    f"capacity; counter-offer at MXN {affordable:,.0f}"
                )
                approved_amount = affordable
                rep = rep_retry

    # ── 3-Dimension tier lookup ──────────────────────────────────────────────
    buro_dim = _buro_dim(app.buro)
    dscr_dim = _dscr_dim(rep)
    score_dim = _score_dim(composite)
    tier, decision = _tier_lookup(buro_dim, dscr_dim, score_dim)

    # ── Phase 0 guard: preserve matrix Tier 1 but route to committee ─────────
    # (AUTO_APPROVE requires all Phase 0 filters, tight CI, coverage, low fraud)
    tier1_downgrade_reason: Optional[str] = None
    if decision == Decision.AUTO_APPROVE:
        if hard_failures:
            decision = Decision.COMMITTEE
            tier1_downgrade_reason = "Phase 0 filter failure"
        elif ci_low < 70.0:
            decision = Decision.COMMITTEE
            tier1_downgrade_reason = f"Score uncertain: CI [{ci_low:.1f}-{ci_high:.1f}]"
        elif coverage < MIN_DATA_COVERAGE:
            decision = Decision.COMMITTEE
            tier1_downgrade_reason = f"Data coverage {coverage:.0%} below {MIN_DATA_COVERAGE:.0%}"
        elif fraud_result.risk_score >= 30.0:
            decision = Decision.COMMITTEE
            tier1_downgrade_reason = f"Fraud risk score {fraud_result.risk_score:.0f}/100"

    # ── Build decision reasons ───────────────────────────────────────────────
    reasons: list[str] = reasons_prefix[:]
    reasons.append(_TIER_LABELS[tier])

    if counter_offer_note:
        reasons.append(counter_offer_note)

    if fraud_result.flags:
        reasons.extend([f"[FRAUD FLAG] {f}" for f in fraud_result.flags])

    if decision == Decision.AUTO_APPROVE:
        reasons.append(
            f"Score {composite:.1f} (CI [{ci_low:.1f}-{ci_high:.1f}]), "
            f"coverage {coverage:.0%}, DSCR {rep.dscr}, all Phase 0 + repayment + fraud checks passed"
        )
        if app.requested_amount_mxn > approved_amount:
            reasons.append(f"Amount capped at MXN {approved_amount:,.0f}")

    elif decision == Decision.COMMITTEE:
        if tier1_downgrade_reason:
            reasons.append(f"Tier 1 downgrade: {tier1_downgrade_reason}")
        if buro_dim == "C3":
            reasons.append(
                "No Círculo de Crédito file on record: committee review required "
                "(policy: no auto-approve without bureau file)"
            )
        elif buro_dim == "C2":
            score_str = f" ({app.buro.score})" if app.buro and app.buro.score else ""
            reasons.append(
                f"Círculo score{score_str} in mid band (600-669): needs ≥{CIRCULO_HIGH_BAND} "
                "for auto-approve — committee review required"
            )
        if score_dim == "S2":
            reasons.append(f"Score {composite:.1f} in committee band (50-74)")
        if dscr_dim == "D2":
            if rep.dscr is not None and rep.dscr < MIN_DSCR_AUTO:
                reasons.append(f"DSCR {rep.dscr:.2f}: below auto-approve threshold of {MIN_DSCR_AUTO}")
            elif rep.dscr is not None:
                reasons.append(f"DSCR {rep.dscr:.2f}: strong but repayment soft-flags present")
            reasons.extend(rep.downgrades)
        if hard_failures:
            reasons.extend(hard_failures)
        if ci_low < 70.0 and not tier1_downgrade_reason:
            reasons.append(f"Score uncertain: CI [{ci_low:.1f}-{ci_high:.1f}]")
        if coverage < MIN_DATA_COVERAGE and not tier1_downgrade_reason:
            reasons.append(f"Data coverage {coverage:.0%} below {MIN_DATA_COVERAGE:.0%}")
        if fraud_result.risk_score >= 30.0 and not tier1_downgrade_reason:
            reasons.append(f"Fraud risk score {fraud_result.risk_score:.0f}/100 — analyst review required")

    else:  # DECLINE
        if score_dim == "S3":
            reasons.append(f"Score {composite:.1f} below decline floor of {MANUAL_REVIEW_FLOOR:.0f}")
        if buro_dim == "C4":
            # C4 is the primary cause; repayment hard_declines from assess_repayment
            # may duplicate the Buró entry — skip them here to avoid redundancy.
            if app.buro and app.buro.active_delinquencies > 0:
                reasons.append(f"Círculo de Crédito: {app.buro.active_delinquencies} active delinquencies")
            elif app.buro and app.buro.score is not None:
                reasons.append(
                    f"Círculo score {app.buro.score} below minimum of {CIRCULO_MID_BAND} "
                    "(band C4 — outside lending criteria)"
                )
        elif dscr_dim == "D3":
            if rep.hard_declines:
                reasons.extend(rep.hard_declines)
            elif rep.dscr is not None:
                reasons.append(f"DSCR {rep.dscr:.2f} below repayment floor of {MIN_DSCR_HARD}")
            else:
                reasons.append("DSCR could not be assessed (no bank data)")
        if hard_failures:
            reasons.extend(hard_failures)

    if decision == Decision.DECLINE:
        approved_amount = 0.0

    sensitivity = _compute_sensitivity(
        buro_dim, dscr_dim, score_dim, tier, composite, rep, app.bank
    )

    return _result(
        app, signals_list, composite, ci_low, ci_high, coverage,
        decision, reasons, hard_failures, fraud_result, rep,
        max_ticket, approved_amount, pricing_rate, tier=tier,
        sensitivity=sensitivity,
    )


def _result(
    app, signals_list, composite, ci_low, ci_high, coverage,
    decision, reasons, hard_failures, fraud_result, rep,
    max_ticket, approved_amount, pricing_rate=MONTHLY_RATE, tier: int = 0,
    sensitivity: Optional[dict] = None,
    production_blocks: Optional[list[str]] = None,
) -> ScoreResult:
    return ScoreResult(
        application_id=app.application_id,
        merchant_name=app.merchant_name,
        score=round(composite, 1),
        ci_low=ci_low, ci_high=ci_high,
        data_coverage=round(coverage, 2),
        decision=decision,
        decision_reasons=reasons,
        hard_filter_failures=hard_failures,
        fraud_assessment=fraud_result,
        repayment=rep,
        max_ticket_mxn=max_ticket,
        approved_amount_mxn=approved_amount,
        pricing_fixed_cost_mxn=_pricing_fixed_cost(approved_amount, pricing_rate),
        signals=signals_list,
        tier=tier,
        tier_sensitivity=sensitivity or {},
        environment=app.environment,
        production_blocks=production_blocks or [],
    )
