"""Print a non-secret real-data startup verdict for CI and operators."""
from __future__ import annotations

import argparse
import json
import sys

from olin.config import default_database_target
from olin.production_preflight import production_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Olin real-data configuration")
    parser.add_argument("--db", default=None, help="PostgreSQL DSN override")
    args = parser.parse_args()
    target = args.db or default_database_target(__import__("pathlib").Path.cwd())
    result = production_preflight(target)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
