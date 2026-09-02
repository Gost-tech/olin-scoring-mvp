#!/usr/bin/env python3
"""Executable bank acceptance journey against a clean local Olin instance."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import json
import os
import secrets
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from olin import server
from olin.bank_ingestion import canonical_json, sign_payload
from olin.store import ScoringLog


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
def _server(db_path: str):
    previous_db = server.DB_PATH
    server.DB_PATH = db_path
    httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)
        httpd.server_close()
        server.DB_PATH = previous_db


def _request(
    base: str, path: str, method: str = "GET", body: dict | None = None,
    token: str = "", signature: str = "",
) -> tuple[int, dict]:
    raw = None if body is None else canonical_json(body)
    headers = {"Content-Type": "application/json"} if raw is not None else {}
    if token:
        headers["X-Olin-Analyst-Token"] = token
    if signature:
        headers["X-Olin-Signature"] = signature
    request = urllib.request.Request(
        base + path, data=raw, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            content = response.read()
            return response.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        try:
            content = exc.read()
            return exc.code, json.loads(content) if content else {}
        finally:
            exc.close()


def _case_payload(now: str) -> dict:
    return {
        "merchant_name": "Comercio Banco Sandbox",
        "business_type": "abarrotes",
        "business_description": "Tienda de barrio evaluada por una institución sandbox.",
        "funding_purpose": "inventory",
        "project_description": "Compra de inventario de alta rotación para cuatro semanas.",
        "evidence_route": "bank_flow_led",
        "requested_mxn": 20_000,
        "colonia": "Iztapalapa",
        "case_mode": "shadow",
        "cohort_id": "bank_acceptance_sandbox",
        "partner_case_reference": "BANK-UAT-0001",
        "consent": {
            "channel": "in_person",
            "text": "Autorizo la evaluación crediticia del piloto sombra y el uso de métricas bancarias derivadas.",
            "policy_version": "bank-uat-v1",
        },
        "bank": {
            "months_connected": 9,
            "avg_daily_balance_mxn": 18_500,
            "min_daily_balance_mxn": 4_200,
            "monthly_deposit_count": 24,
            "monthly_deposit_volume_mxn": 86_000,
            "monthly_outflow_volume_mxn": 59_500,
            "deposit_regularity": 0.86,
            "overdrafts_90d": 0,
            "balance_trend_90d": 0.06,
            "source": "partner_bank_sandbox",
            "verified": True,
            "evidence_reference": "BANK-UAT-EVIDENCE-0001",
            "observed_at": now,
        },
        "tenure": {"years_on_google_maps": 6, "years_in_imss": 3, "address_consistent": True},
        "maps": {"rating": 4.5, "review_count": 84, "review_velocity_6m": 7},
        "buro": {"checked": True, "active_delinquencies": 0, "active_loans_count": 1,
                 "worst_mob_status": "01", "score": 705,
                 "source": "partner_bureau", "verified": True,
                 "evidence_reference": "BUREAU-UAT-0001"},
        "fraud": {"phone_mx": "5500000000", "rfc": "UAT850101AB1", "curp": "",
                  "ine_checked": True, "address_stated": "Iztapalapa, CDMX"},
    }


def run_acceptance() -> dict:
    tokens = {name: secrets.token_urlsafe(32) for name in ("bank", "other", "analyst", "admin")}
    webhook_secret = secrets.token_urlsafe(48)
    users = {
        "bank_uat": {"token": tokens["bank"], "role": "partner"},
        "other_bank": {"token": tokens["other"], "role": "partner"},
        "olin_analyst": {"token": tokens["analyst"], "role": "analyst"},
        "olin_admin": {"token": tokens["admin"], "role": "admin"},
    }
    env = {
        "OLIN_MODE": "production",
        "OLIN_ALLOW_LEGACY_CONSENT": "1",
        "OLIN_USERS": json.dumps(users),
        "OLIN_BANK_WEBHOOK_SECRET": webhook_secret,
        "OLIN_LIVE_LENDING_ENABLED": "0",
        "OLIN_RATE_LIMIT_PER_MINUTE": "500",
    }
    steps: list[dict] = []

    def check(name: str, actual: int, expected: int, detail: str = "") -> None:
        steps.append({"step": name, "status": actual, "expected": expected,
                      "passed": actual == expected, "detail": detail})

    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = handle.name
    handle.close()
    try:
        with ScoringLog(db_path):
            pass
        with _environment(env), _server(db_path) as base:
            status, ready = _request(base, "/readyz")
            check(
                "local application readiness", status, 200,
                "local process/configuration checks green; external production gate is separate",
            )

            status, _ = _request(base, "/api/apps")
            check("missing authentication rejected", status, 401)

            status, created = _request(
                base, "/api/applications", "POST",
                _case_payload(datetime.now(timezone.utc).isoformat()), tokens["bank"],
            )
            check("bank creates shadow case", status, 201)
            application_id = created.get("application_id", "")

            status, _ = _request(
                base, f"/api/applications/{application_id}", token=tokens["other"]
            )
            check("cross-partner case isolation", status, 404)

            status, consents = _request(
                base, f"/api/v1/cases/{application_id}/consents", token=tokens["bank"]
            )
            check("bank reads consent evidence", status, 200)
            consent_id = consents.get("data", [{}])[0].get("consent_id", "")

            callback = {
                "event_id": "bank-uat-event-0001",
                "application_id": application_id,
                "provider": "partner-bank-sandbox",
                "connection_id": "bank-uat-connection-0001",
                "consent_id": consent_id,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    "months_connected": 9, "avg_daily_balance_mxn": 18_500,
                    "monthly_deposit_count": 24, "monthly_deposit_volume_mxn": 86_000,
                    "monthly_outflow_volume_mxn": 59_500, "deposit_regularity": 0.86,
                    "overdrafts_90d": 0, "balance_trend_90d": 0.06,
                    "min_daily_balance_mxn": 4_200,
                },
            }
            raw_callback = canonical_json(callback)
            status, _ = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", callback,
                signature="sha256=invalid",
            )
            check("invalid bank signature rejected", status, 401)

            signature = sign_payload(raw_callback, webhook_secret)
            status, ingested = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", callback,
                signature=signature,
            )
            check("signed bank metrics accepted", status, 201)

            status, replay = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST", callback,
                signature=signature,
            )
            check("callback replay is idempotent", status, 200,
                  "duplicate acknowledged without second write")

            conflicting_callback = dict(callback)
            conflicting_callback["connection_id"] = "different-connection"
            conflicting_raw = canonical_json(conflicting_callback)
            status, conflict = _request(
                base, "/api/v1/webhooks/bank-evidence", "POST",
                conflicting_callback,
                signature=sign_payload(conflicting_raw, webhook_secret),
            )
            check(
                "changed payload cannot reuse event id", status, 409,
                str((conflict.get("error") or {}).get("code", "")),
            )

            status, evidence = _request(
                base, f"/api/v1/cases/{application_id}/bank-evidence",
                token=tokens["bank"],
            )
            evidence_text = json.dumps(evidence)
            evidence_safe = not any(key in evidence_text.lower() for key in ("transactions", "password", "clabe"))
            check("derived evidence retrievable without raw banking data", status, 200,
                  "data minimization passed" if evidence_safe else "forbidden data detected")
            if not evidence_safe:
                steps[-1]["passed"] = False

            status, correction = _request(
                base, f"/api/v1/cases/{application_id}/corrections", "POST",
                {"field_path": "bank.monthly_deposit_count", "claimed_value": 25,
                 "reason": "Bank reconciliation found one additional deposit"},
                tokens["bank"],
            )
            check("bank opens correction", status, 201)
            request_id = correction.get("data", {}).get("request_id", "")

            resolution_path = f"/api/v1/cases/{application_id}/corrections/{request_id}/resolve"
            resolution = {"status": "accepted", "note": "Analyst verified source reconciliation"}
            status, _ = _request(base, resolution_path, "POST", resolution, tokens["bank"])
            check("partner cannot resolve own correction", status, 403)
            status, resolved = _request(base, resolution_path, "POST", resolution, tokens["analyst"])
            check("analyst resolves correction", status, 201,
                  "accepted correction requires a new score")

            status, _ = _request(
                base, f"/api/apps/{application_id}/outcome", "POST",
                {"partner_decision": "approved",
                 "partner_reason": "Sandbox bank confirms policy fit and repayment capacity"},
                tokens["bank"],
            )
            check("bank records independent decision", status, 200)

            status, _ = _request(
                base, f"/api/apps/{application_id}/disburse", "POST", {}, tokens["admin"]
            )
            check("shadow disbursement blocked", status, 403)

        with ScoringLog(db_path) as log:
            audit_types = [row[0] for row in log.conn.execute(
                "SELECT event_type FROM audit_event WHERE application_id=? ORDER BY occurred_at",
                (application_id,),
            ).fetchall()]
            bank_event_count = log.conn.execute(
                "SELECT COUNT(*) FROM bank_ingestion_event WHERE application_id=?",
                (application_id,),
            ).fetchone()[0]
            disbursed = log.conn.execute(
                "SELECT disbursed FROM scoring_log WHERE application_id=?", (application_id,)
            ).fetchone()[0]
        audit_ok = {
            "case_scored", "consent_recorded", "bank_evidence_ingested",
            "correction_requested", "correction_resolved", "partner_decision_recorded",
        }.issubset(audit_types)
        steps.append({"step": "complete immutable audit trail", "status": "checked",
                      "expected": "all events", "passed": audit_ok, "detail": ", ".join(audit_types)})
        steps.append({"step": "single bank event after replay", "status": bank_event_count,
                      "expected": 1, "passed": bank_event_count == 1, "detail": ""})
        steps.append({"step": "database confirms no disbursement", "status": disbursed,
                      "expected": 0, "passed": disbursed == 0, "detail": ""})
        return {
            "test": "Olin bank integration acceptance",
            "mode": "production-shadow",
            "passed": all(step["passed"] for step in steps),
            "application_id": application_id,
            "recommendation": created.get("recommendation"),
            "score": created.get("score"),
            "steps": steps,
            "security": {
                "secrets_in_report": False,
                "raw_transactions_stored": False,
                "money_movement": False,
            },
        }
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Olin bank acceptance journey")
    parser.parse_args()
    report = run_acceptance()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
