"""
Integration test: ofmockbank_br_retail -> BankData -> Scorecard

Mocks requests.post / requests.get with the exact JSON schema that Belvo
returns for ofmockbank_br_retail so the full pipeline can be validated
without needing an active link.

Run:
    python3 test_belvo_pipeline.py
"""
from __future__ import annotations

import json
import statistics
import sys
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Build a realistic 90-day transaction dataset (ofmockbank format)
# ---------------------------------------------------------------------------

def _make_transactions(
    days: int = 90,
    daily_deposits: int = 2,       # MXN small business: 2 deposits/day
    avg_deposit: float = 1_800,
    weekly_expense: float = 9_500,
    starting_balance: float = 14_000,
    overdraft_days: list[int] = None,
) -> list[dict]:
    """
    Generate transactions in Belvo's exact JSON format for ofmockbank_br_retail.
    The schema is identical to any Belvo bank institution.
    """
    txns = []
    today = date.today()
    balance = starting_balance
    account_id = uuid.uuid4().hex

    for day_offset in range(days - 1, -1, -1):
        d = (today - timedelta(days=day_offset)).isoformat()

        # Daily deposits (INFLOW) – cash sales for an abarrotes
        for i in range(daily_deposits):
            amount = avg_deposit * (0.9 + 0.2 * ((day_offset * 7 + i) % 10) / 10)
            balance += amount
            txns.append({
                "id": uuid.uuid4().hex,
                "account": {"id": account_id, "name": "Conta Corrente",
                             "category": "CHECKING_ACCOUNT", "currency": "BRL"},
                "collected_at": f"{d}T10:00:00Z",
                "created_at":   f"{d}T10:00:00Z",
                "value_date":      d,
                "accounting_date": d,
                "amount": round(amount, 2),
                "balance": round(balance, 2),
                "currency": "BRL",
                "description": f"Venta dia {day_offset}-{i}",
                "observations": None,
                "category": "INCOME",
                "subcategory": None,
                "reference": f"REF{day_offset:03d}{i}",
                "type": "INFLOW",
                "status": "PROCESSED",
                "merchant": None,
            })

        # Weekly restocking expense (OUTFLOW) every 7 days
        if day_offset % 7 == 0:
            balance -= weekly_expense
            # Simulate one overdraft event if specified
            if overdraft_days and day_offset in overdraft_days:
                balance -= 5_000  # extra outflow that goes negative
            txns.append({
                "id": uuid.uuid4().hex,
                "account": {"id": account_id, "name": "Conta Corrente",
                             "category": "CHECKING_ACCOUNT", "currency": "BRL"},
                "collected_at": f"{d}T18:00:00Z",
                "created_at":   f"{d}T18:00:00Z",
                "value_date":      d,
                "accounting_date": d,
                "amount": round(weekly_expense, 2),
                "balance": round(balance, 2),
                "currency": "BRL",
                "description": "FEMSA/Bimbo reposicion",
                "observations": None,
                "category": "EXPENSE",
                "subcategory": "FOOD_AND_GROCERIES",
                "reference": f"RSTK{day_offset:03d}",
                "type": "OUTFLOW",
                "status": "PROCESSED",
                "merchant": None,
            })

    return txns


# ---------------------------------------------------------------------------
# Mock Belvo HTTP responses
# ---------------------------------------------------------------------------

def _mock_post(url, auth=None, json=None, timeout=None, **_):
    """Intercepts requests.post inside olin/belvo.py"""
    mock = MagicMock()
    mock.status_code = 200
    if "links" in url:
        mock.json.return_value = {"id": "fake-link-ofmock-0001"}
        mock.raise_for_status = lambda: None
    elif "transactions" in url:
        txns = _TRANSACTIONS
        mock.json.return_value = txns          # flat list (retrieve endpoint)
        mock.raise_for_status = lambda: None
    return mock


def _mock_get(url, auth=None, params=None, timeout=None, **_):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"count": 5, "next": None,
                               "results": [{"name": "ofmockbank_br_retail"}]}
    mock.raise_for_status = lambda: None
    return mock


# ---------------------------------------------------------------------------
# Pretty print helpers
# ---------------------------------------------------------------------------

def _bar(value: float, width: int = 30) -> str:
    filled = int(round(value / 100 * width))
    return "█" * filled + "░" * (width - filled)

def _print_result(res) -> None:
    print("=" * 72)
    print(f"  {res.merchant_name}")
    print(f"  App ID : {res.application_id}")
    print(f"  Score  : {res.score}   CI [{res.ci_low} – {res.ci_high}]")
    print(f"  {_bar(res.score)}")
    print(f"  Coverage : {res.data_coverage:.0%}")
    print()
    decision_color = {
        "AUTO_APPROVE":  "✅",
        "MANUAL_REVIEW": "🟡",
        "DECLINE":       "❌",
    }
    print(f"  DECISION: {decision_color.get(res.decision.value,'')} {res.decision.value}")
    for r in res.decision_reasons:
        print(f"    • {r}")
    if res.approved_amount_mxn > 0:
        print(f"\n  Approved: MXN {res.approved_amount_mxn:>10,.0f}")
        print(f"  Fixed cost: MXN {res.pricing_fixed_cost_mxn:>7,.0f}  (60 days, 2 payments)")
    print()
    print("  SIGNALS:")
    for s in res.signals:
        if s.available:
            fb = f" [fallback: {s.fallback_used}]" if s.fallback_used else ""
            src = "Belvo ✓" if s.name == "bank_cash_flow" and not s.fallback_used else ""
            print(f"    {s.name:28s}  {s.raw_score:5.1f}  w={s.effective_weight:.2f}  {src}{fb}")
            print(f"    {'':28s}  {s.explanation}")
        else:
            print(f"    {s.name:28s}  MISSING  {s.explanation}")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# 90 days of transactions for a healthy abarrotes
