"""
Olin - Loan graduation (repeat borrower path)

Every application starts from the same caps and rates unless the borrower
has a history with us. Graduation is the retention mechanic: a merchant who
repaid on time earns better terms on the next loan, automatically.

Tier system:
  Tier 0 — New borrower.           Max MXN 30K, rate 3.0%/month
  Tier 1 — 1 repaid on time.       Max MXN 50K, rate 2.8%/month
  Tier 2 — 2+ repaid, no default.  Max MXN 75K, rate 2.5%/month
  Tier 3 — 4+ repaid, no default.  Max MXN 100K, rate 2.2%/month

Early repayment bonus:
  Repaid ≥ 5 days early on the most recent loan → -0.2% on next loan rate.

Counter-offer respect:
  If the merchant's last loan was a counter-offer (approved < requested), the
  new max ticket is still based on graduation tier, but the repayment capacity
  check in scorecard.py will size it down again if needed.

Usage:
    from olin.graduation import get_graduation_offer
    offer = get_graduation_offer(clabe, db_path)
    # offer.tier, offer.max_ticket_mxn, offer.pricing_rate
"""
from __future__ import annotations

from typing import Optional

from .models import GraduationOffer

TIERS = [
    # (min_repaid, max_no_default_required, max_ticket, monthly_rate)
    (0, False, 30_000.0, 0.030),   # Tier 0: new
    (1, False, 50_000.0, 0.028),   # Tier 1
    (2, True,  75_000.0, 0.025),   # Tier 2: 2+ and no defaults
    (4, True, 100_000.0, 0.022),   # Tier 3: 4+ and no defaults
]
EARLY_REPAYMENT_DAYS = 5    # paid this many days before Day 60 = bonus
EARLY_REPAYMENT_RATE_BONUS = 0.002   # 0.2% rate reduction


def get_graduation_offer(clabe: str, db_path: str) -> GraduationOffer:
    """
    Look up the merchant's history and return the best offer they qualify for.
    Returns Tier 0 defaults if no history or DB error.
    """
    if not clabe or not db_path:
        return _tier_offer(0, early_bonus=False, notes=["New borrower"])

    try:
        from .store import ScoringLog
        with ScoringLog(db_path) as log:
            history = log.merchant_history(clabe)
    except Exception:
        return _tier_offer(0, early_bonus=False, notes=["New borrower (DB unavailable)"])

    if not history:
        return _tier_offer(0, early_bonus=False, notes=["New borrower"])

    # Count repaid and defaulted loans
    repaid_count  = sum(1 for h in history if h.get("repaid_on_time") == 1)
    default_count = sum(1 for h in history if h.get("defaulted") == 1)
    notes: list[str] = []

    # Any prior default suspends automatic graduation during the pilot.
    tier = 0
    if default_count == 0:
        for t, (min_rep, no_default_req, _, _) in enumerate(TIERS):
            if repaid_count >= min_rep:
                tier = t
            else:
                break

    # Early repayment bonus: did the most recent completed loan pay early?
    early_bonus = False
    for h in history:
        if h.get("repaid_on_time") == 1 and h.get("days_to_repay") is not None:
            days = h["days_to_repay"]
            if days <= (60 - EARLY_REPAYMENT_DAYS):
                early_bonus = True
                notes.append(
                    f"Early repayment bonus: last loan repaid in {days} days "
                    f"(-{EARLY_REPAYMENT_RATE_BONUS:.1%} rate)"
                )
            break  # only check most recent completed loan

    if repaid_count > 0:
        notes.append(f"{repaid_count} loan{'s' if repaid_count > 1 else ''} repaid on time")
    if default_count > 0:
        notes.append(f"⚠ {default_count} default{'s' if default_count > 1 else ''} on record")
        notes.append("Automatic graduation suspended because of prior default")
    if tier == 0 and repaid_count == 0 and len(history) > 0:
        notes.append("Existing application on file but no completed loans yet")

    return _tier_offer(tier, early_bonus=early_bonus, notes=notes)


def _tier_offer(tier: int, early_bonus: bool, notes: list[str]) -> GraduationOffer:
    _, _, max_ticket, rate = TIERS[tier]
    if early_bonus:
        rate = max(0.015, rate - EARLY_REPAYMENT_RATE_BONUS)
    return GraduationOffer(
        tier=tier,
        max_ticket_mxn=max_ticket,
        pricing_rate=round(rate, 4),
        early_repayment_bonus=early_bonus,
        notes=notes,
    )
