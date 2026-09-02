from __future__ import annotations

import unittest

from olin.business_comparison import build_public_peer_comparison


def peer(identifier: str, distance: float, size: str = "0 a 5 personas") -> dict:
    return {
        "denueId": identifier,
        "name": f"Peer {identifier}",
        "activity": "Comercio al por menor de abarrotes",
        "scianCode": "461110",
        "sizeBand": size,
        "distanceM": distance,
    }


class BusinessComparisonTests(unittest.TestCase):
    def test_small_cohort_is_suppressed(self):
        result = build_public_peer_comparison([peer("1", 100), peer("2", 250)])
        self.assertEqual(result["status"], "insufficient_cohort")
        self.assertNotIn("peerMetrics", result)
        self.assertFalse(result["creditDecisionUse"])

    def test_sufficient_cohort_returns_only_aggregate_benchmark(self):
        records = [peer(str(index), 100 * index) for index in range(1, 7)]
        result = build_public_peer_comparison(records)
        self.assertEqual(result["status"], "benchmark_available")
        self.assertEqual(result["cohortSize"], 6)
        self.assertEqual(result["peerMetrics"]["medianDistanceM"], 350.0)
        self.assertNotIn("records", result)
        self.assertNotIn("rank", result)
        self.assertFalse(result["creditDecisionUse"])
        self.assertEqual(result["permittedUse"], "market_context_only")

    def test_missing_optional_fields_do_not_create_negative_evidence(self):
        records = [peer(str(index), 100 * index, "") for index in range(1, 7)]
        result = build_public_peer_comparison(records)
        self.assertEqual(result["peerMetrics"]["sizeBandCoverage"], 0.0)
        self.assertIn("neutral", " ".join(result["limitations"]).lower())


if __name__ == "__main__":
    unittest.main()
