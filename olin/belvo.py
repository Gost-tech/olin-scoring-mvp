"""
Belvo sandbox connector -> BankData

Fetches up to 90 days of transactions for a linked account and computes
the BankData metrics the scoring engine expects for the bank_cash_flow
signal (25% weight).

Auth: HTTP Basic with BELVO_SECRET_ID / BELVO_SECRET_KEY from environment.

Typical usage
-------------
# Already have a link_id (most common in production):
    from olin.belvo import fetch_bank_data
    bank = fetch_bank_data("3b5ece36-...")

# Create a link on the fly (sandbox / onboarding flow):
    from olin.belvo import create_link_and_fetch
    bank, link_id = create_link_and_fetch(
        institution="erebea_mx_retail",
        username="bnk_MX0000000111",
        password="full",
    )

# Verify credentials work without a link:
    from olin.belvo import ping
    ping()   # raises if credentials are wrong
"""
from __future__ import annotations

import os
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise ImportError("pip install requests  (see requirements.txt)") from exc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional; set env vars manually if not installed

from .models import BankData

BELVO_BASE = os.getenv("BELVO_BASE_URL", "https://sandbox.belvo.com")


def _auth() -> tuple[str, str]:
    sid = os.environ.get("BELVO_SECRET_ID", "").strip()
    key = os.environ.get("BELVO_SECRET_KEY", "").strip()
    if not sid or not key:
        raise EnvironmentError(
            "BELVO_SECRET_ID and BELVO_SECRET_KEY must be set. "
            "Copy .env.example to .env and fill them in."
        )
    return sid, key


def ping() -> dict:
    """GET /api/institutions/ – cheapest call to verify credentials."""
    resp = requests.get(
        f"{BELVO_BASE}/api/institutions/",
        auth=_auth(),
        params={"page_size": 1},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------

def create_link(
    institution: str,
    username: str,
    password: str,
    username_type: Optional[str] = None,
    password2: Optional[str] = None,
) -> str:
    """Register a bank link and return the link_id (UUID).

    Some institutions require username_type (e.g. ironbank_br_business).
    Check GET /api/institutions/{name}/ -> form_fields to see which fields
    are mandatory and their allowed values.

    Sandbox MX retail (when available): institution="erebea_mx_retail",
    username="bnk_MX0000000111", password="full"
    """
    payload: dict = {
        "institution": institution,
        "username": username,
        "password": password,
        "save_data": True,
    }
    if username_type is not None:
        payload["username_type"] = username_type
    if password2 is not None:
        payload["password2"] = password2

    resp = requests.post(
        f"{BELVO_BASE}/api/links/",
        auth=_auth(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def list_links() -> list[dict]:
    """Return all links registered under these credentials."""
    results, url = [], f"{BELVO_BASE}/api/links/"
    while url:
        resp = requests.get(url, auth=_auth(), timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            return body
        results.extend(body.get("results", []))
        url = body.get("next")
    return results


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------

def _retrieve_transactions(link_id: str, date_from: str, date_to: str) -> list[dict]:
    """POST /api/transactions/ then follow pagination."""
    resp = requests.post(
        f"{BELVO_BASE}/api/transactions/",
        auth=_auth(),
        json={
            "link": link_id,
            "date_from": date_from,
            "date_to": date_to,
            "save_data": True,
        },
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()

    # Flat list (retrieve endpoint) vs paginated dict (GET endpoint)
    if isinstance(body, list):
        return body

    results = list(body.get("results", []))
    url = body.get("next")
    while url:
        r = requests.get(url, auth=_auth(), timeout=30)
        r.raise_for_status()
        page = r.json()
        results.extend(page.get("results", []))
        url = page.get("next")
    return results


def _retrieve_accounts(link_id: str) -> list[dict]:
    resp = requests.get(
        f"{BELVO_BASE}/api/accounts/",
        auth=_auth(),
        params={"link": link_id},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else body.get("results", [])


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_bank_data(txns: list[dict], days: int) -> BankData:
    if not txns:
        return BankData(months_connected=0.0)

    num_months = days / 30.0

    # --- deposits (INFLOW) ------------------------------------------------
    inflows = [
        t for t in txns
        if t.get("type") == "INFLOW" and t.get("status") == "PROCESSED"
    ]
    monthly_deposit_count = len(inflows) / num_months if num_months > 0 else 0.0

    # --- deposit regularity via weekly CV ---------------------------------
    weekly_counts: dict[int, int] = defaultdict(int)
    today = date.today()
    for t in inflows:
        raw = t.get("value_date") or t.get("accounting_date", "")
        if not raw:
            continue
        d = date.fromisoformat(raw[:10])
        week_idx = (today - d).days // 7
        weekly_counts[week_idx] += 1

    weeks_total = max(days // 7, 1)
    counts = [weekly_counts.get(w, 0) for w in range(weeks_total)]
    mean_c = statistics.mean(counts)
    if len(counts) >= 2 and mean_c > 0:
        cv = statistics.stdev(counts) / mean_c
        deposit_regularity = max(0.0, min(1.0, 1.0 - cv))
    else:
        deposit_regularity = 0.5

    # --- running balance --------------------------------------------------
    balance_pairs: list[tuple[str, float]] = []
    for t in txns:
        bal = t.get("balance")
        raw = t.get("value_date") or t.get("accounting_date", "")
        if bal is not None and raw:
            try:
                balance_pairs.append((raw[:10], float(bal)))
            except (TypeError, ValueError):
                pass
    balance_pairs.sort(key=lambda x: x[0])

    avg_daily_balance = 0.0
    balance_trend = 0.0
    overdrafts = 0

    if balance_pairs:
        balances = [b for _, b in balance_pairs]
        avg_daily_balance = statistics.mean(balances)
        overdrafts = sum(1 for b in balances if b < 0)

        # trend: compare first-half vs second-half average, normalised to [-1, 1]
        n = len(balances)
        mid = n // 2
        if mid > 0:
            first_avg = statistics.mean(balances[:mid])
            second_avg = statistics.mean(balances[mid:])
            if first_avg != 0:
                raw_trend = (second_avg - first_avg) / abs(first_avg)
                balance_trend = max(-1.0, min(1.0, raw_trend))

    return BankData(
        months_connected=round(num_months, 1),
        avg_daily_balance_mxn=round(avg_daily_balance, 2),
        monthly_deposit_count=round(monthly_deposit_count, 1),
        deposit_regularity=round(deposit_regularity, 3),
        overdrafts_90d=overdrafts,
        balance_trend_90d=round(balance_trend, 3),
        source="belvo",
        verified=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_bank_data(link_id: str, days: int = 90) -> BankData:
    """Fetch transactions for an existing link and return BankData.

    Args:
        link_id: UUID returned by Belvo when the link was registered.
        days: lookback window in days (max 90 for most MX banks).
    """
    today = date.today()
    date_from = (today - timedelta(days=days)).isoformat()
    date_to = today.isoformat()
    txns = _retrieve_transactions(link_id, date_from, date_to)
    return _compute_bank_data(txns, days)


def create_link_and_fetch(
    institution: str,
    username: str,
    password: str,
    days: int = 90,
    username_type: Optional[str] = None,
) -> Tuple[BankData, str]:
    """Register a new link and immediately return (BankData, link_id).

    Sandbox quick-start:
        bank, link_id = create_link_and_fetch(
            "erebea_mx_retail", "bnk_MX0000000111", "full"
        )
    """
    link_id = create_link(institution, username, password, username_type=username_type)
    bank = fetch_bank_data(link_id, days)
    return bank, link_id
