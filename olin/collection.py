"""
Olin - Repayment collection

Phase 0 collection model: 2 equal SPEI payments, Day 30 and Day 60.
Merchants pay by sending a SPEI transfer to Olin's CLABE with a unique
reference code so we can match the incoming payment to the loan.

Reference format: OLIN-{APP_ID_SHORT}-{P1|P2}
Example:          OLIN-A3F92B1C-P1  (payment 1 for app a3f92b1c)

Payment detection:
  - STP sends an incoming payment webhook to POST /api/webhook/stp
  - The webhook body includes the claveRastreo (reference) and amount
  - We match on collection_reference and update the DB

Late payment detection:
  - Run check_overdue() daily (or via cron) to flag loans past Day 30/60
  - Returns overdue loans for WhatsApp reminder (360dialog integration in Session 4)

Outcome auto-labelling:
  - When payment_2_received = 1, store.record_payment() auto-sets repaid_on_time=1
  - When a loan hits Day 75 without payment 2, mark defaulted=1

Usage:
    from olin.collection import (
        make_collection_ref, payment_schedule,
        process_incoming_payment, check_overdue,
        attempt_partial_domiciliacion,
    )
"""
from __future__ import annotations

import re
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional


def make_collection_ref(application_id: str) -> str:
    """Unique SPEI reference the merchant must include in their transfer."""
    return f"OLIN-{application_id[:8].upper()}"


def payment_schedule(
    application_id: str,
    approved_amount_mxn: float,
    pricing_fixed_cost_mxn: float,
    disbursed_at: Optional[str] = None,
) -> dict:
    """
    Compute the two payment dates and amounts.

    Payment 1: half principal + half fixed cost, due Day 30
    Payment 2: half principal + half fixed cost, due Day 60
    """
    if disbursed_at:
        try:
            t0 = datetime.fromisoformat(disbursed_at.replace("Z", "+00:00"))
        except ValueError:
            t0 = datetime.now(timezone.utc)
    else:
        t0 = datetime.now(timezone.utc)

    half_principal = round(approved_amount_mxn / 2, 2)
    half_cost      = round(pricing_fixed_cost_mxn / 2, 2)
    payment_amount = half_principal + half_cost

    due_1 = (t0 + timedelta(days=30)).date().isoformat()
    due_2 = (t0 + timedelta(days=60)).date().isoformat()

    ref = make_collection_ref(application_id)
    return {
        "collection_reference": ref,
        "payment_1": {
            "reference":   f"{ref}-P1",
            "amount_mxn":  payment_amount,
            "due_date":    due_1,
        },
        "payment_2": {
            "reference":   f"{ref}-P2",
            "amount_mxn":  payment_amount,
            "due_date":    due_2,
        },
        "total_repayable_mxn": approved_amount_mxn + pricing_fixed_cost_mxn,
    }


def process_incoming_payment(
    webhook_body: dict,
    db_path: str,
) -> dict:
    """
    Handle an incoming STP SPEI webhook notification.

    STP webhook POST body (relevant fields):
      claveRastreo  — the reference the merchant used
      monto         — amount received
      nombreOrdenante, rfcCurpOrdenante — merchant identity

    Matches on collection_reference (prefix match on claveRastreo).
    Returns {"matched": bool, "application_id": ..., "payment": 1|2|None}
    """
    clave = str(webhook_body.get("claveRastreo", "")).upper().strip()
    try:
        monto = float(webhook_body.get("monto", 0))
    except (TypeError, ValueError):
        return {"matched": False, "reason": "Invalid payment amount"}

    if not clave or not math.isfinite(monto) or monto <= 0:
        return {"matched": False, "reason": "Missing claveRastreo or zero amount"}

    # Match OLIN-{APP_ID}-P1 or OLIN-{APP_ID}-P2 or bare OLIN-{APP_ID}
    m = re.fullmatch(r'(OLIN-[A-F0-9]{8})(?:-(P[12]))?', clave)
    if not m:
        return {"matched": False, "reason": f"Reference '{clave}' not an Olin reference"}

    base_ref   = m.group(1)   # e.g. OLIN-A3F92B1C
    payment_id = m.group(2)   # P1, P2, or None

    try:
        from .store import ScoringLog
        with ScoringLog(db_path) as log:
            row = log.conn.execute(
                "SELECT application_id, payment_1_received, payment_2_received, "
                "approved_mxn, pricing_fixed_cost_mxn, disbursed "
                "FROM scoring_log WHERE collection_reference=?",
                (base_ref,),
            ).fetchone()

            if not row:
                return {"matched": False, "reason": f"No loan for reference {base_ref}"}

            app_id, p1_recv, p2_recv, amount, cost, disbursed = row
            if not disbursed:
                return {"matched": False, "reason": "Loan has not been disbursed"}
            expected_payment = round((amount + cost) / 2, 2)

            # Determine which payment this is
            if payment_id == "P1" or (not payment_id and not p1_recv):
                pn = 1
            elif payment_id == "P2" or (not payment_id and p1_recv and not p2_recv):
                pn = 2
            else:
                return {"matched": True, "application_id": app_id,
                        "payment": None, "note": "Both payments already received"}

            event_source = str(
                webhook_body.get("id") or webhook_body.get("folio")
                or webhook_body.get("idOrden") or ""
            ).strip()
            if event_source:
                event_id = f"stp:{event_source[:120]}"
            else:
                canonical = json.dumps(webhook_body, sort_keys=True, separators=(",", ":"))
                event_id = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

            try:
                recorded = log.record_payment_event(
                    base_ref, pn, monto, event_id, webhook_body,
                )
            except (ValueError, LookupError) as exc:
                return {"matched": False, "reason": str(exc)}
            return {
                "matched": True,
                **recorded,
                "amount_received": monto,
                "expected": expected_payment,
                "delta": round(monto - expected_payment, 2),
            }
    except Exception as e:
        return {"matched": False, "reason": f"DB error: {e}"}


