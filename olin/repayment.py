"""
Olin V2 - Repayment Prediction Layer

This module answers ONE question the quality scorecard cannot:
  "Can this specific merchant repay THIS specific amount in 60 days?"

Five checks, all computable from existing Syncfy BankData. No new APIs.

1. DSCR (Debt Service Coverage Ratio)
   monthly_net_income / monthly_payment >= 2.5 for auto-approve
   Below 1.5 = hard decline (mathematically cannot repay)

2. Stress buffer
   Can the merchant absorb a 2-day revenue shock (fridge breaks, street
   closed, sick day) and still make the payment?
   min_daily_balance >= 2 x average daily payment burden

3. Deposit volatility
   Fixed payments require predictable income.
   deposit_regularity < 0.60 -> income too irregular for fixed schedule

4. Balance trend
   A business in decline should not receive credit regardless of score.
   balance_trend_90d < -0.30 -> hard decline

5. Payment burden ratio
   monthly_payment / monthly_inflows <= 25%
   Above 40% = hard decline (loan payment would eat the business)

Design principle: these are FILTERS, not score inputs. A beautiful
business that cannot repay gets declined. The score says "good business",
the repayment layer says "good borrower". Both must pass.
"""
from __future__ import annotations

from typing import Optional

from .models import Application, BankData, RepaymentAssessment

# Phase 0 repayment policy constants
MIN_DSCR_AUTO = 2.5          # auto-approve threshold
MIN_DSCR_HARD = 1.5          # below this = hard decline
MIN_STRESS_BUFFER = 2.0      # days of payment burden covered by min balance
MIN_DEPOSIT_REGULARITY = 0.60
MAX_NEGATIVE_TREND = -0.30   # hard decline below this
MAX_BURDEN_AUTO = 0.25       # payment <= 25% of inflows for auto
MAX_BURDEN_HARD = 0.40       # above 40% = hard decline
TERM_MONTHS = 2
NET_MARGIN_FLOOR = 0.10      # assume at least 10% of inflows are margin


def _estimate_monthly_net(bank: BankData) -> Optional[float]:
    """Best available estimate of monthly free cash flow.
    Preferred: inflows - outflows (true net).
    Fallback: inflow volume x margin floor (conservative).
    Last resort: avg_daily_balance x 30 x 0.15 (very rough)."""
    if bank.monthly_deposit_volume_mxn > 0 and bank.monthly_outflow_volume_mxn > 0:
        net = bank.monthly_deposit_volume_mxn - bank.monthly_outflow_volume_mxn
        # Net can be tiny or negative even in healthy cash businesses that
        # sweep cash out; floor it at margin-based estimate.
        floor = bank.monthly_deposit_volume_mxn * NET_MARGIN_FLOOR
        return max(net, floor)
    if bank.monthly_deposit_volume_mxn > 0:
        return bank.monthly_deposit_volume_mxn * NET_MARGIN_FLOOR
    if bank.avg_daily_balance_mxn > 0:
        return bank.avg_daily_balance_mxn * 30 * 0.15
    return None


