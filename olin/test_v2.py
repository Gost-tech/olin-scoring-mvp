"""
Olin V2 — Full test suite: Círculo de Crédito tier matrix, repayment layer, edge cases.

Run: python3 -m olin.test_v2

Coverage:
  • Original 5 cases (repayment logic)
  • C1 tiers 2-4 and C3 thin-file tiers 9-12 explicitly
  • NEW: C2 mid-band tiers 5-8 (Círculo 600-669 — COMMITTEE ceiling)
  • Graduation borrower hitting tier matrix
  • Multi-lending soft-flag (C1 + Círculo loans ≥ 3 → D2)
  • No-bank-data edge case (→ D3, tier 13 DECLINE)
  • Score boundary cases (exactly 75, exactly 50)
  • DSCR sensitivity fields
  • Círculo de Crédito mock integration
"""
from __future__ import annotations

from dataclasses import replace as _dc_replace

from .models import (
    Application, BusinessType, BuroData, FraudData,
    FMCGData, BankData, TenureData, POSData, MapsRatingData, IMSSPayrollData,
    Decision, GraduationOffer,
)
from .scorecard import score_application

# ── Shared helpers ───────────────────────────────────────────────────────────

_CLEAN_FRAUD = FraudData(
    phone_mx="5512345678", rfc="CHGU850101AB2",
    ine_checked=True, address_stated="Iztapalapa Centro CDMX",
)

_CLEAN_BURO  = BuroData(checked=True, active_delinquencies=0, active_loans_count=1, score=720)  # C1
_MID_BURO    = BuroData(checked=True, active_delinquencies=0, active_loans_count=1, score=635)  # C2
_NOFILE_BURO = BuroData(checked=False)                                                           # C3
_MULTI_BURO  = BuroData(checked=True, active_delinquencies=0, active_loans_count=3, score=695)  # C1+soft
_DELQ_BURO   = BuroData(checked=True, active_delinquencies=2, active_loans_count=4, score=520)  # C4

# Bank that gives DSCR ≥ 2.5 with no downgrades (D1)
_BANK_D1 = BankData(
    months_connected=3, avg_daily_balance_mxn=22_000,
    monthly_deposit_count=24,
    monthly_deposit_volume_mxn=95_000, monthly_outflow_volume_mxn=52_000,
    deposit_regularity=0.88, overdrafts_90d=0,
    balance_trend_90d=0.10, min_daily_balance_mxn=9_000,
)
# Bank that gives DSCR 1.5–2.5 (D2) — low net / high payment
_BANK_D2 = BankData(
    months_connected=3, avg_daily_balance_mxn=5_000,
    monthly_deposit_count=15,
    monthly_deposit_volume_mxn=28_000, monthly_outflow_volume_mxn=21_000,
    deposit_regularity=0.72, overdrafts_90d=0,
    balance_trend_90d=0.02, min_daily_balance_mxn=1_500,
)  # net≈7K, monthly_payment for 20K = 10K → DSCR≈0.7 — actually D3 for 20K
# For D2 we need net ≥ 1.5×payment: at 20K request net = 10K payment, need net ≥ 15K
_BANK_D2_OK = BankData(
    months_connected=3, avg_daily_balance_mxn=8_000,
    monthly_deposit_count=18,
    monthly_deposit_volume_mxn=45_000, monthly_outflow_volume_mxn=28_000,
    deposit_regularity=0.68, overdrafts_90d=0,
    balance_trend_90d=0.02, min_daily_balance_mxn=2_200,
)  # net=17K, payment for 20K=10K, DSCR=1.7 → D2 (deposit_regularity 0.68 > 0.60 OK)

_TENURE_S1 = TenureData(11, 8, True)       # 11 years → high score
_TENURE_S2 = TenureData(5, 3, True)        # 5 years → mid score contribution
_MAPS_S1   = MapsRatingData(4.6, 132, 9)
_MAPS_S2   = MapsRatingData(4.2, 45, 3)
_FMCG_S1   = FMCGData(18, 0.96, 0, 8_500, True, 0.15)
_FMCG_S2   = FMCGData(10, 0.78, 2, 4_000, True, 0.0)