def check_overdue(db_path: str, grace_days: int = 3) -> list[dict]:
    """
    Return loans that are past their payment due date.

    Used by the daily job (and eventually 360dialog reminder bot) to identify
    who to contact. grace_days gives a buffer before flagging.

    Returns list of dicts with overdue details.
    """
    today = datetime.now(timezone.utc).date()
    overdue = []

    try:
        from .store import ScoringLog
        with ScoringLog(db_path) as log:
            rows = log.conn.execute(
                """SELECT application_id, merchant_name, clabe, collection_reference,
                          approved_mxn, pricing_fixed_cost_mxn,
                          payment_1_received, payment_2_received, disbursed_at
                   FROM scoring_log
                   WHERE disbursed=1 AND disbursed_at IS NOT NULL
                   AND (repaid_on_time IS NULL OR repaid_on_time=0)
                   AND (defaulted IS NULL OR defaulted=0)"""
            ).fetchall()
    except Exception as exc:
        raise RuntimeError(f"Overdue query failed: {exc}") from exc

    for row in rows:
        (app_id, merchant, clabe, ref, amount, cost,
         p1_recv, p2_recv, disbursed_at) = row

        try:
            t0 = datetime.fromisoformat(disbursed_at.replace("Z", "")).date()
        except (ValueError, AttributeError):
            continue

        due_1 = t0 + timedelta(days=30)
        due_2 = t0 + timedelta(days=60)
        payment = round(((amount or 0) + (cost or 0)) / 2, 2)

        if not p1_recv and today > due_1 + timedelta(days=grace_days):
            days_late = (today - due_1).days
            overdue.append({
                "application_id": app_id,
                "merchant_name":  merchant,
                "clabe":          clabe,
                "collection_ref": ref,
                "payment_number": 1,
                "due_date":       due_1.isoformat(),
                "days_late":      days_late,
                "amount_due_mxn": payment,
                "critical":       days_late >= 15,  # flag for escalation
            })

        if p1_recv and not p2_recv and today > due_2 + timedelta(days=grace_days):
            days_late = (today - due_2).days
            overdue.append({
                "application_id": app_id,
                "merchant_name":  merchant,
                "clabe":          clabe,
                "collection_ref": ref,
                "payment_number": 2,
                "due_date":       due_2.isoformat(),
                "days_late":      days_late,
                "amount_due_mxn": payment,
                "critical":       days_late >= 15,
            })

    return sorted(overdue, key=lambda x: (-x["days_late"], x["merchant_name"]))


