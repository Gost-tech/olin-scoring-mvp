"""
Olin · Bank Data Mock (Syncfy fallback)

Generates realistic BankData for development and testing when Syncfy
credentials are unavailable (plan limitation, no internet, or offline dev).

Scenarios mirror the Círculo de Crédito profiles so they can be paired:
  "healthy"       — D1: strong DSCR candidate, regular deposits, growing balance
  "adequate"      — D2: decent cash flow, some volatility, borderline DSCR
  "stressed"      — D3: thin margins, irregular deposits, declining balance
  "cash_only"     — No bank account: returns None (signal absent)
  "auto"          — Deterministic from merchant_name hash

Distribution observed in CDMX micro-merchant segment:
  ~40% healthy, ~35% adequate, ~15% stressed, ~10% cash-only

Usage:
    from olin.bank_mock import mock_bank
    app.bank = mock_bank("Tortillería La Paloma", scenario="healthy")
"""
from __future__ import annotations

import hashlib
from typing import Literal, Optional

from .models import BankData

Scenario = Literal["healthy", "adequate", "stressed", "cash_only", "auto"]

_PROFILES: dict[str, BankData] = {
    # D1 candidate: DSCR ≥ 2.5, consistent weekly deposits, positive trend
    "healthy": BankData(
        months_connected=6.0,
        avg_daily_balance_mxn=18_500.0,
        monthly_deposit_count=22.0,       # ~daily deposits
        monthly_deposit_volume_mxn=85_000.0,
        monthly_outflow_volume_mxn=48_000.0,
        deposit_regularity=0.88,
        overdrafts_90d=0,
        balance_trend_90d=0.18,           # growing
        min_daily_balance_mxn=4_200.0,
        source="mock_sandbox",
        verified=False,
    ),
    # D2 candidate: DSCR 1.5–2.5, some volatility, flat trend
    "adequate": BankData(
        months_connected=4.0,
        avg_daily_balance_mxn=7_800.0,
        monthly_deposit_count=14.0,
        monthly_deposit_volume_mxn=42_000.0,
        monthly_outflow_volume_mxn=31_000.0,
        deposit_regularity=0.62,
        overdrafts_90d=1,
        balance_trend_90d=0.02,           # flat
        min_daily_balance_mxn=800.0,
        source="mock_sandbox",
        verified=False,
    ),
    # D3 candidate: DSCR < 1.5, irregular, declining
    "stressed": BankData(
        months_connected=2.5,
        avg_daily_balance_mxn=2_100.0,
        monthly_deposit_count=8.0,
        monthly_deposit_volume_mxn=18_000.0,
        monthly_outflow_volume_mxn=16_500.0,
        deposit_regularity=0.31,
        overdrafts_90d=4,
        balance_trend_90d=-0.22,          # declining
        min_daily_balance_mxn=-300.0,
        source="mock_sandbox",
        verified=False,
    ),
}

_AUTO_WEIGHTS = [
    ("healthy",  range(0,  40)),
    ("adequate", range(40, 75)),
    ("stressed", range(75, 90)),
    ("cash_only",range(90, 100)),
]


def mock_bank(identifier: str, scenario: Scenario = "auto") -> Optional[BankData]:
    """
    Return synthetic BankData for the given scenario.
    Returns None for cash_only (signal absent, not scored).

    Args:
        identifier: merchant name or RFC — seeds deterministic auto mode
        scenario:   "auto" uses MD5 hash of identifier for repeatability
    """
    if scenario == "auto":
        h = int(hashlib.md5(identifier.encode()).hexdigest(), 16) % 100
        for sc, rng in _AUTO_WEIGHTS:
            if h in rng:
                scenario = sc  # type: ignore[assignment]
                break
        else:
            scenario = "healthy"

    if scenario == "cash_only":
        return None

    p = _PROFILES[scenario]
    return BankData(
        months_connected=p.months_connected,
        avg_daily_balance_mxn=p.avg_daily_balance_mxn,
        monthly_deposit_count=p.monthly_deposit_count,
        monthly_deposit_volume_mxn=p.monthly_deposit_volume_mxn,
        monthly_outflow_volume_mxn=p.monthly_outflow_volume_mxn,
        deposit_regularity=p.deposit_regularity,
        overdrafts_90d=p.overdrafts_90d,
        balance_trend_90d=p.balance_trend_90d,
        min_daily_balance_mxn=p.min_daily_balance_mxn,
        source=p.source,
        verified=False,
    )


def dscr_label(bank: Optional[BankData], loan_mxn: float, rate: float = 0.06) -> str:
    """Quick DSCR estimate label for display (D1/D2/D3/unknown)."""
    if bank is None or bank.monthly_deposit_volume_mxn == 0:
        return "unknown"
    monthly_payment = loan_mxn * (1 + rate) / 2
    net = bank.monthly_deposit_volume_mxn - bank.monthly_outflow_volume_mxn
    if monthly_payment <= 0:
        return "unknown"
    dscr = net / monthly_payment
    if dscr >= 2.5:
        return "D1"
    if dscr >= 1.5:
        return "D2"
    return "D3"


# ── Standalone demo ────────────────────────────────────────────────────────
if __name__ == "__main__":
    _G = "\033[92m"; _A = "\033[93m"; _R = "\033[91m"
    _B = "\033[1m";  _X = "\033[0m";  _M = "\033[90m"

    print(f"\n  {_B}Olin · Bank Mock Profiles{_X}\n")
    test_merchants = [
        "Tortillería La Paloma",
        "Abarrotes Don Pepe",
        "Taquería El Güero",
        "Jugos y Licuados Mary",
        "Carnicería La Reforma",
    ]
    for name in test_merchants:
        b = mock_bank(name, "auto")
        if b is None:
            print(f"  {name:<30}  {_M}cash_only — no bank signal{_X}")
        else:
            label = dscr_label(b, 30_000)
            col = _G if label == "D1" else (_A if label == "D2" else _R)
            net = b.monthly_deposit_volume_mxn - b.monthly_outflow_volume_mxn
            print(f"  {name:<30}  {col}{label}{_X}  "
                  f"balance={b.avg_daily_balance_mxn:>8,.0f}  "
                  f"net/mo={net:>8,.0f}  "
                  f"reg={b.deposit_regularity:.2f}  ({b.source})")
    print()