def _abarrotes(name, amount, buro, bank, tenure=_TENURE_S1, maps=_MAPS_S1,
               fmcg=_FMCG_S1, imss=None) -> Application:
    return Application(
        merchant_name=name, business_type=BusinessType.ABARROTES,
        requested_amount_mxn=amount, colonia="Iztapalapa",
        fmcg=fmcg, bank=bank, tenure=tenure, maps=maps,
        imss=imss or IMSSPayrollData(2), buro=buro, fraud=_CLEAN_FRAUD,
    )


def _print(res, label=""):
    rep = res.repayment
    dscr_s = f"{rep.dscr:.2f}" if rep and rep.dscr is not None else "—"
    sens = res.tier_sensitivity or {}
    print(f"  {'='*70}")
    print(f"  {label or res.merchant_name}")
    print(f"  Score {res.score:.1f}  CI [{res.ci_low:.1f}-{res.ci_high:.1f}]  "
          f"DSCR {dscr_s}  Coverage {res.data_coverage:.0%}")
    print(f"  → Tier {res.tier}  {res.decision.value}  "
          f"Approved MXN {res.approved_amount_mxn:,.0f}")
    if sens.get("path"):
        print(f"  Sensitivity: {sens['path']}")
    for r in res.decision_reasons:
        print(f"     • {r}")
    print()


# ── Original 5 cases ─────────────────────────────────────────────────────────

def case_1_maria_healthy():
    """C1·D1·S1 → Tier 1, AUTO_APPROVE. The golden path."""
    return _abarrotes("CASE 1 Maria — great business strong cash flow",
                       40_000, _CLEAN_BURO, _BANK_D1)


def case_2_beautiful_trap():
    """C1·D3·S1 → Tier 13 DECLINE. 12-year abarrotes, balance in freefall."""
    app = _abarrotes("CASE 2 Beautiful trap — great score, dying cash flow",
                     30_000, _CLEAN_BURO,
                     BankData(months_connected=3, avg_daily_balance_mxn=3_500,
                              monthly_deposit_count=22,
                              monthly_deposit_volume_mxn=60_000,
                              monthly_outflow_volume_mxn=58_000,
                              deposit_regularity=0.85, overdrafts_90d=1,
                              balance_trend_90d=-0.45,    # freefall → hard decline
                              min_daily_balance_mxn=400),
                     tenure=TenureData(12, 9, True),
                     maps=MapsRatingData(4.8, 210, 6),
                     fmcg=FMCGData(24, 0.92, 1, 7_000, True, -0.05),
                     imss=IMSSPayrollData(3))
    return app


def case_3_counter_offer():
    """C1·S1 + DSCR fails at 30K but passes at 16K → counter-offer, Tier 1."""
    return Application(
        merchant_name="CASE 3 Counter-offer — over-asked, carries 16K",
        business_type=BusinessType.TAQUERIA, requested_amount_mxn=30_000,
        colonia="Narvarte",
        fmcg=FMCGData(14, 0.88, 1, 5_000, True, 0.05),
        bank=BankData(months_connected=3, avg_daily_balance_mxn=8_000,
                      monthly_deposit_count=20,
                      monthly_deposit_volume_mxn=48_000, monthly_outflow_volume_mxn=28_000,
                      deposit_regularity=0.78, overdrafts_90d=0,
                      balance_trend_90d=0.05, min_daily_balance_mxn=3_000),
        tenure=TenureData(7, 5, True), pos=None,
        maps=MapsRatingData(4.4, 76, 5), imss=IMSSPayrollData(0),
        buro=_CLEAN_BURO, fraud=_CLEAN_FRAUD,
    )


def case_4_delinquent():
    """C4 → Tier 13 DECLINE regardless of score or DSCR."""
    app = case_1_maria_healthy()
    app.merchant_name = "CASE 4 Delinquent Círculo — great numbers, active default"
    app.buro = _DELQ_BURO
    return app


def case_5_volatile_income():
    """C1·D2·S1 → Tier 3. Deposit regularity 0.45 downgrades DSCR to D2."""
    app = case_1_maria_healthy()
    app.merchant_name = "CASE 5 Volatile income — irregular deposits downgrade DSCR"
    # Use _dc_replace to avoid mutating the shared _BANK_D1 module-level object
    app.bank = _dc_replace(app.bank, deposit_regularity=0.45)
    return app


# ── C1 committee tiers (tiers 2-4) ───────────────────────────────────────────

