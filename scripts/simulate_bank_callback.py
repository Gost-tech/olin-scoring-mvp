#!/usr/bin/env python3
"""Send one deterministic, signed sandbox callback to an Olin deployment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from olin.bank_ingestion import canonical_json, sign_payload


def callback_payload(application_id: str, consent_id: str, event_id: str) -> dict:
    return {
        "event_id": event_id,
        "application_id": application_id,
        "provider": "partner-bank-sandbox",
        "connection_id": "sandbox-connection-001",
        "consent_id": consent_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "months_connected": 9,
            "avg_daily_balance_mxn": 18_500,
            "monthly_deposit_count": 24,
            "monthly_deposit_volume_mxn": 86_000,
            "monthly_outflow_volume_mxn": 59_500,
            "deposit_regularity": 0.86,
            "overdrafts_90d": 0,
            "balance_trend_90d": 0.06,
            "min_daily_balance_mxn": 4_200,
        },
    }


def safe_endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url.rstrip("/"))
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Use HTTPS, except for an explicit localhost test")
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("base-url must not contain credentials")
    return base_url.rstrip("/") + "/api/v1/webhooks/bank-evidence"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a signed Olin bank callback")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--consent-id", required=True)
    parser.add_argument("--event-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    secret = os.getenv("OLIN_BANK_WEBHOOK_SECRET", "")
    if len(secret) < 32:
        raise SystemExit("OLIN_BANK_WEBHOOK_SECRET must contain at least 32 characters")
    payload = callback_payload(
        args.application_id, args.consent_id, args.event_id or f"sandbox-{uuid4().hex}"
    )
    raw = canonical_json(payload)
    endpoint = safe_endpoint(args.base_url)
    if args.dry_run:
        print(json.dumps({"endpoint": endpoint, "payload": payload}, ensure_ascii=False, indent=2))
        return
    request = urllib.request.Request(
        endpoint,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Olin-Signature": sign_payload(raw, secret),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode("utf-8") + "\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
