"""
Olin - Portfolio-level concentration limits (pre-GATE 0)

Runs before fraud screening. These checks protect the portfolio as a whole,
not the individual loan. A perfectly creditworthy merchant in a colonia where
we're already overexposed gets flagged — not because they're risky, but because
we are.

Phase 0 limits (conservative for a book < 200 loans):
  - Duplicate CLABE: same account can't have 2 active loans (hard block)
  - Colonia concentration: >4 active loans in one colonia → flag
  - Colonia exposure: >MXN 120,000 active in one colonia → flag
  - Business type: >65% of active portfolio in one type → flag
  - Portfolio default rate: >15% → freeze AUTO_APPROVE (hard block)

Limits are intentionally tight for Phase 0. Relax them as the book grows
and you have data to calibrate per-colonia default rates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import Application, PortfolioBlock
from .config import is_production

# Phase 0 limits
MAX_ACTIVE_PER_COLONIA      = 4
MAX_EXPOSURE_PER_COLONIA    = 120_000.0   # MXN
MAX_TYPE_CONCENTRATION      = 0.65        # 65% of active book
MAX_PORTFOLIO_DEFAULT_RATE  = 0.15        # freeze AUTO_APPROVE above this


def check_portfolio(
    app: Application,
    db_path: str,
) -> PortfolioBlock:
    """
    Run portfolio-level checks before scoring this application.

    Returns PortfolioBlock with blocked=True if any hard limit is breached.
    Warnings are surfaced to the analyst but don't block.
    """
    try:
        from .store import ScoringLog
        with ScoringLog(db_path) as log:
            snapshot = log.portfolio_snapshot()
            active   = log.active_loans()
    except Exception as e:
        # A production decision without exposure/default checks is unsafe.
        return PortfolioBlock(
            blocked=is_production(),
            reasons=[f"Portfolio check unavailable: {e}"] if is_production() else [],
            warnings=[f"Portfolio check failed: {e}"],
        )

    reasons:  list[str] = []
    warnings: list[str] = []

    # ── 1. Duplicate CLABE ──────────────────────────────────────────
    if app.clabe:
        clabe_active = [l for l in active if l.get("clabe") == app.clabe]
        if clabe_active:
            reasons.append(
                f"CLABE {app.clabe[:6]}****** already has an active loan "
                f"(app {clabe_active[0]['application_id']}). "
                "A borrower cannot hold two Olin loans simultaneously."
            )

    # ── 2. Colonia concentration ─────────────────────────────────────
    colonia = (app.colonia or "").strip().lower()
    if colonia:
        col_loans = [l for l in active
                     if (l.get("colonia") or "").strip().lower() == colonia]
        col_count = len(col_loans)
        col_mxn   = sum(l.get("approved_mxn", 0) for l in col_loans)

        if col_count >= MAX_ACTIVE_PER_COLONIA:
            warnings.append(
                f"Colonia '{app.colonia}' already has {col_count} active loans "
                f"(limit {MAX_ACTIVE_PER_COLONIA}). Consider spreading geographic risk."
            )
        if col_mxn >= MAX_EXPOSURE_PER_COLONIA:
            warnings.append(
                f"Colonia '{app.colonia}' exposure MXN {col_mxn:,.0f} "
                f"exceeds limit MXN {MAX_EXPOSURE_PER_COLONIA:,.0f}."
            )

    # ── 3. Business type concentration ──────────────────────────────
    btype = app.business_type.value if app.business_type else "other"
    n_active = len(active)
    if n_active >= 5:  # only meaningful with some portfolio
        type_count = sum(1 for l in active
                         if (l.get("business_type") or "") == btype)
        type_share = type_count / n_active
        if type_share >= MAX_TYPE_CONCENTRATION:
            warnings.append(
                f"Business type '{btype}' is {type_share:.0%} of active portfolio "
                f"(limit {MAX_TYPE_CONCENTRATION:.0%}). Sector concentration risk."
            )

    # ── 4. Portfolio default rate ────────────────────────────────────
    default_rate = snapshot.get("default_rate", 0.0)
    total_disbursed = snapshot.get("total_disbursed", 0)
    resolved_loans = snapshot.get("resolved_loans", 0)
    if resolved_loans >= 10 and default_rate >= MAX_PORTFOLIO_DEFAULT_RATE:
        reasons.append(
            f"Portfolio default rate {default_rate:.1%} exceeds "
            f"{MAX_PORTFOLIO_DEFAULT_RATE:.0%} threshold. "
            "New lending is frozen until portfolio risk is reviewed."
        )

    return PortfolioBlock(
        blocked=len(reasons) > 0,
        reasons=reasons,
        warnings=warnings,
        stats={
            "active_loans":   snapshot.get("active_loans", 0),
            "active_mxn":     snapshot.get("active_mxn", 0),
            "default_rate":   default_rate,
            "total_disbursed": total_disbursed,
            "resolved_loans": resolved_loans,
        },
    )
