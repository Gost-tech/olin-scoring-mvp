#!/usr/bin/env python3
"""
Olin · End-to-end integration test (no external APIs)

Simulates a full loan lifecycle for a fake merchant — no Syncfy, no
Google Places, no real STP call. Everything runs locally against a
temporary SQLite database that is deleted at the end.

Scenario:
  Carmen Reyes — Abarrotes La Reforma, Iztapalapa CDMX

  Loan 1 (new borrower):
    portfolio check → Tier 0 → score → AUTO_APPROVE MXN 20,000
    → disburse (simulated) → 2 payments → repaid_on_time=1

  Loan 2 (repeat borrower):
    portfolio check → Tier 1 (earned) → score → AUTO_APPROVE MXN 25,000
    at 2.6%/month (vs 3.0% first time) because of graduation + early bonus

  Daily job run between loans: shows 0 overdue, 1 repaid, 0 defaulted

Run from project root:
    python3 test_full_flow.py
"""
from __future__ import annotations

import os
import sys
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from olin.models import (
    Application, BusinessType,
    FMCGData, BankData, TenureData, MapsRatingData,
    BuroData, FraudData,
)
from olin.scorecard import score_application
from olin.store import ScoringLog
from olin.portfolio import check_portfolio
from olin.graduation import get_graduation_offer
from olin.collection import (
    make_collection_ref, payment_schedule, process_incoming_payment,
)
from jobs.daily import run as daily_run

# ── ANSI ─────────────────────────────────────────────────────────────
GR = "\033[92m"; AM = "\033[93m"; RD = "\033[91m"
MU = "\033[90m"; CY = "\033[96m"; B  = "\033[1m";  R  = "\033[0m"

def ok(msg):   print(f"  {GR}✓{R}  {msg}")
def fail(msg): print(f"  {RD}✗{R}  {msg}"); sys.exit(1)
def info(msg): print(f"  {MU}·{R}  {MU}{msg}{R}")
def head(msg): print(f"\n  {B}{msg}{R}")
def sep(c="─", w=60): print(f"\n  {MU}{c*w}{R}")

# ── Fake merchant ─────────────────────────────────────────────────────
CLABE   = "002180700001234569"   # Banamex prefix + valid checksum
RFC     = "RECC850304AB1"
PHONE   = "5512345678"
COLONIA = "Iztapalapa Centro"
NAME    = "Carmen Reyes — Abarrotes La Reforma"

def make_app(requested_mxn: float) -> Application:
    return Application(
        merchant_name=NAME,
        business_type=BusinessType.ABARROTES,
        requested_amount_mxn=requested_mxn,
        colonia=COLONIA,
        clabe=CLABE,
        fmcg=FMCGData(
            months_of_history=15,
            weekly_purchase_rate=0.92,
            missed_weeks_last_12=0,
            avg_weekly_purchase_mxn=7_200,
            distributor_confirmed=True,
            trend_3m=0.10,
        ),
        bank=BankData(
            months_connected=3,
            avg_daily_balance_mxn=18_000,
            monthly_deposit_count=22,
            monthly_deposit_volume_mxn=72_000,
            monthly_outflow_volume_mxn=38_000,
            deposit_regularity=0.82,
            overdrafts_90d=0,
            balance_trend_90d=0.08,
            min_daily_balance_mxn=5_000,
        ),
        tenure=TenureData(
            years_on_google_maps=7.0,
            years_in_imss=0.0,
            address_consistent=True,
        ),
        pos=None,
        maps=MapsRatingData(rating=4.4, review_count=89, review_velocity_6m=6),
        imss=None,
        buro=BuroData(checked=True, active_delinquencies=0, active_loans_count=1, score=720),
        fraud=FraudData(
            phone_mx=PHONE,
            rfc=RFC,
            ine_checked=True,
            address_stated=f"{COLONIA} CDMX",
        ),
    )


def assert_eq(label: str, got, expected):
    if got == expected:
        ok(f"{label}: {got}")
    else:
        fail(f"{label}: expected {expected!r}, got {got!r}")

def assert_gt(label: str, got, threshold):
    if got > threshold:
        ok(f"{label}: {got} > {threshold}")
    else:
        fail(f"{label}: expected > {threshold}, got {got}")

def assert_lt(label: str, got, threshold):
    if got < threshold:
        ok(f"{label}: {got} < {threshold}")
    else:
        fail(f"{label}: expected < {threshold}, got {got}")


