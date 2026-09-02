"""Coverage and conservative-routing tests for sector policies."""
import unittest
import os
from unittest.mock import patch

from olin.business_segments import assess_business_policy, unmapped_business_types
from olin.models import BusinessType


class BusinessSegmentPolicyTests(unittest.TestCase):
    def test_every_supported_business_type_has_a_policy(self):
        self.assertEqual(unmapped_business_types(), set())

    def test_no_type_is_automated_without_model_risk_registry(self):
        verified = [
            {"key": "supplier_purchases", "status": "verified"},
            {"key": "bank_cash_flow", "status": "verified"},
            {"key": "pos_settlements", "status": "verified"},
            {"key": "identity_consent", "status": "verified"},
        ]
        with patch.dict(os.environ, {"OLIN_VALIDATED_AUTO_APPROVE_TYPES": ""}):
            for business_type in BusinessType:
                result = assess_business_policy(business_type, verified)
                self.assertEqual(result["routing"], "bank_committee_review")

    def test_model_risk_can_enable_one_validated_type(self):
        verified = [
            {"key": "supplier_purchases", "status": "verified"},
            {"key": "bank_cash_flow", "status": "verified"},
        ]
        with patch.dict(os.environ, {"OLIN_VALIDATED_AUTO_APPROVE_TYPES": "abarrotes"}):
            result = assess_business_policy(BusinessType.ABARROTES, verified)
        self.assertEqual(result["policy_status"], "pilot_auto_eligible")

    def test_missing_primary_evidence_forces_review(self):
        result = assess_business_policy(BusinessType.ABARROTES, [])
        self.assertEqual(result["routing"], "bank_committee_review")
        self.assertIn("supplier_purchases", result["missing_primary_evidence"])


if __name__ == "__main__":
    unittest.main()