_TRANSACTIONS = _make_transactions(
    days=90,
    daily_deposits=2,
    avg_deposit=1_800,
    weekly_expense=9_500,
    starting_balance=14_000,
)

_TRANSACTIONS_STRESSED = _make_transactions(
    days=90,
    daily_deposits=1,
    avg_deposit=900,
    weekly_expense=9_000,
    starting_balance=8_000,
    overdraft_days=[7, 14],
)


def run_tests():
    from olin.models import (
        Application, BusinessType, BuroData, FraudData,
        FMCGData, TenureData, MapsRatingData, IMSSPayrollData,
    )
    from olin.scorecard import score_application

    print("\n" + "─" * 72)
    print("  OLIN SCORING — BELVO PIPELINE TEST")
    print("  Institution: ofmockbank_br_retail (OF Mock Bank by Raidiam)")
    print("─" * 72 + "\n")

    # ── Inspect raw BankData output ─────────────────────────────────────────
    with patch("requests.post", side_effect=_mock_post), \
         patch("requests.get",  side_effect=_mock_get):

        from olin.belvo import fetch_bank_data, create_link_and_fetch

        # Case A: fetch from existing link
        bank_healthy = fetch_bank_data("fake-link-ofmock-0001", days=90)

        # Swap transactions for stressed profile
        global _TRANSACTIONS
        orig = _TRANSACTIONS
        _TRANSACTIONS = _TRANSACTIONS_STRESSED
        bank_stressed = fetch_bank_data("fake-link-ofmock-0002", days=90)
        _TRANSACTIONS = orig

    print("┌─ BankData (healthy abarrotes) ─────────────────────────────────┐")
    print(f"│  source                 : {bank_healthy.source}")
    print(f"│  months_connected       : {bank_healthy.months_connected}")
    print(f"│  avg_daily_balance_mxn  : {bank_healthy.avg_daily_balance_mxn:>12,.2f}")
    print(f"│  monthly_deposit_count  : {bank_healthy.monthly_deposit_count}")
    print(f"│  deposit_regularity     : {bank_healthy.deposit_regularity}  (1.0 = perfectly consistent)")
    print(f"│  overdrafts_90d         : {bank_healthy.overdrafts_90d}")
    print(f"│  balance_trend_90d      : {bank_healthy.balance_trend_90d:+.3f}  (-1 = declining, +1 = growing)")
    print("└────────────────────────────────────────────────────────────────┘")
    print()

    assert bank_healthy.source == "belvo"
    assert bank_healthy.verified is True
    assert bank_stressed.source == "belvo"
    assert bank_stressed.verified is True
    print("┌─ BankData (stressed profile, overdrafts) ──────────────────────┐")
    print(f"│  source                 : {bank_stressed.source}")
    print(f"│  months_connected       : {bank_stressed.months_connected}")
    print(f"│  avg_daily_balance_mxn  : {bank_stressed.avg_daily_balance_mxn:>12,.2f}")
    print(f"│  monthly_deposit_count  : {bank_stressed.monthly_deposit_count}")
    print(f"│  deposit_regularity     : {bank_stressed.deposit_regularity}  (1.0 = perfectly consistent)")
    print(f"│  overdrafts_90d         : {bank_stressed.overdrafts_90d}")
    print(f"│  balance_trend_90d      : {bank_stressed.balance_trend_90d:+.3f}")
    print("└────────────────────────────────────────────────────────────────┘")
    print()

    # ── Full scorecard runs ─────────────────────────────────────────────────
    base_fmcg   = FMCGData(months_of_history=18, weekly_purchase_rate=0.92,
                            missed_weeks_last_12=1, distributor_confirmed=True, trend_3m=0.1)
    base_tenure = TenureData(years_on_google_maps=7, years_in_imss=5, address_consistent=True)
    base_maps   = MapsRatingData(rating=4.4, review_count=95, review_velocity_6m=6)
    base_imss   = IMSSPayrollData(registered_employees=1)

    cases = [
        ("Case 1 — Belvo healthy", bank_healthy),
        ("Case 2 — Belvo stressed", bank_stressed),
        ("Case 3 — Belvo absent", None),
    ]

    for label, bank in cases:
        print(f"\n{'─'*72}")
        print(f"  {label}")
        app = Application(
            merchant_name=label,
            business_type=BusinessType.ABARROTES,
            requested_amount_mxn=25_000,
            colonia="Iztapalapa",
            bank=bank,
            fmcg=base_fmcg,
            tenure=base_tenure,
            maps=base_maps,
            imss=base_imss,
            buro=BuroData(checked=True, active_delinquencies=0,
                          active_loans_count=1, worst_mob_status="01", score=720),
            fraud=FraudData(phone_mx="5512345678", rfc="CHGU850101AB2",
                            ine_checked=True, address_stated="Iztapalapa"),
        )
        result = score_application(app)
        assert result.application_id == app.application_id
        assert 0 <= result.score <= 100
        if bank is not None:
            bank_signal = next(s for s in result.signals if s.name == "bank_cash_flow")
            assert bank_signal.available is True
        _print_result(result)

    print("\n✓  Pipeline assertions passed — Belvo -> BankData -> Scorecard is wired.\n")


if __name__ == "__main__":
    run_tests()
