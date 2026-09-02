"""Black-box acceptance contract from a bank integration team's perspective."""
from __future__ import annotations

import unittest

from scripts.bank_acceptance_test import run_acceptance


class BankAcceptanceTests(unittest.TestCase):
    def test_complete_production_shadow_journey(self):
        report = run_acceptance()
        failures = [step for step in report["steps"] if not step["passed"]]
        self.assertTrue(report["passed"], failures)
        self.assertEqual("production-shadow", report["mode"])
        self.assertFalse(report["security"]["secrets_in_report"])
        self.assertFalse(report["security"]["raw_transactions_stored"])
        self.assertFalse(report["security"]["money_movement"])


if __name__ == "__main__":
    unittest.main()
