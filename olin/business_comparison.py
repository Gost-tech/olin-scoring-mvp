"""Privacy-minimized public peer benchmarks for analyst market context.

The output intentionally avoids borrower ranking and peer-level disclosure.
It is not a credit score and cannot be used as a sole adverse reason.
"""
from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Iterable


COMPARISON_VERSION = "public-peer-comparison-1.0.0"
MIN_PUBLIC_COHORT = 5


def _finite_nonnegative(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def build_public_peer_comparison(
    peer_records: Iterable[dict],
    *,
    minimum_cohort: int = MIN_PUBLIC_COHORT,
) -> dict:
    """Aggregate a DENUE-derived peer cohort without identifying its members."""
    threshold = max(MIN_PUBLIC_COHORT, int(minimum_cohort))
    rows = [row for row in peer_records if isinstance(row, dict)]
    base = {
        "comparisonVersion": COMPARISON_VERSION,
        "cohortSize": len(rows),
        "minimumCohort": threshold,
        "permittedUse": "market_context_only",
        "creditDecisionUse": False,
        "mayBeSoleDeclineReason": False,
        "limitations": [
            "Public directory peers describe the local market, not repayment capacity",
            "Missing optional peer attributes are neutral and never converted into adverse evidence",
            "No applicant rank or individual peer record is returned",
        ],
    }
    if len(rows) < threshold:
        return {**base, "status": "insufficient_cohort"}

    distances = [
        value for value in (_finite_nonnegative(row.get("distanceM")) for row in rows)
        if value is not None
    ]
    size_bands = [str(row.get("sizeBand") or "").strip() for row in rows]
    known_size_bands = [value for value in size_bands if value]
    scian_prefixes = [
        str(row.get("scianCode") or "").strip()[:4]
        for row in rows if str(row.get("scianCode") or "").strip()
    ]
    size_distribution = Counter(known_size_bands)
    scian_distribution = Counter(scian_prefixes)

    return {
        **base,
        "status": "benchmark_available",
        "peerMetrics": {
            "medianDistanceM": round(median(distances), 1) if distances else None,
            "distanceCoverage": round(len(distances) / len(rows), 3),
            "sizeBandCoverage": round(len(known_size_bands) / len(rows), 3),
            "sizeBandDistribution": dict(sorted(size_distribution.items())),
            "scianFourDigitDistribution": dict(sorted(scian_distribution.items())),
        },
    }
