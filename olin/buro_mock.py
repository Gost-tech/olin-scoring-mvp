"""
Olin · Círculo de Crédito Mock

Simulates realistic Círculo de Crédito responses for development and testing
without spending MXN 50/query on the real API (circulodecredito.com.mx).

Scenarios:
  "clean"        — C1: score 720, 0 delinquencies, 1 active loan
  "mid_band"     — C2: score 635, 0 delinquencies (committee ceiling)
  "multi_lending"— C1 with soft-flag: 3+ active loans (DSCR downgrade)
  "delinquent"   — C4: score 520, active delinquencies → DECLINE tier 13
  "thin_file"    — C3: not checked (no file on record) → COMMITTEE ceiling
  "auto"         — deterministic based on merchant_name hash

Usage in tests:
    from olin.buro_mock import mock_buro
    app.buro = mock_buro("CHGU850101AB2", scenario="clean")

Usage in batch / CI:
    from olin.buro_mock import patch_apps_for_testing
    apps = patch_apps_for_testing(apps)   # auto-assigns scenarios
"""
from __future__ import annotations

import hashlib
from typing import Literal

from .models import BuroData

Scenario = Literal["clean", "mid_band", "multi_lending", "delinquent", "thin_file", "auto"]

# Realistic Círculo de Crédito profiles used in Mexican micro-merchant segment
_PROFILES: dict[str, BuroData] = {
    "clean": BuroData(
        checked=True,
        active_delinquencies=0,
        active_loans_count=1,
        worst_mob_status="01",   # al corriente
        score=720,               # C1: ≥670
    ),
    "mid_band": BuroData(
        checked=True,
        active_delinquencies=0,
        active_loans_count=1,
        worst_mob_status="01",
        score=635,               # C2: 600-669 — COMMITTEE ceiling
    ),
    "multi_lending": BuroData(
        checked=True,
        active_delinquencies=0,
        active_loans_count=3,    # triggers soft downgrade in assess_repayment
        worst_mob_status="01",
        score=695,               # C1: still high-band despite multiple loans
    ),
    "delinquent": BuroData(
        checked=True,
        active_delinquencies=2,
        active_loans_count=4,
        worst_mob_status="04",   # 90+ DPD
        score=520,               # C4: <600 AND delinquent
    ),
    "thin_file": BuroData(
        checked=False,           # C3: no file — forces COMMITTEE ceiling
        active_delinquencies=0,
        active_loans_count=0,
        score=None,
    ),
}

# Distribution that mirrors observed MX micro-merchant Círculo population:
#   ~45% clean (C1), ~15% mid-band (C2), ~15% multi-lending (C1+soft), ~10% delinquent (C4), ~15% thin-file (C3)
_AUTO_WEIGHTS = [
    ("clean",         range(0,  45)),
    ("mid_band",      range(45, 60)),
    ("multi_lending", range(60, 75)),
    ("delinquent",    range(75, 85)),
    ("thin_file",     range(85, 100)),
]


def mock_buro(identifier: str, scenario: Scenario = "auto") -> BuroData:
    """
    Return a synthetic BuroData for testing.

    Args:
        identifier: merchant RFC, CLABE, or name — used to seed deterministic auto mode
        scenario:   which profile to use ("auto" = hash-based determinism)
    """
    if scenario == "auto":
        h = int(hashlib.md5(identifier.encode()).hexdigest(), 16) % 100
        for sc, rng in _AUTO_WEIGHTS:
            if h in rng:
                scenario = sc  # type: ignore[assignment]
                break
        else:
            scenario = "clean"

    p = _PROFILES[scenario]
    return BuroData(
        checked              = p.checked,
        active_delinquencies = p.active_delinquencies,
        active_loans_count   = p.active_loans_count,
        worst_mob_status     = p.worst_mob_status,
        score                = p.score,
    )


def buro_dim_label(buro: BuroData) -> str:
    """Return the Círculo de Crédito dimension label (C1/C2/C3/C4) for display / testing."""
    from .scorecard import CIRCULO_HIGH_BAND, CIRCULO_MID_BAND
    if not buro.checked:
        return "C3"   # thin-file
    if buro.active_delinquencies > 0:
        return "C4"   # delinquent
    if buro.score is None:
        return "C1"   # backward-compat: checked but no score
    if buro.score >= CIRCULO_HIGH_BAND:
        return "C1"
    if buro.score >= CIRCULO_MID_BAND:
        return "C2"
    return "C4"       # score < 600


def patch_apps_for_testing(apps: list, scenario: Scenario = "auto") -> list:
    """
    Inject mock Buró data into a list of Application objects.
    Useful in batch tests where buro=None would force Tier 14.
    """
    for app in apps:
        if app.buro is None or not app.buro.checked:
            identifier = app.fraud.rfc if (app.fraud and app.fraud.rfc) else app.merchant_name
            app.buro = mock_buro(identifier, scenario)
    return apps


# ── Standalone demo ────────────────────────────────────────────────────────
if __name__ == "__main__":
    _G = "\033[92m"; _A = "\033[93m"; _R = "\033[91m"; _M = "\033[90m"
    _B = "\033[1m";  _X = "\033[0m"

    print(f"\n  {_B}Olin · Círculo de Crédito Mock Profiles{_X}\n")
    test_ids = ["CHGU850101AB2", "GURE900215CD3", "LENA010115MH0", "AABC800101ABC", "XYZF910601DE4"]
    for rfc in test_ids:
        b = mock_buro(rfc, "auto")
        dim = buro_dim_label(b)
        col = _G if dim == "C1" else (_A if dim in ("C2", "C3") else _R)
        status = "checked" if b.checked else "not checked"
        score_str = f"  score={b.score}" if b.score else ""
        print(f"  {rfc}  →  {col}{dim}{_X}  delq={b.active_delinquencies}  "
              f"loans={b.active_loans_count}{score_str}  ({status})")
    print()
