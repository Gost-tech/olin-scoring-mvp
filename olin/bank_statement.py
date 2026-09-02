"""Analyze an authorized bank CSV without retaining transaction rows."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import re

from .syncfy import _compute_bank_data


DATE_NAMES = {"date", "fecha", "transaction_date", "fecha_operacion"}
AMOUNT_NAMES = {"amount", "monto", "importe"}
CREDIT_NAMES = {"credit", "credito", "abono", "deposito", "deposit"}
DEBIT_NAMES = {"debit", "debito", "cargo", "withdrawal"}
BALANCE_NAMES = {"balance", "saldo"}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _money(value: str | None) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not cleaned or cleaned in {"-", ".", "-."}:
        return 0.0
    return float(cleaned)


def _date(value: str) -> datetime:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Unsupported transaction date: {text[:32]}") from exc


def _column(fieldnames: list[str], aliases: set[str]) -> str | None:
    return next((name for name in fieldnames if _key(name) in aliases), None)


def analyze_csv(csv_text: str) -> dict:
    raw = csv_text.encode("utf-8")
    if not csv_text.strip():
        raise ValueError("csvText is required")
    if len(raw) > 500_000:
        raise ValueError("CSV exceeds the 500 KB pilot limit")
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    fields = reader.fieldnames or []
    date_col = _column(fields, DATE_NAMES)
    amount_col = _column(fields, AMOUNT_NAMES)
    credit_col = _column(fields, CREDIT_NAMES)
    debit_col = _column(fields, DEBIT_NAMES)
    balance_col = _column(fields, BALANCE_NAMES)
    if not date_col or not (amount_col or credit_col or debit_col):
        raise ValueError(
            "CSV requires a date/fecha column and amount/monto or credit/debit columns"
        )

    transactions: list[dict] = []
    dates: list[datetime] = []
    last_balance: float | None = None
    for line_number, row in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        try:
            when = _date(str(row.get(date_col, "")))
            amount = _money(row.get(amount_col)) if amount_col else 0.0
            if amount_col is None:
                amount = _money(row.get(credit_col)) - _money(row.get(debit_col))
            if balance_col and str(row.get(balance_col, "")).strip():
                last_balance = _money(row.get(balance_col))
        except ValueError as exc:
            raise ValueError(f"CSV line {line_number}: {exc}") from exc
        if amount == 0:
            continue
        transactions.append({"dt_transaction": int(when.timestamp()), "amount": amount})
        dates.append(when)
    if len(transactions) < 5:
        raise ValueError("At least 5 valid non-zero transactions are required")
    span_days = max(30, min(365, (max(dates) - min(dates)).days + 1))
    bank = _compute_bank_data(transactions, span_days, account_balance=last_balance)
    evidence_reference = "sha256:" + hashlib.sha256(raw).hexdigest()
    bank.source = "bank_statement_csv"
    # A partner-supplied file is useful for pre-analysis, but a content hash
    # does not prove that the file came from the bank. Only a provider feed or
    # a controlled documentary-review workflow may promote it to verified.
    bank.verified = False
    bank.evidence_reference = evidence_reference
    bank.observed_at = datetime.now(timezone.utc).isoformat()
    return {
        "provider": "bank_statement_csv",
        "bank": bank.__dict__,
        "summary": {
            "transactionCount": len(transactions),
            "firstDate": min(dates).date().isoformat(),
            "lastDate": max(dates).date().isoformat(),
            "statementStored": False,
            "eligibleForDecision": False,
        },
        "limitations": [
            "The CSV was supplied by the partner and is not independently authenticated",
            "Only derived metrics and a SHA-256 reference are returned",
        ],
    }
