"""Acceptance test for every SME type exposed to a partner bank."""
import unittest

from olin.models import BusinessType
from scripts.all_business_bank_acceptance import run_all_business_acceptance


class AllBusinessBankAcceptanceTests(unittest.TestCase):
    def test_every_supported_business_has_safe_bank_journey(self):
        report = run_all_business_acceptance()
        failures = [item for item in report["results"] if not item["passed"]]
        self.assertEqual(len(BusinessType), report["business_type_count"])
        self.assertTrue(report["negative_tests"]["passed"])
        self.assertTrue(report["passed"], failures)


if __name__ == "__main__":
    unittest.main()
