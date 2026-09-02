"""Outcome-data sufficiency checks; never substitutes synthetic cases for validation."""
from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import Any

from .models import BusinessType
from .store import connect_database


def validation_readiness(
    db_path: str,
    *,
    minimum_cases: int = 200,
    minimum_adverse_outcomes: int = 30,
    minimum_label_coverage: float = 0.80,
) -> dict[str, Any]:
    rows = []
    with closing(connect_database(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        for business_type in BusinessType:
            case_count = conn.execute(
                "SELECT COUNT(*) FROM scoring_log WHERE business_type=? AND is_demo=0",
                (business_type.value,),
            ).fetchone()[0]
            labeled = conn.execute(
                "SELECT COUNT(DISTINCT p.application_id) FROM shadow_performance_event p "
                "JOIN scoring_log s ON s.application_id=p.application_id "
                "WHERE s.business_type=? AND s.is_demo=0",
                (business_type.value,),
            ).fetchone()[0]
            adverse = conn.execute(
                "SELECT COUNT(DISTINCT p.application_id) FROM shadow_performance_event p "
                "JOIN scoring_log s ON s.application_id=p.application_id "
                "WHERE s.business_type=? AND s.is_demo=0 "
                "AND p.status IN ('dpd_90_plus','defaulted','charged_off')",
                (business_type.value,),
            ).fetchone()[0]
            coverage = labeled / case_count if case_count else 0.0
            ready = (
                case_count >= minimum_cases
                and adverse >= minimum_adverse_outcomes
                and coverage >= minimum_label_coverage
            )
            rows.append({
                "business_type": business_type.value,
                "case_count": case_count,
                "labeled_case_count": labeled,
                "adverse_outcome_count": adverse,
                "label_coverage": round(coverage, 4),
                "ready_for_statistical_validation": ready,
                "blocks": [
                    reason for reason, blocked in {
                        f"fewer_than_{minimum_cases}_cases": case_count < minimum_cases,
                        f"fewer_than_{minimum_adverse_outcomes}_adverse_outcomes": adverse < minimum_adverse_outcomes,
                        f"label_coverage_below_{minimum_label_coverage:.0%}": coverage < minimum_label_coverage,
                    }.items() if blocked
                ],
            })
    return {
        "plan_version": "historical-validation-readiness-1.0",
        "thresholds": {
            "minimum_cases": minimum_cases,
            "minimum_adverse_outcomes": minimum_adverse_outcomes,
            "minimum_label_coverage": minimum_label_coverage,
        },
        "all_types_ready": all(row["ready_for_statistical_validation"] for row in rows),
        "business_types": rows,
        "warning": "Readiness counts do not calculate model performance or replace a bank-approved statistical analysis.",
    }
