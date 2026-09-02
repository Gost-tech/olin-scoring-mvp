"""Validate or commit an approved bank shadow batch inside the controlled environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from olin.bank_batch import import_bank_batch, load_bank_batch
from olin.config import default_database_target


def main() -> int:
    parser = argparse.ArgumentParser(description="Olin controlled bank-batch intake")
    parser.add_argument("bundle", help="Approved UTF-8 JSON bundle")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--db", default=None, help="Managed PostgreSQL DSN override")
    parser.add_argument("--actor", default="", help="Named partner ingestion account")
    parser.add_argument("--commit", action="store_true", help="Persist after validation")
    args = parser.parse_args()
    batch, digest = load_bank_batch(args.bundle, args.expected_sha256)
    if not args.commit:
        result = {
            "status": "validated_not_imported",
            "batch_id": batch["batch_id"],
            "cohort_id": batch["cohort_id"],
            "case_count": batch["case_count"],
            "sha256": digest,
        }
    else:
        if not args.actor.strip():
            parser.error("--actor is required with --commit")
        target = args.db or default_database_target(Path.cwd())
        result = import_bank_batch(batch, target, args.actor)
        result["sha256"] = digest
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
