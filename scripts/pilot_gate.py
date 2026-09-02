#!/usr/bin/env python3
"""Validate an Olin bank-pilot manifest and print its fail-closed verdict."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from olin.pilot_gate import evaluate_pilot_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to the pilot JSON manifest")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"NO_GO: cannot read manifest: {exc}", file=sys.stderr)
        return 2

    result = evaluate_pilot_manifest(manifest)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Verdict: {result['verdict']}")
        if result["blockers"]:
            print("Blockers:")
            for blocker in result["blockers"]:
                print(f"- {blocker}")
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
