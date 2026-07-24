"""
Olin · FMCG Purchase History Mock (FEMSA / Bimbo fallback)

Generates realistic FMCGData for development when distributor APIs are
unavailable. In production, this data comes from WhatsApp photos of
delivery receipts + distributor confirmation calls.

Scenarios:
  "strong"   — 18+ months, high cadence, no gaps, growing trend → ~96 pts
  "regular"  — 12 months, 75% cadence, 2 missed weeks, flat    → ~56 pts
  "weak"     — 6 months, 50% cadence, 4 missed weeks, declining → ~10 pts
  "auto"     — Deterministic from merchant_name hash

Distribution observed in CDMX FEMSA/Bimbo micro-merchant segment:
  ~35% strong, ~45% regular, ~20% weak
"""
from __future__ import annotations

import hashlib
from typing import Literal

from .models import FMCGData

Scenario = Literal["strong", "regular", "weak", "auto"]

_PROFILES: dict[str, FMCGData] = {
    "strong": FMCGData(
        months_of_history=18.0,
        weekly_purchase_rate=0.92,    # buys almost every week
        missed_weeks_last_12=0,
        avg_weekly_purchase_mxn=9_800.0,
        distributor_confirmed=True,
        trend_3m=0.25,                # growing volume
        source="mock_sandbox",
        verified=False,
    ),
    "regular": FMCGData(
        months_of_history=12.0,
        weekly_purchase_rate=0.75,
        missed_weeks_last_12=2,
        avg_weekly_purchase_mxn=5_500.0,
        distributor_confirmed=True,
        trend_3m=0.0,
        source="mock_sandbox",
        verified=False,
    ),
    "weak": FMCGData(
        months_of_history=6.0,
        weekly_purchase_rate=0.50,
        missed_weeks_last_12=4,
        avg_weekly_purchase_mxn=2_200.0,
        distributor_confirmed=True,
        trend_3m=-0.20,               # shrinking orders
        source="mock_sandbox",
        verified=False,
    ),
}

_AUTO_WEIGHTS = [
    ("strong",  range(0,  35)),
    ("regular", range(35, 80)),
    ("weak",    range(80, 100)),
]


def mock_fmcg(identifier: str, scenario: Scenario = "auto") -> FMCGData:
    """
    Return synthetic FMCGData for the given scenario.

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
            scenario = "regular"

    p = _PROFILES[scenario]
    return FMCGData(
        months_of_history=p.months_of_history,
        weekly_purchase_rate=p.weekly_purchase_rate,
        missed_weeks_last_12=p.missed_weeks_last_12,
        avg_weekly_purchase_mxn=p.avg_weekly_purchase_mxn,
        distributor_confirmed=p.distributor_confirmed,
        trend_3m=p.trend_3m,
        source="mock_sandbox",
        verified=False,
    )


# ── Standalone demo ────────────────────────────────────────────────────────
if __name__ == "__main__":
    from .signals import score_fmcg
    _G = "\033[92m"; _A = "\033[93m"; _R = "\033[91m"
    _B = "\033[1m";  _X = "\033[0m";  _M = "\033[90m"

    print(f"\n  {_B}Olin · FMCG Mock Profiles{_X}\n")
    test_ids = [
        "Abarrotes Don Pepe",
        "Tortillería La Paloma",
        "Taquería El Güero",
        "Carnicería La Reforma",
        "Jugos y Licuados Mary",
    ]
    for name in test_ids:
        f = mock_fmcg(name, "auto")
        sc, expl = score_fmcg(f)
        col = _G if (sc or 0) >= 70 else (_A if (sc or 0) >= 40 else _R)
        print(f"  {name:<30}  {col}{sc:5.1f}{_X}  {_M}{expl[:55]}{_X}")
    print()
