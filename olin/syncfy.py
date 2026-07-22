"""
Syncfy (ex-Paybook) connector -> BankData

Replaces olin/belvo.py. Public interface is the same:

    # Already have a credential_id:
        from olin.syncfy import fetch_bank_data
        bank = fetch_bank_data(token, credential_id)

    # Full flow: create link on the fly (sandbox / onboarding):
        from olin.syncfy import create_link_and_fetch
        bank, credential_id = create_link_and_fetch(
            bank_site_id=SYNCFY_TEST_SITE_ID,
            username="test",
            password="test",
        )

Auth flow (Syncfy differs from Belvo):
  1. API KEY  → global, stored in SYNCFY_API_KEY env var
  2. User     → logical container per end-customer (POST /users)
  3. Session  → per-user token (POST /sessions)
  4. Credentials → bank link under that user (POST /credentials)
  5. Poll     → wait for sync job to finish
  6. Fetch    → GET /transactions + GET /accounts

Sandbox test site (Normal): id = 56cf5728784806f72b8b4568
  username = "test", password = "test"
"""
from __future__ import annotations

import os
import time
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise ImportError("pip install requests  (see requirements.txt)") from exc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .models import BankData

SYNCFY_BASE = os.getenv("SYNCFY_BASE_URL", "https://sync.paybook.com/v1")

# Default sandbox site – BBVA México Personal (use test credentials)
SYNCFY_TEST_SITE_ID = os.getenv("SYNCFY_SANDBOX_SITE_ID", "56cf5728784806f72b8b4568")

# Known MX bank site IDs (personal accounts)
SYNCFY_MX_SITES: dict[str, str] = {
    "BBVA":          "56cf5728784806f72b8b456b",  # BBVA México Personal
    "BBVA Bancomer": "56cf5728784806f72b8b456b",
    "Banamex":       "56cf5728784806f72b8b456c",  # BancaNet Personal
    "Banorte":       "56cf5728784806f72b8b456e",  # Banorte Personal
    "HSBC":          "5719a71a7848060f038b4569",  # HSBC Banca Empresas
    "Santander":     "5731fb37784806a6118b4571",  # SuperNET Particulares
    "Scotiabank":    "5739cc3b7848066b028b4573",  # Scotiabank Personal
}

# Job status codes in the response array
_SUCCESS_CODES = {200, 201, 202, 203}   # 200=accounts, 201=transactions
_ERROR_CODES   = {401, 403, 406, 500}


