import tempfile
import unittest

from olin.historical_validation import validation_readiness
from olin.models import BusinessType
from olin.store import ScoringLog


class HistoricalValidationReadinessTests(unittest.TestCase):
    def test_empty_or_synthetic_database_cannot_claim_validation(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with ScoringLog(tmp.name):
                pass
            result = validation_readiness(tmp.name)
        self.assertFalse(result["all_types_ready"])
        self.assertEqual(len(BusinessType), len(result["business_types"]))
        self.assertTrue(all(not row["ready_for_statistical_validation"] for row in result["business_types"]))


if __name__ == "__main__":
    unittest.main()
