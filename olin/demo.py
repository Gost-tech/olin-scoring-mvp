"""
Olin Credit Scoring MVP - Demo
Three real-world profiles:
  1. Maria, abarrotes Iztapalapa, 11 years, FEMSA confirmed, full data -> auto-approve
  2. Roberto, taqueria cash-only, no POS, BanCoppel (no Belvo) -> manual review on fallback signals
  3. New jugueria, 14 months old, weak signals -> decline
Run: python -m olin.demo
"""
from __future__ import annotations

from .models import (
    Application, BusinessType,
    FMCGData, BankData, TenureData, POSData, MapsRatingData, IMSSPayrollData,
)
from .scorecard import score_application
from .store import ScoringLog


def _print_result(res):
    print("=" * 72)
    print(f"{res.merchant_name}  |  app {res.application_id}")
    print(f"SCORE: {res.score}  CI [{res.ci_low} - {res.ci_high}]  coverage {res.data_coverage:.0%}")
    print(f"DECISION: {res.decision.value}")
    for r in res.decision_reasons:
        print(f"  - {r}")
    if res.approved_amount_mxn > 0:
        print(f"  Amount: MXN {res.approved_amount_mxn:,.0f}  |  "
              f"Fixed cost: MXN {res.pricing_fixed_cost_mxn:,.0f} over 60 days, 2 payments")
    print("  Signals:")
    for s in res.signals:
        if s.available:
            fb = f" [fallback: {s.fallback_used}]" if s.fallback_used else ""
            print(f"    {s.name:26s} {s.raw_score:5.1f}  w={s.effective_weight:.2f}{fb}  {s.explanation}")
        else:
            print(f"    {s.name:26s}  MISSING  {s.explanation}")
    print()


def main():
    log = ScoringLog("/home/claude/olin_scoring/olin_scoring.db")

    # ------------------------------------------------------------------
    # Case 1: Maria - the ideal Phase 0 borrower
    # ------------------------------------------------------------------
    maria = Application(
        merchant_name="Maria - Abarrotes Don Chuy",
        business_type=BusinessType.ABARROTES,
        requested_amount_mxn=40_000,   # will be capped at 30K in Phase 0
        colonia="Iztapalapa Centro",
        fmcg=FMCGData(
            months_of_history=18, weekly_purchase_rate=0.96,
            missed_weeks_last_12=0, avg_weekly_purchase_mxn=8_500,
            distributor_confirmed=True, trend_3m=0.15,
        ),
        bank=BankData(
            months_connected=3, avg_daily_balance_mxn=22_000,
            monthly_deposit_count=24, deposit_regularity=0.88,
            overdrafts_90d=0, balance_trend_90d=0.10, source="belvo",
        ),
        tenure=TenureData(years_on_google_maps=11, years_in_imss=8, address_consistent=True),
        pos=POSData(months_of_history=14, avg_monthly_volume_mxn=38_000,
                    volume_consistency=0.82, trend_3m=0.08),
        maps=MapsRatingData(rating=4.6, review_count=132, review_velocity_6m=9),
        imss=IMSSPayrollData(registered_employees=2),
    )
    res = score_application(maria)
    log.log(maria, res)
    _print_result(res)

    # ------------------------------------------------------------------
    # Case 2: Roberto - cash-only taqueria, non-Belvo bank
    # The coverage-gap case: 15-20% of the segment looks like this
    # ------------------------------------------------------------------
    roberto = Application(
        merchant_name="Roberto - Taqueria El Guero",
        business_type=BusinessType.TAQUERIA,
        requested_amount_mxn=25_000,
        colonia="Doctores",
        fmcg=FMCGData(
            months_of_history=10, weekly_purchase_rate=0.85,
            missed_weeks_last_12=2, avg_weekly_purchase_mxn=5_200,
            distributor_confirmed=True, trend_3m=0.0,
        ),
        bank=BankData(  # manual statement upload, BanCoppel
            months_connected=3, avg_daily_balance_mxn=9_000,
            monthly_deposit_count=15, deposit_regularity=0.70,
            overdrafts_90d=1, balance_trend_90d=0.0, source="manual_upload",
        ),
        tenure=TenureData(years_on_google_maps=7, years_in_imss=0, address_consistent=True),
        pos=None,  # cash-only: weighted signal missing, NOT a hard filter
        maps=MapsRatingData(rating=4.3, review_count=58, review_velocity_6m=4),
        imss=IMSSPayrollData(registered_employees=0),
    )
    res = score_application(roberto)
    log.log(roberto, res)
    _print_result(res)

    # ------------------------------------------------------------------
    # Case 3: New jugueria, thin file, weak signals
    # ------------------------------------------------------------------
    nueva = Application(
        merchant_name="Jugueria La Esquina (14 months)",
        business_type=BusinessType.JUGUERIA,
        requested_amount_mxn=20_000,
        colonia="Narvarte",
        fmcg=FMCGData(
            months_of_history=4, weekly_purchase_rate=0.55,
            missed_weeks_last_12=5, distributor_confirmed=False,
        ),
        bank=None,
        tenure=TenureData(years_on_google_maps=1.2, years_in_imss=0),
        pos=None,
        maps=MapsRatingData(rating=4.0, review_count=6, review_velocity_6m=3),
        imss=IMSSPayrollData(registered_employees=0),
    )
    res = score_application(nueva)
    log.log(nueva, res)
    _print_result(res)

    # ------------------------------------------------------------------
    # Outcome labeling demo: this is how logs become the ML training set
    # ------------------------------------------------------------------
    log.record_outcome(maria.application_id, repaid_on_time=True, days_to_repay=58)
    print("Portfolio stats:", log.stats())
    print(f"Training rows with labels: {len(log.training_rows())}")


if __name__ == "__main__":
    main()