def _api_key() -> str:
    k = os.environ.get("SYNCFY_API_KEY", "").strip()
    if not k:
        raise EnvironmentError(
            "SYNCFY_API_KEY must be set. "
            "Sign up at https://paybook.com/sync to get a sandbox key, "
            "then add it to your .env file."
        )
    return k


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def ping() -> dict:
    """GET /users – cheapest call to verify the API key."""
    resp = requests.get(
        f"{SYNCFY_BASE}/users",
        params={"api_key": _api_key()},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def list_sites(is_test: bool = False) -> list[dict]:
    """Return available banking institutions.

    Pass is_test=True to list only sandbox test sites.
    """
    params: dict = {"api_key": _api_key()}
    if is_test:
        params["is_test"] = 1
    resp = requests.get(f"{SYNCFY_BASE}/sites", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("response", [])


# ---------------------------------------------------------------------------
# User + session
# ---------------------------------------------------------------------------

def _unwrap(body: dict, key: str, endpoint: str) -> dict:
    """Extract a single-object response (dict or first element of list)."""
    r = body.get("response")
    if isinstance(r, dict):
        return r
    if isinstance(r, list) and r:
        return r[0]
    raise RuntimeError(f"{endpoint}: unexpected response {body}")


def create_user(name: str) -> str:
    """Create a Syncfy user and return id_user."""
    resp = requests.post(
        f"{SYNCFY_BASE}/users",
        json={"api_key": _api_key(), "name": name},
        timeout=15,
    )
    resp.raise_for_status()
    return _unwrap(resp.json(), "response", "create_user")["id_user"]


def create_session(id_user: str) -> str:
    """Create a session for id_user and return the token."""
    resp = requests.post(
        f"{SYNCFY_BASE}/sessions",
        json={"api_key": _api_key(), "id_user": id_user},
        timeout=15,
    )
    resp.raise_for_status()
    return _unwrap(resp.json(), "response", "create_session")["token"]


# ---------------------------------------------------------------------------
# Credentials (bank links)
# ---------------------------------------------------------------------------

def create_credentials(
    token: str,
    id_site: str,
    creds: dict,
) -> Tuple[str, str]:
    """POST /credentials and return (id_credential, status_url).

    creds example: {"username": "test", "password": "test"}
    """
    payload = {"token": token, "id_site": id_site, "credentials": creds}
    resp = requests.post(
        f"{SYNCFY_BASE}/credentials",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    cred = _unwrap(resp.json(), "response", "create_credentials")
    id_credential = cred.get("id_credential", "")
    status_url    = cred.get("status", f"{SYNCFY_BASE}/jobs/{id_credential}/status")
    if not id_credential:
        raise RuntimeError(f"create_credentials: no id_credential in {resp.json()}")
    return id_credential, status_url


def poll_sync(status_url: str, token: str, max_wait: int = 120) -> bool:
    """Poll the job status URL until the sync finishes or times out.

    Returns True on success, False on error or timeout.
    """
    deadline = time.time() + max_wait
    seen_codes: set[int] = set()

    while time.time() < deadline:
        try:
            resp = requests.get(
                status_url,
                params={"token": token},
                timeout=15,
            )
            resp.raise_for_status()
            events = resp.json().get("response", [])
            for ev in events:
                code = ev.get("code", 0)
                seen_codes.add(code)

            # Error state
            if seen_codes & _ERROR_CODES:
                return False

            # Done: transactions (201) or accounts (200) confirmed
            if seen_codes & {201, 202}:
                return True
            if 200 in seen_codes and time.time() > deadline - max_wait + 10:
                # 200 = accounts ready; wait a bit more for transactions
                pass

        except requests.RequestException:
            pass

        time.sleep(5)

    # Timed out — if we saw any success code, proceed anyway
    return bool(seen_codes & _SUCCESS_CODES)


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------

def _get_account_balance(token: str, id_credential: str) -> Optional[float]:
    """Try to get the current balance from the accounts endpoint."""
    try:
        resp = requests.get(
            f"{SYNCFY_BASE}/accounts",
            params={"token": token, "id_credential": id_credential},
            timeout=20,
        )
        resp.raise_for_status()
        accounts = resp.json().get("response", [])
        for acc in accounts:
            bal = acc.get("balance")
            if bal is not None:
                return float(bal)
    except Exception:
        pass
    return None


def _fetch_transactions(
    token: str,
    id_credential: str,
    dt_from: int,
    dt_to: int,
) -> list[dict]:
    """GET /transactions with date range filters (Unix timestamps)."""
    params = {
        "token": token,
        "id_credential": id_credential,
        "dt_transaction[gte]": dt_from,
        "dt_transaction[lte]": dt_to,
    }
    results: list[dict] = []
    url: Optional[str] = f"{SYNCFY_BASE}/transactions"

    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        page = body.get("response", [])
        if not isinstance(page, list):
            break
        results.extend(page)
        # Syncfy uses next/previous pagination links
        url = body.get("next")
        params = {}  # pagination URL already contains all params

    return results


# ---------------------------------------------------------------------------
# Collection calendar
# ---------------------------------------------------------------------------

_DOW_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _compute_collection_calendar(deposits: list[tuple[int, float]]) -> Optional[dict]:
    """
    Identify which days of the week and month deposits typically land.

    Requires at least 6 deposit events to produce a meaningful pattern.
    Returns None if data is insufficient.

    best_days_of_week: up to 3 day names with above-average deposit frequency
    best_days_of_month: up to 5 calendar days (1-31) with clustering (e.g. 1, 15, 30)
    pattern_confidence: 0..1 — how concentrated vs. uniform the deposit pattern is
    """
    if len(deposits) < 6:
        return None

    dow_counts: dict[int, int] = defaultdict(int)   # 0=Mon … 6=Sun
    dom_counts: dict[int, int] = defaultdict(int)   # 1-31

    for ts, _ in deposits:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        dow_counts[dt.weekday()] += 1
        dom_counts[dt.day] += 1

    n = len(deposits)

    # Days of week with at least 1.3× the average frequency, sorted by frequency
    avg_dow = n / 7
    best_dow = sorted(
        [d for d in range(7) if dow_counts.get(d, 0) >= avg_dow * 1.3],
        key=lambda d: -dow_counts.get(d, 0),
    )[:3]
    best_days_of_week = [_DOW_NAMES[d] for d in best_dow]

    # Days of month with at least 1.5× the average frequency (31 buckets → noisier)
    avg_dom = n / 31
    best_dom = sorted(
        [d for d in range(1, 32) if dom_counts.get(d, 0) >= avg_dom * 1.5],
        key=lambda d: -dom_counts.get(d, 0),
    )[:5]
    best_days_of_month = sorted(best_dom)

    # Confidence: how much the top-3 days of the week account for vs. uniform 3/7
    top3_share = sum(dow_counts.get(d, 0) for d in (best_dow or list(range(3)))) / n
    uniform_3_share = 3 / 7
    raw_conf = (top3_share - uniform_3_share) / (1 - uniform_3_share)
    pattern_confidence = round(max(0.0, min(1.0, raw_conf)), 2)

    return {
        "best_days_of_week": best_days_of_week,
        "best_days_of_month": best_days_of_month,
        "pattern_confidence": pattern_confidence,
        "basis": "syncfy_transactions",
    }


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_bank_data(
    txns: list[dict],
    days: int,
    account_balance: Optional[float] = None,
) -> BankData:
    if not txns:
        return BankData(months_connected=0.0, source="syncfy")

    num_months = days / 30.0

    # Parse and sort by timestamp
    now_ts = int(datetime.now(timezone.utc).timestamp())
    dated: list[tuple[int, float]] = []
    for t in txns:
        ts = t.get("dt_transaction")
        amt = t.get("amount")
        if ts is not None and amt is not None:
            try:
                dated.append((int(ts), float(amt)))
            except (TypeError, ValueError):
                pass
    dated.sort(key=lambda x: x[0])

    if not dated:
        return BankData(months_connected=0.0, source="syncfy")

    # Deposits = positive amounts; outflows = negative
    deposits = [(ts, amt) for ts, amt in dated if amt > 0]
    outflows = [(ts, amt) for ts, amt in dated if amt < 0]
    monthly_deposit_count = len(deposits) / num_months if num_months > 0 else 0.0
    monthly_deposit_volume = sum(amt for _, amt in deposits) / num_months if num_months > 0 else 0.0
    monthly_outflow_volume = sum(-amt for _, amt in outflows) / num_months if num_months > 0 else 0.0

    # Deposit regularity via weekly CV
    weekly_counts: dict[int, int] = defaultdict(int)
    for ts, _ in deposits:
        week_idx = (now_ts - ts) // (7 * 86400)
        if 0 <= week_idx < days // 7 + 1:
            weekly_counts[week_idx] += 1

    weeks_total = max(days // 7, 1)
    counts = [weekly_counts.get(w, 0) for w in range(weeks_total)]
    mean_c = statistics.mean(counts)
    if len(counts) >= 2 and mean_c > 0:
        cv = statistics.stdev(counts) / mean_c
        deposit_regularity = max(0.0, min(1.0, 1.0 - cv))
    else:
        deposit_regularity = 0.5

    # Running balance: compute cumulative sum from all transactions,
    # then anchor to account_balance if available.
    cumsum = 0.0
    balance_series: list[float] = []
    for _, amt in dated:
        cumsum += amt
        balance_series.append(cumsum)

    if account_balance is not None and balance_series:
        shift = account_balance - balance_series[-1]
        balance_series = [b + shift for b in balance_series]

    avg_daily_balance = statistics.mean(balance_series)
    min_daily_balance = min(balance_series)
    overdrafts = sum(1 for b in balance_series if b < 0)

    n = len(balance_series)
    mid = n // 2
    balance_trend = 0.0
    if mid > 0:
        first_avg = statistics.mean(balance_series[:mid])
        second_avg = statistics.mean(balance_series[mid:])
        if first_avg != 0:
            raw_trend = (second_avg - first_avg) / abs(first_avg)
            balance_trend = max(-1.0, min(1.0, raw_trend))

    return BankData(
        months_connected=round(num_months, 1),
        avg_daily_balance_mxn=round(avg_daily_balance, 2),
        monthly_deposit_count=round(monthly_deposit_count, 1),
        monthly_deposit_volume_mxn=round(monthly_deposit_volume, 2),
        monthly_outflow_volume_mxn=round(monthly_outflow_volume, 2),
        deposit_regularity=round(deposit_regularity, 3),
        overdrafts_90d=overdrafts,
        balance_trend_90d=round(balance_trend, 3),
        min_daily_balance_mxn=round(min_daily_balance, 2),
        source="syncfy",
        verified=True,
        recommended_collection_days=_compute_collection_calendar(deposits),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_bank_data(token: str, id_credential: str, days: int = 90) -> BankData:
    """Fetch transactions for an existing credential and return BankData.

    Args:
        token: session token for the user who owns the credential.
        id_credential: returned by create_credentials().
        days: lookback window in days.
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    dt_from = now_ts - days * 86400
    txns = _fetch_transactions(token, id_credential, dt_from, now_ts)
    balance = _get_account_balance(token, id_credential)
    return _compute_bank_data(txns, days, account_balance=balance)


def create_link_and_fetch(
    bank_site_id: str,
    username: str,
    password: str,
    days: int = 90,
    user_name: Optional[str] = None,
) -> Tuple[BankData, str]:
    """Full flow: create user → session → credentials → poll → fetch.

    Returns (BankData, id_credential).

    Sandbox quick-start:
        bank, cred_id = create_link_and_fetch(
            SYNCFY_TEST_SITE_ID, "test", "test"
        )
    """
    name = user_name or f"olin_{int(time.time())}"
    id_user = create_user(name)
    token = create_session(id_user)
    id_credential, status_url = create_credentials(
        token, bank_site_id, {"username": username, "password": password}
    )
    poll_sync(status_url, token, max_wait=120)
    bank = fetch_bank_data(token, id_credential, days)
    return bank, id_credential