# ── Test runner ───────────────────────────────────────────────────────
def main():
    print()
    print(f"  {B}╔══════════════════════════════════════════════════════════╗{R}")
    print(f"  {B}║   Olin · End-to-End Integration Test                     ║{R}")
    print(f"  {B}╚══════════════════════════════════════════════════════════╝{R}")
    print(f"\n  Merchant : {B}{NAME}{R}")
    print(f"  CLABE    : {CLABE[:6]}{'*'*10}{CLABE[-2:]}")
    print(f"  RFC      : {RFC}")

    # Temporary DB — auto-deleted at end
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    info(f"Test DB  : {db_path}")

    results = {}   # store ScoreResult objects for assertions at the end

    try:
        # ══════════════════════════════════════════════════════════════
        sep("═")
        head("LOAN 1 — New borrower · requesting MXN 20,000")
        sep("═")

        app1 = make_app(20_000)

        # Step 1: Portfolio check
        head("Step 1 · Portfolio check")
        pf1 = check_portfolio(app1, db_path)
        if pf1.blocked:
            fail(f"Unexpected portfolio block: {pf1.reasons}")
        ok(f"No blocks (empty book)  warnings={pf1.warnings}")

        # Step 2: Graduation (new borrower)
        head("Step 2 · Graduation offer")
        grad1 = get_graduation_offer(CLABE, db_path)
        assert_eq("Tier", grad1.tier, 0)
        assert_eq("Max ticket MXN", grad1.max_ticket_mxn, 30_000.0)
        assert_eq("Rate", grad1.pricing_rate, 0.030)

        # Step 3: Score
        head("Step 3 · Scoring")
        r1 = score_application(app1, portfolio_block=pf1, graduation=grad1)
        results["loan1"] = r1
        info(f"Score    : {r1.score:.1f}  CI [{r1.ci_low:.1f}–{r1.ci_high:.1f}]")
        info(f"Decision : {r1.decision.value}")
        info(f"Approved : MXN {r1.approved_amount_mxn:,.0f}  cost MXN {r1.pricing_fixed_cost_mxn:,.0f}")
        if r1.repayment:
            info(f"DSCR     : {r1.repayment.dscr}  burden {r1.repayment.burden_ratio:.1%}")
        assert_eq("Decision", r1.decision.value, "AUTO_APPROVE")
        assert_eq("Approved MXN", r1.approved_amount_mxn, 20_000.0)
        assert_gt("Score", r1.score, 75.0)

        # Step 4: Log
        head("Step 4 · Log to DB")
        with ScoringLog(db_path) as log:
            log.log(app1, r1)
        ok(f"Saved  app_id={r1.application_id}")

        # Step 5: Simulate disbursement (bypass STP, write directly)
        head("Step 5 · Simulate disbursement")
        col_ref = make_collection_ref(r1.application_id)
        with ScoringLog(db_path) as log:
            log.log_disbursement(r1.application_id, f"OLIN_SIM_{r1.application_id[:8].upper()}", col_ref)
        sched = payment_schedule(r1.application_id, r1.approved_amount_mxn,
                                 r1.pricing_fixed_cost_mxn)
        p1_amount = sched["payment_1"]["amount_mxn"]
        p2_amount = sched["payment_2"]["amount_mxn"]
        ok(f"Folio : OLIN_SIM_{r1.application_id[:8].upper()}")
        ok(f"Ref   : {col_ref}")
        info(f"Pago 1 MXN {p1_amount:,.2f} due {sched['payment_1']['due_date']}")
        info(f"Pago 2 MXN {p2_amount:,.2f} due {sched['payment_2']['due_date']}")
        info(f"Total repayable: MXN {sched['total_repayable_mxn']:,.2f}")

        # Step 6: Payment 1 webhook
        head("Step 6 · Payment 1 webhook")
        pay1 = process_incoming_payment(
            {"claveRastreo": f"{col_ref}-P1", "monto": p1_amount},
            db_path,
        )
        if not pay1["matched"]:
            fail(f"Payment 1 not matched: {pay1}")
        ok(f"P1 matched  app={pay1['application_id']}  delta={pay1['delta']:.2f}")

        # Step 7: Payment 2 webhook → triggers repaid_on_time=1
        head("Step 7 · Payment 2 webhook → repaid_on_time")
        pay2 = process_incoming_payment(
            {"claveRastreo": f"{col_ref}-P2", "monto": p2_amount},
            db_path,
        )
        if not pay2["matched"]:
            fail(f"Payment 2 not matched: {pay2}")
        ok(f"P2 matched  app={pay2['application_id']}  delta={pay2['delta']:.2f}")

        # Verify repaid_on_time in DB
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT repaid_on_time, days_to_repay, payment_1_received, payment_2_received "
                "FROM scoring_log WHERE application_id=?",
                (r1.application_id,),
            ).fetchone()
        finally:
            conn.close()
        assert_eq("repaid_on_time", row[0], 1)
        assert_eq("payment_1_received", row[2], 1)
        assert_eq("payment_2_received", row[3], 1)
        ok(f"days_to_repay = {row[1]}")

        # ══════════════════════════════════════════════════════════════
        sep("═")
        head("DAILY JOB — between loans")
        sep("═")
        issues = daily_run(db_path, dry_run=False)
        assert_eq("Daily job issues", issues, 0)

        # ══════════════════════════════════════════════════════════════
        sep("═")
        head("LOAN 2 — Repeat borrower · requesting MXN 25,000")
        sep("═")

        app2 = make_app(25_000)

        # Step 1: Portfolio check (0 active loans after repayment)
        head("Step 1 · Portfolio check")
        pf2 = check_portfolio(app2, db_path)
        if pf2.blocked:
            fail(f"Unexpected portfolio block: {pf2.reasons}")
        ok(f"No blocks  active={pf2.stats.get('active_loans', '?')}")

        # Step 2: Graduation — should be Tier 1 now
        head("Step 2 · Graduation offer")
        grad2 = get_graduation_offer(CLABE, db_path)
        results["grad2"] = grad2
        info(f"Tier  : {grad2.tier}")
        info(f"Cap   : MXN {grad2.max_ticket_mxn:,.0f}")
        info(f"Rate  : {grad2.pricing_rate:.1%}/month")
        info(f"Notes : {grad2.notes}")
        assert_eq("Tier", grad2.tier, 1)
        assert_eq("Max ticket MXN", grad2.max_ticket_mxn, 50_000.0)
        # Rate should be 2.6% (2.8% Tier-1 base - 0.2% early-repayment bonus)
        assert_lt("Rate vs first loan", grad2.pricing_rate, 0.030)

        # Step 3: Score
        head("Step 3 · Scoring")
        r2 = score_application(app2, portfolio_block=pf2, graduation=grad2)
        results["loan2"] = r2
        info(f"Score    : {r2.score:.1f}")
        info(f"Decision : {r2.decision.value}")
        info(f"Approved : MXN {r2.approved_amount_mxn:,.0f}  cost MXN {r2.pricing_fixed_cost_mxn:,.0f}")
        assert_eq("Decision", r2.decision.value, "AUTO_APPROVE")
        assert_eq("Approved MXN", r2.approved_amount_mxn, 25_000.0)
        # Fixed cost at 2.6% should be 1,300 (vs 1,200 at 3.0% for 20K — same rate, larger amount, still cheaper per MXN)
        assert_lt("Cost rate vs Loan 1", r2.pricing_fixed_cost_mxn / r2.approved_amount_mxn,
                  r1.pricing_fixed_cost_mxn / r1.approved_amount_mxn)

        # Step 4: Log second loan
        head("Step 4 · Log to DB")
        with ScoringLog(db_path) as log2:
            log2.log(app2, r2)
            log2.conn.execute(
                "UPDATE scoring_log SET graduation_tier=? WHERE application_id=?",
                (grad2.tier, r2.application_id),
            )
            log2.conn.commit()
        ok(f"Saved  app_id={r2.application_id}  graduation_tier={grad2.tier}")

        # ══════════════════════════════════════════════════════════════
        sep("═")
        head("FINAL ASSERTIONS")
        sep("═")

        r1 = results["loan1"]
        r2 = results["loan2"]
        g2 = results["grad2"]

        assert_eq("Loan 1 decision",          r1.decision.value,          "AUTO_APPROVE")
        assert_eq("Loan 2 decision",          r2.decision.value,          "AUTO_APPROVE")
        assert_eq("Graduation tier after L1", g2.tier,                    1)
        assert_lt("Loan 2 rate < Loan 1 rate",
                  g2.pricing_rate, 0.030)
        assert_lt("Loan 2 cost/MXN cheaper",
                  r2.pricing_fixed_cost_mxn / r2.approved_amount_mxn,
                  r1.pricing_fixed_cost_mxn / r1.approved_amount_mxn)
        assert_gt("Loan 2 cap > Loan 1 cap",  g2.max_ticket_mxn,         30_000.0)

        sep("═")
        print(f"\n  {GR}{B}ALL ASSERTIONS PASSED{R}\n")
        print(f"  {MU}Loan 1{R}  MXN {r1.approved_amount_mxn:,.0f}  "
              f"cost {r1.pricing_fixed_cost_mxn:,.0f}  rate 3.0%  Tier 0")
        print(f"  {MU}Loan 2{R}  MXN {r2.approved_amount_mxn:,.0f}  "
              f"cost {r2.pricing_fixed_cost_mxn:,.0f}  rate {g2.pricing_rate:.1%}  Tier 1"
              + (f"  {GR}(early bonus){R}" if g2.early_repayment_bonus else ""))
        print()

    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
