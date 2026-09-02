from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import unittest
from unittest.mock import patch

from olin.bank_batch import SCHEMA_VERSION, validate_bank_batch
from test_product_mvp import partner_payload


def batch_payload() -> dict:
    case = partner_payload()
    case.pop("consent")
    authorization = {
        "basis_label": "bank_documented_instruction",
        "approval_reference": "BANK-PRIVACY-204",
        "approved_by": "bank_privacy_owner",
        "approved_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "scope_sha256": sha256(b"approved-scope").hexdigest(),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": "bank-batch-001",
        "cohort_id": "shadow-uat-001",
        "institution_reference": "BANK-DATA-TRANSFER-88",
        "data_classification": "identifiable_historical",
        "data_authorization": authorization,
        "cases": [case],
    }


class BankBatchTests(unittest.TestCase):
    def test_historical_batch_is_normalized_without_echoing_fake_consent(self):
        with patch.dict(os.environ, {
            "OLIN_MODE": "production",
            "OLIN_DATA_CLASSIFICATION": "identifiable_historical",
        }):
            result = validate_bank_batch(batch_payload())
        self.assertEqual(1, result["case_count"])
        self.assertNotIn("consent", result["cases"][0])
        self.assertEqual("shadow", result["cases"][0]["case_mode"])

    def test_raw_transactions_or_credentials_are_quarantined(self):
        for forbidden in (
            {"transactions": []},
            {"credentials": {"password": "never"}},
        ):
            payload = batch_payload()
            payload["cases"][0]["bank"].update(forbidden)
            with patch.dict(os.environ, {
                "OLIN_MODE": "production",
                "OLIN_DATA_CLASSIFICATION": "identifiable_historical",
            }):
                with self.assertRaisesRegex(ValueError, "Forbidden"):
                    validate_bank_batch(payload)

    def test_duplicate_references_and_more_than_ten_cases_are_rejected(self):
        duplicate = batch_payload()
        duplicate["cases"].append(deepcopy(duplicate["cases"][0]))
        too_many = batch_payload()
        too_many["cases"] = [deepcopy(too_many["cases"][0]) for _ in range(11)]
        env = {"OLIN_MODE": "production", "OLIN_DATA_CLASSIFICATION": "identifiable_historical"}
        with patch.dict(os.environ, env):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validate_bank_batch(duplicate)
            with self.assertRaisesRegex(ValueError, "between 1 and 10"):
                validate_bank_batch(too_many)

    def test_prospective_applicants_cannot_enter_through_batch_import(self):
        payload = batch_payload()
        payload["data_classification"] = "prospective"
        with patch.dict(os.environ, {
            "OLIN_MODE": "production", "OLIN_DATA_CLASSIFICATION": "prospective"
        }):
            with self.assertRaisesRegex(ValueError, "hosted intake"):
                validate_bank_batch(payload)


if __name__ == "__main__":
    unittest.main()
