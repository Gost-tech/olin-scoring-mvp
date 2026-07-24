#!/usr/bin/env python3
"""
Olin · Daily operations job

Run daily via cron or manually:
    python3 -m jobs.daily
    python3 -m jobs.daily --db /path/to/olin_scoring.db
    python3 -m jobs.daily --dry-run

Three operations (always in this order):
  1. Auto-default loans at Day 75+ with no second payment
  2. Print overdue payment table (grace period = 3 days)
  3. Print portfolio snapshot

Cron example (daily at 08:00 MX):
  0 8 * * * cd /path/to/olin_scoring_mvp_1 && python3 -m jobs.daily >> logs/daily.log 2>&1
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from olin.collection import check_overdue, mark_defaulted
from olin.alerts import send_alert
from olin.config import default_db_path
from olin.store import ScoringLog

DB_DEFAULT = default_db_path(ROOT)

GR = "\033[92m"
AM = "\033[93m"
RD = "\033[91m"
MU = "\033[90m"
B  = "\033[1m"
R  = "\033[0m"


def run(db_path: str, dry_run: bool = False) -> int:
    """
    Execute all daily checks. Returns number of critical issues found
    (overdue loans flagged as critical + defaults auto-marked).
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    tag = f" {AM}[DRY RUN]{R}" if dry_run else ""
    print(f"\n  {B}Olin Daily Job{R}  {MU}{now_str}{R}{tag}")
    print(f"  {MU}DB: {db_path}{R}\n")

    issues = 0

    # ── 1. Auto-default Day 75+ loans ──────────────────────────────────
    print(f"  {B}[1/3] Day 75+ defaults{R}")
    today = datetime.now(timezone.utc).date()

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT application_id, merchant_name, disbursed_at, clabe
                   FROM scoring_log
                   WHERE disbursed=1
                   AND (payment_2_received IS NULL OR payment_2_received=0)
                   AND (defaulted IS NULL OR defaulted=0)
                   AND disbursed_at IS NOT NULL"""
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        send_alert("Olin daily job: database error", f"Database: {db_path}\nError: {e}")
        return 1

    newly_defaulted = []
    for row in rows:
        try:
            t0 = datetime.fromisoformat(row["disbursed_at"].replace("Z","")).date()
        except (ValueError, AttributeError):
            continue
        days_out = (today - t0).days
        if days_out >= 75:
            newly_defaulted.append({
                "application_id": row["application_id"],
                "merchant_name":  row["merchant_name"],
                "days_out":       days_out,
            })
            issues += 1
            if not dry_run:
                mark_defaulted(row["application_id"], db_path)

    if newly_defaulted:
        body = "\n".join(
            f"{d['application_id']} | {d['merchant_name']} | day {d['days_out']}"
            for d in newly_defaulted
        )
        send_alert(
            f"Olin: {len(newly_defaulted)} loan(s) reached default threshold",
            f"Database: {db_path}\nDry run: {dry_run}\n\n{body}",
        )
        print(f"  {AM}{len(newly_defaulted)} default alert(s) recorded{R}")
    else:
        print(f"  {GR}✓{R}  {MU}No new defaults today{R}")

    # ── 2. Overdue payments ────────────────────────────────────────────
    print(f"\n  {B}[2/3] Overdue payments{R}  {MU}(3-day grace period){R}")
    try:
        overdue = check_overdue(db_path, grace_days=3)
    except RuntimeError as exc:
        send_alert(
            "Olin daily job: collection query failed",
            f"Database: {db_path}\nError: {exc}",
        )
        return issues + 1

    if not overdue:
        print(f"  {GR}✓{R}  {MU}No overdue loans{R}")
    else:
        for o in overdue:
            if o["critical"]:
                issues += 1
        overdue_body = "\n".join(
            f"{o['application_id']} | {o['merchant_name']} | payment {o['payment_number']} | "
            f"due {o['due_date']} | {o['days_late']} days late | "
            f"MXN {o['amount_due_mxn']:,.2f} | critical={o['critical']}"
            for o in overdue
        )
        send_alert(
            f"Olin: {len(overdue)} overdue payment(s)",
            f"Database: {db_path}\n\n{overdue_body}",
        )
        print(f"  {AM}{len(overdue)} overdue payment alert(s) recorded{R}")

    # ── 3. Portfolio snapshot ──────────────────────────────────────────
    print(f"\n  {B}[3/3] Portfolio snapshot{R}")
    try:
        with ScoringLog(db_path) as _sl:
            snap = _sl.portfolio_snapshot()
    except Exception as e:
        send_alert("Olin daily job: portfolio snapshot failed", f"Database: {db_path}\nError: {e}")
        return issues

    dr    = snap.get("default_rate", 0.0)
    dr_c  = GR if dr < 0.10 else (AM if dr < 0.15 else RD)
    dr_ic = "✓" if dr < 0.10 else ("⚠" if dr < 0.15 else "🔴")

    print(f"  {'Applications':<20}: {snap.get('total_applications', 0)}")
    print(f"  {'Disbursed':<20}: {snap.get('total_disbursed', 0)}")
    print(f"  {'Active loans':<20}: {snap.get('active_loans', 0)}"
          f"  (MXN {snap.get('active_mxn', 0):,.0f})")
    print(f"  {'Repaid':<20}: {snap.get('repaid', 0)}")
    print(f"  {'Defaulted':<20}: {snap.get('defaulted', 0)}")
    print(f"  {'Default rate':<20}: {dr_c}{dr*100:.1f}%{R}  {dr_ic}")
    if dr >= 0.15:
        send_alert(
            "Olin: portfolio default-rate stop threshold reached",
            f"Database: {db_path}\nDefault rate: {dr*100:.1f}%\n"
            f"Defaulted: {snap.get('defaulted', 0)}\n"
            f"Resolved loans: {snap.get('resolved_loans', 0)}",
        )

    by_type = snap.get("by_type", [])
    if by_type:
        print(f"\n  {MU}By business type:{R}")
        for t in by_type:
            print(f"    {t['type']:<16}  {t['count']} active")

    by_colonia = snap.get("by_colonia", [])[:5]
    if by_colonia:
        print(f"\n  {MU}Top colonias (active):{R}")
        for c in by_colonia:
            print(f"    {(c['colonia'] or 'Unknown')[:20]:<20}  {c['count']} loans  MXN {c['mxn']:,.0f}")

    print()
    return issues


def main():
    parser = argparse.ArgumentParser(description="Olin Daily Operations Job")
    parser.add_argument("--db",      default=str(DB_DEFAULT), help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true",     help="Print what would happen without writing")
    args = parser.parse_args()
    issues = run(args.db, dry_run=args.dry_run)
    sys.exit(1 if issues > 0 else 0)


if __name__ == "__main__":
    main()
