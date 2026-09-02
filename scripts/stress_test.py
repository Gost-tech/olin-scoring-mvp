#!/usr/bin/env python3
"""Local, destructive-to-temporary-data stress gate for the Olin bank API.

The command starts a production-mode server against a temporary SQLite file,
exercises concurrent reads and state-machine races, verifies database
invariants, and removes the temporary database when finished. It never calls
an external provider and never enables money movement.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import resource
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from olin import server
from olin.bank_ingestion import canonical_json, sign_payload
from olin.store import ScoringLog


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def _rss_mib() -> float:
    # macOS reports bytes; Linux reports KiB.
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if os.uname().sysname == "Darwin" else rss / 1024


@contextmanager
def _environment(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _running_server(db_path: str):
    previous_db = server.DB_PATH
    server.DB_PATH = db_path
    server._RATE_WINDOWS.clear()
    httpd = server.OlinHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=3)
        httpd.server_close()
        server.DB_PATH = previous_db
        server._RATE_WINDOWS.clear()


def _request(
    base: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    *,
    token: str = "",
    signature: str = "",
    timeout: float = 15,
) -> tuple[int, dict, float]:
    raw = None if body is None else canonical_json(body)
    headers = {"Content-Type": "application/json"} if raw is not None else {}
    if token:
        headers["X-Olin-Analyst-Token"] = token
    if signature:
        headers["X-Olin-Signature"] = signature
    request = urllib.request.Request(base + path, data=raw, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            return response.status, json.loads(content) if content else {}, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        try:
            content = exc.read()
            return exc.code, json.loads(content) if content else {}, time.perf_counter() - started
        finally:
            exc.close()
    except (OSError, TimeoutError) as exc:
        return 0, {"transport_error": str(exc)}, time.perf_counter() - started


def _run_parallel(
    name: str,
    count: int,
    concurrency: int,
    operation: Callable[[int], tuple[int, dict, float]],
    accepted: set[int],
) -> tuple[dict, list[tuple[int, dict, float]]]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(operation, range(count)))
    elapsed = time.perf_counter() - started
    latencies = [item[2] * 1000 for item in results]
    failures = [item for item in results if item[0] not in accepted]
    summary = {
        "scenario": name,
        "requests": count,
        "concurrency": concurrency,
        "elapsed_s": round(elapsed, 3),
        "rps": round(count / elapsed, 1) if elapsed else 0,
        "p50_ms": round(_percentile(latencies, 0.50), 1),
        "p95_ms": round(_percentile(latencies, 0.95), 1),
        "p99_ms": round(_percentile(latencies, 0.99), 1),
        "max_ms": round(max(latencies, default=0), 1),
        "unexpected": len(failures),
        "failure_samples": [
            {"status": item[0], "body": item[1]} for item in failures[:3]
        ],
        "statuses": {str(code): sum(1 for item in results if item[0] == code)
                     for code in sorted({item[0] for item in results})},
    }
    return summary, results


def _intake_body(index: int) -> dict:
    return {
        "partner_case_reference": f"STRESS-{index:08d}-{secrets.token_hex(3)}",
        "cohort_id": "local_stress_gate",
        "merchant_name": f"Comercio Stress {index}",
    }


def _scoring_body() -> dict:
    return {
        "business_type": "abarrotes",
        "business_description": "Tienda de barrio con ventas diarias verificadas.",
        "funding_purpose": "inventory",
        "project_description": "Compra de inventario de alta rotación.",
        "requested_mxn": 20_000,
        "colonia": "Iztapalapa",
        "tenure": {"years_on_google_maps": 5, "years_in_imss": 2,
                   "address_consistent": True},
        "buro": {"checked": True, "active_delinquencies": 0,
                 "active_loans_count": 1, "worst_mob_status": "01", "score": 700,
                 "source": "partner_bureau", "verified": True,
                 "evidence_reference": "BUREAU-STRESS-001"},
        "fraud": {"phone_mx": "5500000000", "rfc": "UAT850101AB1", "curp": "",
                  "ine_checked": True, "address_stated": "Iztapalapa, CDMX"},
    }


def _prepare_evidence_ready(
    base: str, token: str, secret: str, index: int,
) -> tuple[str, str]:
    status, created, _ = _request(base, "/api/v1/intakes", "POST", _intake_body(index), token=token)
    if status != 201:
        raise RuntimeError(f"intake setup failed: {status} {created}")
    intake_id = created["data"]["intake_id"]
    status, consent, _ = _request(
        base, f"/api/v1/intakes/{intake_id}/consents", "POST",
        {"channel": "in_person", "policy_version": "stress-v1",
         "text": "Autorizo el enlace bancario y la evaluación crediticia de esta prueba."},
        token=token,
    )
    if status != 201:
        raise RuntimeError(f"consent setup failed: {status} {consent}")
    consent_id = consent["data"]["consent_id"]
    status, link, _ = _request(
        base, f"/api/v1/intakes/{intake_id}/link-sessions", "POST",
        {"provider": "partner-bank-sandbox", "ttl_minutes": 15}, token=token,
    )
    if status != 201:
        raise RuntimeError(f"link setup failed: {status} {link}")
    link_id = link["data"]["link_session_id"]
    event = {
        "event_id": f"stress-event-{index}-{secrets.token_hex(4)}",
        "intake_id": intake_id,
        "link_session_id": link_id,
        "provider": "partner-bank-sandbox",
        "connection_id": f"stress-connection-{index}",
        "consent_id": consent_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "months_connected": 8, "avg_daily_balance_mxn": 17_000,
            "monthly_deposit_count": 23, "monthly_deposit_volume_mxn": 82_000,
            "monthly_outflow_volume_mxn": 56_000, "deposit_regularity": 0.84,
            "overdrafts_90d": 0, "balance_trend_90d": 0.05,
            "min_daily_balance_mxn": 3_900,
        },
    }
    raw = canonical_json(event)
    status, accepted, _ = _request(
        base, "/api/v1/webhooks/bank-evidence", "POST", event,
        signature=sign_payload(raw, secret),
    )
    if status != 201:
        raise RuntimeError(f"callback setup failed: {status} {accepted}")
    return intake_id, event["event_id"]


def run_stress(reads: int, writes: int, concurrency: int) -> dict:
    partner_token = secrets.token_urlsafe(32)
    other_token = secrets.token_urlsafe(32)
    analyst_token = secrets.token_urlsafe(32)
    admin_token = secrets.token_urlsafe(32)
    webhook_secret = secrets.token_urlsafe(48)
    users = {
        "stress_bank": {"token": partner_token, "role": "partner"},
        "other_bank": {"token": other_token, "role": "partner"},
        "stress_analyst": {"token": analyst_token, "role": "analyst"},
        "stress_admin": {"token": admin_token, "role": "admin"},
    }
    env = {
        "OLIN_MODE": "production",
        "OLIN_ALLOW_LEGACY_CONSENT": "1",
        "OLIN_USERS": json.dumps(users),
        "OLIN_BANK_WEBHOOK_SECRET": webhook_secret,
        "OLIN_LIVE_LENDING_ENABLED": "0",
        "OLIN_RATE_LIMIT_PER_MINUTE": "10000",
    }
    handle = tempfile.NamedTemporaryFile(prefix="olin-stress-", suffix=".db", delete=False)
    db_path = handle.name
    handle.close()
    summaries: list[dict] = []
    checks: list[dict] = []
    rss_before = _rss_mib()
    try:
        with ScoringLog(db_path):
            pass
        with _environment(env), _running_server(db_path) as base:
            summary, _ = _run_parallel(
                "readiness burst", reads, concurrency,
                lambda _: _request(base, "/readyz"), {200},
            )
            summaries.append(summary)

            summary, create_results = _run_parallel(
                "concurrent intake creation", writes, concurrency,
                lambda index: _request(
                    base, "/api/v1/intakes", "POST", _intake_body(index), token=partner_token
                ),
                {201},
            )
            summaries.append(summary)
            created_ids = [body["data"]["intake_id"] for status, body, _ in create_results if status == 201]

            sample_ids = created_ids[: min(25, len(created_ids))]
            summary, _ = _run_parallel(
                "cross-partner isolation", len(sample_ids), min(concurrency, 16),
                lambda index: _request(
                    base, f"/api/v1/intakes/{sample_ids[index]}", token=other_token
                ),
                {404},
            )
            summaries.append(summary)

            intake_id, event_id = _prepare_evidence_ready(
                base, partner_token, webhook_secret, writes + 1
            )
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT link_session_id,consent_id,connection_id,derived_metrics,observed_at "
                    "FROM intake_bank_event WHERE event_id=?", (event_id,),
                ).fetchone()
            metrics = json.loads(row[3])
            replay_event = {
                "event_id": event_id, "intake_id": intake_id, "link_session_id": row[0],
                "provider": metrics["source"], "connection_id": row[2],
                "consent_id": row[1], "observed_at": row[4],
                "metrics": {key: metrics[key] for key in (
                    "months_connected", "avg_daily_balance_mxn", "monthly_deposit_count",
                    "monthly_deposit_volume_mxn", "monthly_outflow_volume_mxn",
                    "deposit_regularity", "overdrafts_90d", "balance_trend_90d",
                    "min_daily_balance_mxn",
                )},
            }
            replay_raw = canonical_json(replay_event)
            summary, replay_results = _run_parallel(
                "concurrent webhook replay", max(20, concurrency), concurrency,
                lambda _: _request(
                    base, "/api/v1/webhooks/bank-evidence", "POST", replay_event,
                    signature=sign_payload(replay_raw, webhook_secret),
                ),
                {200},
            )
            summaries.append(summary)
            checks.append({
                "check": "replayed webhook stays single-write",
                "passed": all(status == 200 and body["data"]["duplicate"]
                              for status, body, _ in replay_results),
            })

            summary, score_results = _run_parallel(
                "duplicate scoring race", max(20, concurrency), concurrency,
                lambda _: _request(
                    base, f"/api/v1/intakes/{intake_id}/score", "POST",
                    _scoring_body(), token=partner_token,
                ),
                {201, 422},
            )
            summaries.append(summary)
            checks.append({
                "check": "exactly one score created",
                "passed": sum(1 for status, _, _ in score_results if status == 201) == 1,
            })

        with sqlite3.connect(db_path) as conn:
            intake_count = conn.execute("SELECT COUNT(*) FROM intake").fetchone()[0]
            event_count = conn.execute(
                "SELECT COUNT(*) FROM intake_bank_event WHERE event_id=?", (event_id,)
            ).fetchone()[0]
            scored_count = conn.execute(
                "SELECT COUNT(*) FROM scoring_log WHERE partner_case_reference=("
                "SELECT partner_case_reference FROM intake WHERE intake_id=?)", (intake_id,),
            ).fetchone()[0]
            disbursed = conn.execute(
                "SELECT COUNT(*) FROM scoring_log WHERE disbursed_at IS NOT NULL"
            ).fetchone()[0]
        checks.extend([
            {"check": "all successful intake writes persisted",
             "passed": intake_count == len(created_ids) + 1,
             "detail": {"expected": len(created_ids) + 1, "actual": intake_count}},
            {"check": "one bank event persisted after replay storm", "passed": event_count == 1},
            {"check": "one scoring row persisted after scoring race", "passed": scored_count == 1},
            {"check": "money movement remained disabled", "passed": disbursed == 0},
        ])
    finally:
        Path(db_path).unlink(missing_ok=True)
    rss_after = _rss_mib()
    passed = all(item["unexpected"] == 0 for item in summaries) and all(
        item["passed"] for item in checks
    )
    return {
        "passed": passed,
        "configuration": {"reads": reads, "writes": writes, "concurrency": concurrency,
                          "server": "OlinHTTPServer", "database": "temporary SQLite WAL",
                          "live_lending_enabled": False},
        "scenarios": summaries,
        "invariants": checks,
        "memory": {"max_rss_before_mib": round(rss_before, 1),
                   "max_rss_after_mib": round(rss_after, 1),
                   "max_rss_delta_mib": round(max(0, rss_after - rss_before), 1)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reads", type=int, default=500)
    parser.add_argument("--writes", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    args = parser.parse_args()
    if args.reads < 1 or args.writes < 1 or not 1 <= args.concurrency <= 256:
        parser.error("reads/writes must be positive and concurrency must be 1..256")
    report = run_stress(args.reads, args.writes, args.concurrency)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
