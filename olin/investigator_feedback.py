"""Synthetic attributed annotations; never evidence or bank decision authority."""

import base64
import hashlib
import hmac
import json
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from uuid import UUID

from .investigator_app import InvestigatorAppError
from .investigator_reports import canonical

RECEIPT_VERSION = "investigator-report-receipt-1"
STATUSES = {
    "PENDING",
    "UNKNOWN",
    "UNAVAILABLE",
    "OBSERVED",
    "NOT_APPLICABLE",
    "WINDOW_INCOMPLETE",
}
FIELDS = {
    "kind",
    "receipt",
    "action_id",
    "observation_status",
    "judgment",
    "explanation",
    "source_description",
    "source_reference",
    "occurred_at",
    "predecessor",
    "expected_version",
    "correction_reason",
    "idempotency_key",
}


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid bounded annotation text")
    return value


class FeedbackService:
    """The authenticated app is the issuer/verifier; the writer has no model/evidence credentials.

    Receipt HMAC is domain-separated from sessions. It authenticates historical
    provenance only. Present access is rechecked on every command in PostgreSQL.
    Key rotation invalidates outstanding receipts; it does not erase annotations.
    """

    def __init__(self, workflow, connect, signing_secret):
        if len(signing_secret) < 32:
            raise ValueError("Report receipt signing secret required")
        self.workflow, self.connect = workflow, connect
        self._key = hmac.new(
            signing_secret, RECEIPT_VERSION.encode(), hashlib.sha256
        ).digest()

    def _db(self, identity, sql, values, *, read_only=False):
        if identity.role != "analyst":
            raise InvestigatorAppError(
                403, "FEEDBACK_DENIED", "Analyst access required"
            )
        try:
            with closing(self.connect()) as conn, conn.transaction():
                if read_only:
                    conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL ROLE olin_investigator_feedback")
                conn.execute(
                    "SET LOCAL statement_timeout='5000ms'; SET LOCAL lock_timeout='1000ms'"
                )
                conn.execute(
                    "SELECT set_config('olin.tenant_id',%s,true)",
                    (str(identity.tenant_id),),
                )
                return conn.execute(sql, values).fetchone()[0]
        except Exception as exc:
            known_rejection = str(getattr(exc, "sqlstate", "")) in {
                "P0001",
                "42501",
                "40001",
                "23505",
                "23514",
                "23503",
                "22P02",
            }
            raise InvestigatorAppError(
                409 if known_rejection else 503,
                "ANNOTATION_UNAVAILABLE",
                "Access, version or replay conflict"
                if known_rejection
                else "Database result unconfirmed; retry the identical command",
            ) from exc

    def report(self, identity, case_id):
        # No receipt is issued for arbitrary caller JSON. Capture remains read-only.
        self.history(identity, case_id)
        pair = self.workflow.current_report(identity, case_id)
        payload = {
            "version": RECEIPT_VERSION,
            "actor": identity.name,
            "manifest": pair["manifest"],
            "action_ids": [
                x["action"]["action_id"] for x in pair["annex"]["action_history"]
            ],
        }
        return {**pair, "feedback_receipt": self._sign(payload)}

    def _sign(self, payload):
        encoded = base64.urlsafe_b64encode(canonical(payload).encode()).decode()
        signature = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + "." + signature

    def _receipt(self, identity, case_id, receipt):
        try:
            if not isinstance(receipt, str) or len(receipt) > 16000:
                raise ValueError
            encoded, signature = receipt.split(".")
            if not hmac.compare_digest(
                hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest(),
                signature,
            ):
                raise ValueError
            payload = json.loads(
                base64.b64decode(encoded, altchars=b"-_", validate=True)
            )
            m = payload["manifest"]
            if (
                payload["version"] != RECEIPT_VERSION
                or payload["actor"] != identity.name
                or m["tenant_id"] != str(identity.tenant_id)
                or m["case_id"] != str(case_id)
            ):
                raise ValueError
            return payload
        except (ValueError, KeyError, TypeError):
            raise InvestigatorAppError(
                400, "INVALID_REPORT_RECEIPT", "Server-issued report receipt required"
            ) from None

    def append(self, identity, case_id, body):
        if not isinstance(body, dict) or set(body) != FIELDS:
            raise ValueError(
                "Closed annotation fields required; caller identity/trust fields prohibited"
            )
        receipt = self._receipt(identity, case_id, body["receipt"])
        kind, status = body["kind"], body["observation_status"]
        if kind not in {"FEEDBACK", "EXTERNAL_OUTCOME"} or status not in STATUSES:
            raise ValueError("Unsupported annotation kind/status")
        text(body["explanation"], 1000)
        text(body["idempotency_key"], 240)
        action = body["action_id"]
        if action is not None and action not in receipt["action_ids"]:
            raise ValueError("Action was not in the referenced report")
        if kind == "FEEDBACK":
            if (
                body["source_description"] is not None
                or body["source_reference"] is not None
            ):
                raise ValueError("Own judgment cannot impersonate an external source")
            if status == "OBSERVED" and body["judgment"] not in {
                "USEFUL",
                "NOT_USEFUL",
                "UNCERTAIN",
            }:
                raise ValueError("Attributed judgment required")
        else:
            text(body["source_description"], 500)
            text(body["source_reference"], 240)
            if body["judgment"] is not None:
                raise ValueError("External reports are not usefulness ratings")
        if status != "OBSERVED" and body["judgment"] is not None:
            raise ValueError("Missing observation is not negative feedback")
        occurred = body["occurred_at"]
        if occurred is not None:
            text(occurred, 50)
            at = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            if at.tzinfo is None or at > datetime.now(timezone.utc):
                raise ValueError(
                    "Occurrence requires timezone and cannot be in the future"
                )
        previous = body["predecessor"]
        version = body["expected_version"]
        if type(version) is not int or version < 0:
            raise ValueError("Expected version required")
        if previous is not None:
            previous = UUID(previous)
            text(body["correction_reason"], 500)
        elif body["correction_reason"] is not None or version != 0:
            raise ValueError("Initial annotation has no correction predecessor")
        payload = {
            k: body[k]
            for k in (
                "observation_status",
                "judgment",
                "explanation",
                "source_description",
                "source_reference",
                "occurred_at",
                "action_id",
                "correction_reason",
            )
        }
        payload["report_binding"] = receipt["manifest"]
        return self._db(
            identity,
            "SELECT investigator.append_feedback(%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
            (
                identity.tenant_id,
                case_id,
                identity.name,
                kind,
                canonical(payload),
                body["idempotency_key"],
                previous,
                version,
            ),
        )

    def history(self, identity, case_id):
        record = self._db(
            identity,
            "SELECT investigator.read_measurements(%s,%s)",
            (identity.tenant_id, case_id),
            read_only=True,
        )
        effective = self.effective(record["annotations"])
        for item in effective:
            item["correction_receipt"] = self._sign(
                {
                    "version": RECEIPT_VERSION,
                    "actor": identity.name,
                    "manifest": item["payload"]["report_binding"],
                    "action_ids": [item["payload"]["action_id"]]
                    if item["payload"]["action_id"]
                    else [],
                }
            )
        return {
            **record,
            "effective_records": effective,
            "notice": "SYNTHETIC annotations, not canonical evidence or report sign-offs. Historical report authenticity is not current evidence eligibility. External statements are analyst-reported, never authenticated bank events. Original pre-exposure disposition: NOT ESTABLISHED.",
            "organization_meaning": "Authenticated tenant organization identifier only; no bank identity asserted",
        }

    @staticmethod
    def effective(records):
        streams = {}
        for item in records:
            if (
                item["stream_id"] not in streams
                or item["version"] > streams[item["stream_id"]]["version"]
            ):
                streams[item["stream_id"]] = item
        return sorted(
            streams.values(), key=lambda x: (x["recorded_at"], x["record_id"])
        )

    def cohorts(self, identity):
        records = self.history(identity, None)
        latest = {}
        for c in records["cohort_versions"]:
            latest[c["cohort_id"]] = c
        result = []
        for cohort in latest.values():
            members = []
            for member in cohort["definition"]["members"]:
                entries = [
                    r
                    for r in records["effective_records"]
                    if r["case_id"] == member["case_id"]
                ]
                observations = {}
                for kind in ("FEEDBACK", "EXTERNAL_OUTCOME"):
                    relevant = [r for r in entries if r["kind"] == kind]
                    # Report all effective observations, never select only positive judgments.
                    observations[kind] = {
                        "status": "NOT_YET_OBSERVED" if not relevant else "RECORDED",
                        "observations": [
                            {
                                "record_id": r["record_id"],
                                "status": r["payload"]["observation_status"],
                                "judgment": r["payload"]["judgment"],
                            }
                            for r in relevant
                        ],
                    }
                members.append({**member, "observations": observations})
            counts = {}
            for kind in ("FEEDBACK", "EXTERNAL_OUTCOME"):
                counts[kind] = dict(
                    Counter(
                        "NOT_YET_OBSERVED"
                        if m["observations"][kind]["status"] == "NOT_YET_OBSERVED"
                        else "HAS_RECORDED_ANNOTATION"
                        for m in members
                    )
                )
            result.append(
                {
                    **cohort,
                    "members": members,
                    "declared_denominator": len(members),
                    "eligible_count": sum(m["eligible"] for m in members),
                    "counts": counts,
                }
            )
        return {
            "as_of": records["as_of"],
            "cohorts": result,
            "membership_history": records["cohort_versions"],
            "notice": "Declared synthetic universe only, not a bank portfolio. Stopped/missing cases remain. Counts are observations, not performance. No cost aggregation; use existing action transition references and currencies, never assume unknown cost is zero.",
        }