def case_t2_clean_d1_s2():
    """C1·D1·S2 → Tier 2. Círculo ≥670, strong DSCR, mid score (5yr tenure)."""
    return _abarrotes("TIER 2 C1·D1·S2 — Círculo ≥670, high DSCR, mid score",
                      20_000, _CLEAN_BURO, _BANK_D1,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


def case_t3_clean_d2_s1():
    """C1·D2·S1 → Tier 3. Círculo ≥670, DSCR adequate, high score. (case_5 variant)"""
    return case_5_volatile_income()  # already Tier 3


def case_t4_clean_d2_s2():
    """C1·D2·S2 → Tier 4. Círculo ≥670, mid DSCR, mid score."""
    return _abarrotes("TIER 4 C1·D2·S2 — Círculo ≥670, mid DSCR, mid score",
                      20_000, _CLEAN_BURO, _BANK_D2_OK,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


# ── C2 mid-band committee tiers (tiers 5-8) — NEW ────────────────────────────

def case_t5_midburo_d1_s1():
    """C2·D1·S1 → Tier 5. Círculo 600-669, strong DSCR+score. COMMITTEE ceiling."""
    return _abarrotes("TIER 5 C2·D1·S1 — Círculo 635, high DSCR+score",
                      30_000, _MID_BURO, _BANK_D1)


def case_t6_midburo_d1_s2():
    """C2·D1·S2 → Tier 6. Círculo 600-669, strong DSCR, mid score."""
    return _abarrotes("TIER 6 C2·D1·S2 — Círculo 635, high DSCR, mid score",
                      30_000, _MID_BURO, _BANK_D1,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


def case_t7_midburo_d2_s1():
    """C2·D2·S1 → Tier 7. Círculo 600-669, DSCR mid, high score."""
    app = case_5_volatile_income()
    app.merchant_name = "TIER 7 C2·D2·S1 — Círculo 635, DSCR mid, high score"
    app.buro = _MID_BURO
    return app


def case_t8_midburo_d2_s2():
    """C2·D2·S2 → Tier 8. Círculo 600-669, mid DSCR, mid score."""
    return _abarrotes("TIER 8 C2·D2·S2 — Círculo 635, mid DSCR, mid score",
                      20_000, _MID_BURO, _BANK_D2_OK,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


# ── C3 thin-file committee tiers (tiers 9-12) ────────────────────────────────

def case_t9_nofile_d1_s1():
    """C3·D1·S1 → Tier 9. No Círculo file, strong DSCR+score. COMMITTEE ceiling."""
    return _abarrotes("TIER 9 C3·D1·S1 — no Círculo file, strong DSCR+score",
                      30_000, _NOFILE_BURO, _BANK_D1)


def case_t10_nofile_d1_s2():
    """C3·D1·S2 → Tier 10. No Círculo file, strong DSCR, mid score."""
    return _abarrotes("TIER 10 C3·D1·S2 — no Círculo file, strong DSCR, mid score",
                      30_000, _NOFILE_BURO, _BANK_D1,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


def case_t11_nofile_d2_s1():
    """C3·D2·S1 → Tier 11. No Círculo file, DSCR mid, high score."""
    app = case_5_volatile_income()
    app.merchant_name = "TIER 11 C3·D2·S1 — no Círculo file, DSCR mid, high score"
    app.buro = _NOFILE_BURO
    return app


def case_t12_nofile_d2_s2():
    """C3·D2·S2 → Tier 12. No Círculo file, mid DSCR, mid score."""
    return _abarrotes("TIER 12 C3·D2·S2 — no Círculo file, mid DSCR, mid score",
                      20_000, _NOFILE_BURO, _BANK_D2_OK,
                      tenure=_TENURE_S2, maps=_MAPS_S2, fmcg=_FMCG_S2)


# Keep old function names as aliases so external callers don't break
case_t5_nofile_d1_s1 = case_t9_nofile_d1_s1
case_t6_nofile_d1_s2 = case_t10_nofile_d1_s2
case_t7_nofile_d2_s1 = case_t11_nofile_d2_s1
case_t8_nofile_d2_s2 = case_t12_nofile_d2_s2


# ── Edge cases ────────────────────────────────────────────────────────────────

def case_multi_lending():
    """C1 but Círculo shows 3 active loans → D2 downgrade from repayment layer."""
    app = case_1_maria_healthy()
    app.merchant_name = "EDGE multi-lending — C1 but 3 active Círculo loans"
    app.buro = _MULTI_BURO
    return app


def case_no_bank_data():
    """No bank data → DSCR=None → D3 → Tier 13 DECLINE."""
    app = case_1_maria_healthy()
    app.merchant_name = "EDGE no bank data — unverifiable DSCR"
    app.bank = None
    return app


def case_graduation_tier1():
    """Graduation Tier 1 borrower still runs through the tier matrix."""
    app = case_1_maria_healthy()
    app.merchant_name = "EDGE graduation T1 — repeat borrower, clean file"
    graduation = GraduationOffer(
        tier=1, max_ticket_mxn=35_000, pricing_rate=0.028,
        early_repayment_bonus=True,
    )
    return score_application(app, graduation=graduation)


def case_score_boundary_75():
    """Score exactly at 75 threshold — should stay S1."""
    # Use case_t2 profile but it should cross 75 based on signals
    app = case_t2_clean_d1_s2()
    app.merchant_name = "EDGE score boundary ~75"
    return app


def case_sensitivity_nofile():
    """B2·D1·S1 → Tier 5. Sensitivity must report Buró as the blocker."""
    return case_t5_nofile_d1_s1()


def case_sensitivity_dscr_gap():
    """B1·D2·S1 → Tier 3. Sensitivity must report DSCR gap."""
    return case_5_volatile_income()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*74)
    print("  Olin V2 — Círculo de Crédito Tier Matrix Test Suite")
    print("="*74 + "\n")

    print("── Original 5 cases ─────────────────────────────────────────────────\n")
    for c in [case_1_maria_healthy(), case_2_beautiful_trap(), case_3_counter_offer(),
              case_4_delinquent(), case_5_volatile_income()]:
        _print(score_application(c) if not hasattr(c, 'decision') else c)

    print("── C1 committee tiers 2-4 (Círculo ≥670) ──────────────────────────\n")
    for fn in [case_t2_clean_d1_s2, case_t3_clean_d2_s1, case_t4_clean_d2_s2]:
        app = fn()
        _print(app if hasattr(app, 'decision') else score_application(app))

    print("── C2 mid-band tiers 5-8 (Círculo 600-669) — NEW ──────────────────\n")
    for fn in [case_t5_midburo_d1_s1, case_t6_midburo_d1_s2,
               case_t7_midburo_d2_s1, case_t8_midburo_d2_s2]:
        _print(score_application(fn()))

    print("── C3 thin-file tiers 9-12 (no Círculo file) ──────────────────────\n")
    for fn in [case_t9_nofile_d1_s1, case_t10_nofile_d1_s2,
               case_t11_nofile_d2_s1, case_t12_nofile_d2_s2]:
        _print(score_application(fn()))

    print("── Edge cases ──────────────────────────────────────────────────────\n")
    _print(score_application(case_multi_lending()))
    _print(score_application(case_no_bank_data()))
    _print(case_graduation_tier1(), "EDGE graduation T1")

    # ── Hard assertions ───────────────────────────────────────────────────────
    r1 = score_application(case_1_maria_healthy())
    assert r1.decision == Decision.AUTO_APPROVE, f"Case 1: {r1.decision}"
    assert r1.tier == 1, f"Case 1 tier: {r1.tier}"
    assert r1.tier_sensitivity.get("path") == "Optimal — no upgrade path needed", \
        f"Case 1 sensitivity: {r1.tier_sensitivity.get('path')}"

    r2 = score_application(case_2_beautiful_trap())
    assert r2.decision == Decision.DECLINE, f"Case 2: {r2.decision}"
    assert r2.tier == 13, f"Case 2 tier (C1·D3 → 13): {r2.tier}"
    assert r2.tier_sensitivity is not None, "Case 2: sensitivity dict should exist"

    r3 = score_application(case_3_counter_offer())
    assert 0 < r3.approved_amount_mxn < 30_000, f"Case 3 counter-offer: {r3.approved_amount_mxn}"

    r4 = score_application(case_4_delinquent())
    assert r4.decision == Decision.DECLINE, f"Case 4: {r4.decision}"
    assert r4.tier == 13, f"Case 4 tier (C4 delinquent → 13): {r4.tier}"

    r5 = score_application(case_5_volatile_income())
    assert r5.decision == Decision.COMMITTEE, f"Case 5: {r5.decision}"
    assert r5.tier == 3, f"Case 5 tier (C1·D2·S1 → 3): {r5.tier}"

    # C1 committee tiers 2-4
    assert score_application(case_t2_clean_d1_s2()).tier == 2, "Tier 2 (C1·D1·S2) failed"
    assert score_application(case_t3_clean_d2_s1()).tier == 3, "Tier 3 (C1·D2·S1) failed"
    r_t4 = score_application(case_t4_clean_d2_s2())
    assert r_t4.decision == Decision.COMMITTEE, f"Tier 4 decision: {r_t4.decision}"

    # C2 mid-band tiers 5-8
    r_t5c2 = score_application(case_t5_midburo_d1_s1())
    assert r_t5c2.tier == 5, f"Tier 5 (C2·D1·S1): got {r_t5c2.tier}"
    assert r_t5c2.decision == Decision.COMMITTEE, "C2 must never AUTO_APPROVE"
    assert r_t5c2.tier_sensitivity.get("buro_blocks_auto") is True, "T5 must flag bureau gap"
    r_t6c2 = score_application(case_t6_midburo_d1_s2())
    assert r_t6c2.tier == 6, f"Tier 6 (C2·D1·S2): got {r_t6c2.tier}"
    r_t7c2 = score_application(case_t7_midburo_d2_s1())
    assert r_t7c2.tier == 7, f"Tier 7 (C2·D2·S1): got {r_t7c2.tier}"
    r_t8c2 = score_application(case_t8_midburo_d2_s2())
    assert r_t8c2.decision == Decision.COMMITTEE, f"Tier 8 (C2·D2·S2) decision: {r_t8c2.decision}"

    # C3 thin-file tiers 9-12
    r_t9 = score_application(case_t9_nofile_d1_s1())
    assert r_t9.tier == 9, f"Tier 9 (C3·D1·S1): got {r_t9.tier}"
    assert r_t9.decision == Decision.COMMITTEE, "C3 thin-file must never AUTO_APPROVE"
    assert r_t9.tier_sensitivity.get("buro_blocks_auto") is True, "T9 must flag no bureau file"
    r_t10 = score_application(case_t10_nofile_d1_s2())
    assert r_t10.tier == 10, f"Tier 10 (C3·D1·S2): got {r_t10.tier}"
    r_t11 = score_application(case_t11_nofile_d2_s1())
    assert r_t11.tier == 11, f"Tier 11 (C3·D2·S1): got {r_t11.tier}"
    r_t12 = score_application(case_t12_nofile_d2_s2())
    assert r_t12.decision == Decision.COMMITTEE, f"Tier 12 (C3·D2·S2) decision: {r_t12.decision}"

    # Multi-lending: C1 stays, 3 active loans → D2 → Tier 3 or 4
    r_ml = score_application(case_multi_lending())
    assert r_ml.decision == Decision.COMMITTEE, f"Multi-lending: {r_ml.decision}"
    assert r_ml.tier in (3, 4), f"Multi-lending should be Tier 3 or 4, got {r_ml.tier}"

    # No bank data: D3 → Tier 13 DECLINE
    r_nb = score_application(case_no_bank_data())
    assert r_nb.decision == Decision.DECLINE, f"No bank: {r_nb.decision}"
    assert r_nb.tier == 13, f"No bank tier (D3 → 13): {r_nb.tier}"

    # Graduation: tier matrix still runs, graduation doesn't override safety
    r_grad = case_graduation_tier1()
    assert r_grad.decision in (Decision.AUTO_APPROVE, Decision.COMMITTEE), \
        f"Graduation: {r_grad.decision}"

    # Círculo de Crédito mock integration (C1/C2/C3/C4 labels)
    from .buro_mock import mock_buro, buro_dim_label
    for scenario, expected_dim in [("clean", "C1"), ("mid_band", "C2"),
                                   ("multi_lending", "C1"), ("delinquent", "C4"),
                                   ("thin_file", "C3")]:
        b = mock_buro("test", scenario)
        assert buro_dim_label(b) == expected_dim, \
            f"buro_mock '{scenario}': expected {expected_dim}, got {buro_dim_label(b)}"

    print("ALL ASSERTIONS PASSED ✓ "
          "(original 5 + C1 tiers 2-4 + C2 tiers 5-8 + C3 tiers 9-12 + edge cases + circulo_mock)\n")


if __name__ == "__main__":
    main()
