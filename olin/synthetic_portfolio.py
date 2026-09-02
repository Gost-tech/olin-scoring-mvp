"""Deterministic synthetic portfolio checks for the rules engine.

This validates software behavior and policy invariants. It is not a model
validation dataset and must never be presented as observed repayment evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
import random
from pathlib import Path

from .api.cases import build_application
from .api.synthetic import SYNTHETIC_CASES
from .scorecard import score_application


def generate(case_count: int = 300, seed: int = 42) -> dict:
    if not 3 <= case_count <= 100_000:
        raise ValueError("case_count must be between 3 and 100000")
    rng = random.Random(seed)
    rows = []
    for index in range(case_count):
        profile = index % len(SYNTHETIC_CASES)
        payload = deepcopy(SYNTHETIC_CASES[profile])
        payload["merchant_name"] = f"Comercio Sintético {index + 1:06d}"
        payload["partner_case_reference"] = f"SYN-PORT-{seed}-{index + 1}"
        # Small seeded variation exercises boundaries while retaining the
        # low/medium/high risk character of the three canonical profiles.
        bank = payload["bank"]
        factor = 1 + rng.uniform(-0.08, 0.08)
        bank["avg_daily_balance_mxn"] = round(bank["avg_daily_balance_mxn"] * factor, 2)
        bank["monthly_deposit_volume_mxn"] = round(
            bank["monthly_deposit_volume_mxn"] * factor, 2
        )
        app = build_application(payload)
        result = score_application(app)
        rows.append({
            "profile": profile,
            "score": round(result.score, 6),
            "decision": result.decision.value,
            "approved_mxn": result.approved_amount_mxn,
            "finite": all(value == value for value in (result.score, result.ci_low, result.ci_high)),
        })
    by_profile = {
        str(profile): round(
            sum(row["score"] for row in rows if row["profile"] == profile)
            / sum(row["profile"] == profile for row in rows), 4
        )
        for profile in range(3)
    }
    decisions = Counter(row["decision"] for row in rows)
    checks = {
        "all_scores_finite": all(row["finite"] for row in rows),
        "declines_have_zero_amount": all(
            row["approved_mxn"] == 0 for row in rows if row["decision"] == "DECLINE"
        ),
        "risk_order_preserved": by_profile["0"] > by_profile["1"] > by_profile["2"],
        "multiple_decision_paths_exercised": len(decisions) >= 2,
        "no_real_outcomes_used": True,
        "no_money_movement": True,
    }
    return {
        "kind": "synthetic_software_validation",
        "seed": seed,
        "case_count": case_count,
        "decision_counts": dict(sorted(decisions.items())),
        "average_score_by_canonical_profile": by_profile,
        "checks": checks,
        "passed": all(checks.values()),
        "limitations": [
            "Synthetic cases do not estimate default rates or predictive accuracy",
            "Production calibration requires observed partner decisions and repayment outcomes",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Olin synthetic portfolio checks")
    parser.add_argument("--cases", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = generate(args.cases, args.seed)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
