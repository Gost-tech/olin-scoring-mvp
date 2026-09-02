"""Regression gate for concurrent bank API behavior."""
from __future__ import annotations

import unittest

from scripts.stress_test import run_stress


class StressResilienceTests(unittest.TestCase):
    def test_concurrent_bank_workflow_preserves_invariants(self):
        report = run_stress(reads=80, writes=40, concurrency=16)
        self.assertTrue(report["passed"], report)
        self.assertTrue(all(item["unexpected"] == 0 for item in report["scenarios"]))
        self.assertTrue(all(item["passed"] for item in report["invariants"]))


if __name__ == "__main__":
    unittest.main()