def attempt_partial_domiciliacion(
    application_id: str,
    payment_number: int,
    available_amount_mxn: float,
    db_path: str,
    event_id: Optional[str] = None,
) -> dict:
    """
    Attempt a domiciliación (direct debit) for a scheduled installment.

    If available_amount_mxn < the outstanding balance, the available amount is
    charged and the remainder is carried forward — no payment is skipped entirely.
    Subsequent calls will collect the remainder until the installment is complete.

    This is a collection-mechanism function. It does not touch the score or tier.

    Args:
        application_id: the loan application ID
        payment_number: 1 or 2
        available_amount_mxn: balance available in the merchant's account right now
        db_path: path to the SQLite database
        event_id: idempotency key; auto-generated from timestamp if omitted

    Returns dict with:
        action:                  "full" | "partial" | "skip" | "already_complete"
        charged_mxn:             amount debited this attempt (0 for skip/already_complete)
        remaining_mxn:           still outstanding on this installment after this charge
        complete:                True when installment is fully settled
        installment_paid_total_mxn: cumulative amount received for this installment
        expected_mxn:            full installment amount
    """
    if payment_number not in (1, 2):
        raise ValueError("payment_number must be 1 or 2")
    if available_amount_mxn < 0:
        raise ValueError("available_amount_mxn cannot be negative")

    from .store import ScoringLog
    with ScoringLog(db_path) as log:
        row = log.conn.execute(
            "SELECT approved_mxn, pricing_fixed_cost_mxn, disbursed, "
            "payment_1_received, payment_2_received, collection_reference "
            "FROM scoring_log WHERE application_id=?",
            (application_id,),
        ).fetchone()

        if not row:
            raise LookupError(f"No loan for application {application_id}")
        approved_mxn, cost_mxn, disbursed, p1_done, p2_done, col_ref = row

        if not disbursed:
            raise ValueError("Loan has not been disbursed")
        if not col_ref:
            raise ValueError("Loan has no collection reference; log_disbursement may not have run")

        installment_done = p1_done if payment_number == 1 else p2_done
        if installment_done:
            return {
                "action": "already_complete",
                "charged_mxn": 0.0,
                "remaining_mxn": 0.0,
                "complete": True,
                "installment_paid_total_mxn": round(((approved_mxn or 0) + (cost_mxn or 0)) / 2, 2),
                "expected_mxn": round(((approved_mxn or 0) + (cost_mxn or 0)) / 2, 2),
            }

        expected = round(((approved_mxn or 0) + (cost_mxn or 0)) / 2, 2)

        already_paid = log.conn.execute(
            "SELECT COALESCE(SUM(amount_mxn), 0) FROM payment_ledger "
            "WHERE application_id=? AND payment_number=?",
            (application_id, payment_number),
        ).fetchone()[0]

        remaining = round(max(0.0, expected - already_paid), 2)

        if remaining == 0.0:
            return {
                "action": "already_complete",
                "charged_mxn": 0.0,
                "remaining_mxn": 0.0,
                "complete": True,
                "installment_paid_total_mxn": round(already_paid, 2),
                "expected_mxn": expected,
            }

        if available_amount_mxn <= 0:
            return {
                "action": "skip",
                "charged_mxn": 0.0,
                "remaining_mxn": remaining,
                "complete": False,
                "installment_paid_total_mxn": round(already_paid, 2),
                "expected_mxn": expected,
            }

        charge = round(min(available_amount_mxn, remaining), 2)
        action = "full" if charge >= remaining - 0.01 else "partial"

        if event_id is None:
            event_id = (
                f"domiciliacion:{application_id}:P{payment_number}:"
                f"{datetime.now(timezone.utc).isoformat()}"
            )

        raw_event = {
            "source": "domiciliacion",
            "application_id": application_id,
            "payment_number": payment_number,
            "available_amount_mxn": available_amount_mxn,
            "charged_mxn": charge,
            "action": action,
        }

        result = log.record_payment_event(
            col_ref, payment_number, charge, event_id, raw_event,
        )

    return {
        "action": action,
        "charged_mxn": charge,
        "remaining_mxn": round(max(0.0, remaining - charge), 2),
        "complete": result.get("complete", False),
        "installment_paid_total_mxn": result.get("installment_paid", round(already_paid + charge, 2)),
        "expected_mxn": expected,
    }


def mark_defaulted(application_id: str, db_path: str) -> None:
    """Mark a loan as defaulted (called by the daily job at Day 75+)."""
    from .store import ScoringLog
    with ScoringLog(db_path) as log:
        log.conn.execute(
            "UPDATE scoring_log SET defaulted=1, repaid_on_time=0, outcome_status='defaulted' "
            "WHERE application_id=? AND disbursed=1 AND outcome_status='active'",
            (application_id,),
        )
        log.conn.commit()