def assess_repayment(app: Application, approved_amount: float) -> RepaymentAssessment:
    """Run the 5 repayment checks. Returns hard_declines (kill the loan),
    downgrades (force manual review), and notes (analyst context)."""
    out = RepaymentAssessment(
        dscr=None, stress_buffer_ratio=None, deposit_volatility_ok=None,
        trend_ok=None, burden_ratio=None, estimated_monthly_net_mxn=None,
    )

    if approved_amount <= 0:
        out.notes.append("No amount to assess (already declined)")
        return out

    bank = app.bank
    if bank is None or bank.months_connected <= 0:
        out.downgrades.append(
            "No bank data: repayment capacity unverifiable, manual review required"
        )
        return out

    monthly_payment = approved_amount / TERM_MONTHS
    monthly_net = _estimate_monthly_net(bank)
    out.estimated_monthly_net_mxn = round(monthly_net, 0) if monthly_net else None

    # ---- 1. DSCR ----
    if monthly_net is not None and monthly_payment > 0:
        dscr = monthly_net / monthly_payment
        out.dscr = round(dscr, 2)
        if dscr < MIN_DSCR_HARD:
            out.hard_declines.append(
                f"DSCR {dscr:.2f} below {MIN_DSCR_HARD}: merchant cannot cover "
                f"MXN {monthly_payment:,.0f}/month from estimated net of "
                f"MXN {monthly_net:,.0f}/month"
            )
        elif dscr < MIN_DSCR_AUTO:
            out.downgrades.append(
                f"DSCR {dscr:.2f} below {MIN_DSCR_AUTO}: repayment coverage thin, "
                "manual review required"
            )

    # ---- 2. Stress buffer ----
    daily_burden = monthly_payment / 30
    if bank.min_daily_balance_mxn > 0 and daily_burden > 0:
        buffer = bank.min_daily_balance_mxn / (daily_burden * 2)
        out.stress_buffer_ratio = round(buffer, 2)
        if buffer < 1.0:
            out.downgrades.append(
                f"Stress buffer {buffer:.2f}: worst-day balance "
                f"(MXN {bank.min_daily_balance_mxn:,.0f}) cannot absorb a 2-day "
                "revenue shock while owing payments"
            )
    elif bank.avg_daily_balance_mxn > 0:
        # fallback on average balance if min is unavailable
        buffer = bank.avg_daily_balance_mxn / (approved_amount / 30 * 2)
        out.stress_buffer_ratio = round(buffer, 2)
        if buffer < 1.0:
            out.downgrades.append(
                f"Stress buffer {buffer:.2f} (avg-balance fallback): balance too "
                "thin to absorb a 2-day shock"
            )

    # ---- 3. Deposit volatility ----
    out.deposit_volatility_ok = bank.deposit_regularity >= MIN_DEPOSIT_REGULARITY
    if not out.deposit_volatility_ok:
        out.downgrades.append(
            f"Deposit regularity {bank.deposit_regularity:.2f} below "
            f"{MIN_DEPOSIT_REGULARITY}: income too irregular for fixed "
            "2-payment schedule"
        )

    # ---- 4. Balance trend ----
    out.trend_ok = bank.balance_trend_90d >= MAX_NEGATIVE_TREND
    if not out.trend_ok:
        out.hard_declines.append(
            f"Balance trend {bank.balance_trend_90d:+.2f} over 90d: business in "
            "decline, no credit regardless of score"
        )

    # ---- 5. Payment burden ----
    if bank.monthly_deposit_volume_mxn > 0:
        burden = monthly_payment / bank.monthly_deposit_volume_mxn
        out.burden_ratio = round(burden, 3)
        if burden > MAX_BURDEN_HARD:
            out.hard_declines.append(
                f"Payment burden {burden:.0%} of monthly inflows exceeds "
                f"{MAX_BURDEN_HARD:.0%}: loan would eat the business"
            )
        elif burden > MAX_BURDEN_AUTO:
            out.downgrades.append(
                f"Payment burden {burden:.0%} above {MAX_BURDEN_AUTO:.0%} "
                "auto-approve ceiling"
            )

    # ---- Buro de Credito gate (manual, pre-disbursement) ----
    if app.buro is None or not app.buro.checked:
        out.notes.append(
            "Buro de Credito NOT checked (MXN 50, burodecredito.com.mx). "
            "Mandatory before disbursement even on AUTO_APPROVE."
        )
    elif app.buro.active_delinquencies > 0:
        out.hard_declines.append(
            f"Buro: {app.buro.active_delinquencies} active delinquencies"
        )
    elif app.buro.active_loans_count >= 3:
        out.downgrades.append(
            f"Buro: {app.buro.active_loans_count} active loans elsewhere, "
            "multi-lending stress risk"
        )

    return out


def suggest_max_affordable_amount(bank: Optional[BankData]) -> Optional[float]:
    """Inverse calculation: given this merchant's cash flow, what is the
    largest loan they can safely carry? Used to counter-offer instead of
    declining. amount = monthly_net / MIN_DSCR_AUTO * TERM_MONTHS"""
    if bank is None:
        return None
    net = _estimate_monthly_net(bank)
    if net is None or net <= 0:
        return None
    amount = net / MIN_DSCR_AUTO * TERM_MONTHS
    # round down to nearest 1,000, floor 5,000
    amount = int(amount // 1000) * 1000
    return float(amount) if amount >= 5000 else None
