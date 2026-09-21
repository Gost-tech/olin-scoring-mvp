"""Deterministic, ephemeral Phase 6 reports; no research or write authority."""

import hashlib
import html
import json
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

TEMPLATE_VERSION = "investigator-report-template-2"
INPUT_VERSION = "investigator-report-input-1"
MAX_REPORT_INPUT_BYTES = 2_097_152
ACTION_FIELDS = frozenset(
    [
        "action_id",
        "action_type",
        "question_id",
        "unresolved_question",
        "purpose",
        "permitted_data_scope",
        "requested_source",
        "prerequisites",
        "resolution_criteria",
        "relevant_finding_references",
        "analyst_rationale",
        "selected_snapshot_id",
        "selected_snapshot_digest",
        "selected_authority_revision",
        "selected_authority_digest",
        "selected_evidence_state_digest",
        "selected_assessment_digest",
        "phase3_rules_version",
        "phase3_schema_version",
        "phase4_rules_version",
        "phase4_schema_version",
        "catalogue_version",
        "action_schema_version",
        "selected_by_analyst",
        "selected_at",
    ]
)
TRANSITION_FIELDS = frozenset(
    [
        "transition_sequence",
        "from_status",
        "to_status",
        "reason_code",
        "reason_detail",
        "evidence_references",
        "actual_effort_minutes",
        "actual_cost_amount",
        "actual_cost_currency",
        "transitioned_by_analyst",
        "transitioned_at",
        "transition_digest",
    ]
)
NOTICE = (
    "SYNTHETIC DEVELOPMENT · Authorized AS OF the recorded server time only. "
    "Refresh requires a fresh check. Downloaded files cannot be remotely recalled. "
    "Administrative completion is not evidence verification. No credit decision "
    "or financing recommendation. Shadow research is excluded."
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class ReportInput:
    """Frozen serialized display data, never an authorization capability."""

    serialized: str

    @property
    def record(self):
        return json.loads(self.serialized)


def _actions(connection, tenant, case):
    rows = connection.execute(
        "SELECT action,transitions FROM investigator.read_investigation_actions(%s,%s)",
        (tenant, case),
    ).fetchall()
    return [{"action": r[0], "transitions": r[1]} for r in rows]


def capture(service, identity, case_id):
    """Read-only fence plus append-only history stability, then close all txns.

    Selection/evidence use the existing case fence. Transitions use their own
    action locks, so two equal history reads bracket reasoning: any intervening
    append fails the capture. No new lock order or write capability is introduced.
    """
    from .investigator.evidence_boundary import PostgresReasoningSnapshotGate
    from .investigator_app import InvestigatorAppError
    from .investigator_evidence_adapter import PostgresCanonicalEvidenceReadPort

    if identity.role != "analyst":
        raise InvestigatorAppError(403, "REPORT_DENIED", "Analyst access required")
    try:
        with (
            closing(service._action_connect()) as actions,
            closing(service._runtime_connect()) as runtime,
            closing(service._canonical_connect()) as canonical_reader,
            actions.transaction(),
        ):
            actions.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY")
            actions.execute("SET LOCAL ROLE olin_investigator_action_writer")
            actions.execute(
                "SET LOCAL statement_timeout='5000ms'; SET LOCAL lock_timeout='1000ms'; SET LOCAL idle_in_transaction_session_timeout='5000ms'"
            )
            actions.execute(
                "SELECT set_config('olin.tenant_id',%s,true)",
                (str(identity.tenant_id),),
            )
            # Validate tenant custody before acquiring a case lock.
            if actions.execute(
                "SELECT investigator.action_tenant_access_allowed(%s)",
                (identity.tenant_id,),
            ).fetchone() != (True,):
                raise ValueError("tenant denied")
            actions.execute(
                "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                "%s::text || ':reasoning-currentness:' || %s::text,0))",
                (identity.tenant_id, case_id),
            )
            before = _actions(actions, identity.tenant_id, case_id)
            custody = service._establish_custody(runtime)
            snapshot_id, _ = service._current_snapshot(
                runtime, identity.tenant_id, case_id
            )
            with runtime.transaction():
                service._runtime_context(runtime, identity.tenant_id, read_only=True)
                row = runtime.execute(
                    "SELECT event_head_sequence,canonical_digest,canonical_snapshot_payload "
                    "FROM investigator.case_snapshot WHERE tenant_id=%s AND case_id=%s AND snapshot_id=%s",
                    (identity.tenant_id, case_id, snapshot_id),
                ).fetchone()
                invalidations = runtime.execute(
                    "SELECT invalidation_id::text,snapshot_id::text,invalidation_event_id::text,"
                    "reason_code,reason_reference,invalidated_at,invalidated_by_actor_type,"
                    "invalidated_by_actor_reference FROM investigator.case_snapshot_invalidation "
                    "WHERE tenant_id=%s AND case_id=%s ORDER BY invalidated_at,invalidation_id",
                    (identity.tenant_id, case_id),
                ).fetchall()
                invalidations = [
                    dict(
                        zip(
                            (
                                "invalidation_id",
                                "snapshot_id",
                                "invalidation_event_id",
                                "reason_code",
                                "reason_reference",
                                "invalidated_at",
                                "actor_type",
                                "actor_reference",
                            ),
                            (*item[:5], item[5].isoformat(), *item[6:]),
                            strict=True,
                        )
                    )
                    for item in invalidations
                ]
            gate = PostgresReasoningSnapshotGate(
                runtime_connection=runtime,
                evidence_authority=PostgresCanonicalEvidenceReadPort(
                    canonical_reader, tenant_id=identity.tenant_id
                ),
                runtime_custody=custody,
            )
            reconstruction = gate.reconstruct_economics_current(
                tenant_id=identity.tenant_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                as_of=datetime.now(timezone.utc),
            ).canonical_record()
            after = _actions(actions, identity.tenant_id, case_id)
            if canonical(before) != canonical(after):
                raise ValueError("action history changed during capture")
            binding = reconstruction["input_assessment"]
            if row is None or row[1] != binding["snapshot_digest"]:
                raise ValueError("snapshot binding mismatch")
            # Closed EvidenceReference envelopes contain references/metadata, not bodies.
            evidence = row[2]["evidence"]["accepted_evidence_refs"]
            evidence = [
                {
                    k: e[k]
                    for k in (
                        "reference_id",
                        "artifact",
                        "consent",
                        "proposition_verification",
                        "source_attestation",
                        "acceptance",
                        "subject",
                        "semantic_independence",
                    )
                    if k in e
                }
                for e in evidence
            ]
            history = [
                {
                    "action": {
                        k: v for k, v in a["action"].items() if k in ACTION_FIELDS
                    },
                    "transitions": [
                        {k: v for k, v in t.items() if k in TRANSITION_FIELDS}
                        for t in a["transitions"]
                    ],
                }
                for a in before
            ]
            manifest = {
                **binding,
                "event_cutoff": row[0],
                "action_history_digest": digest(history),
                "action_history_cutoffs": {
                    a["action"]["action_id"]: max(
                        t["transition_sequence"] for t in a["transitions"]
                    )
                    for a in history
                },
                "report_template_version": TEMPLATE_VERSION,
                "report_input_version": INPUT_VERSION,
                "reconstruction_rules_version": reconstruction["rules_version"],
                "reconstruction_schema_version": reconstruction["schema_version"],
            }
            frozen = ReportInput(
                canonical(
                    {
                        "manifest": manifest,
                        "reconstruction": reconstruction,
                        "evidence": evidence,
                        "action_history": history,
                        "historical_snapshot_invalidations": invalidations,
                        "bank_question": "NOT PROVIDED",
                        "bank_disposition": "NOT PROVIDED",
                        "bank_reasons": "NOT PROVIDED",
                        "human_signoffs": "NOT PROVIDED",
                        "candidate_structure_questions": "NOT ASSESSED",
                    }
                )
            )
            if len(frozen.serialized.encode("utf-8")) > MAX_REPORT_INPUT_BYTES:
                raise ValueError("report input exceeds bounded display size")
        return frozen
    except InvestigatorAppError:
        raise
    except Exception as exc:
        raise InvestigatorAppError(
            409,
            "REPORT_UNAVAILABLE",
            "Current consistent report unavailable; refresh after resolving stale evidence or concurrent changes",
        ) from exc


def render(frozen):
    """Pure deterministic templates over one frozen input; no I/O or arithmetic."""
    record = frozen.record
    r = record["reconstruction"]
    manifest = {**record["manifest"], "report_input_digest": digest(record)}
    actions = []
    accepted_refs = {e["reference_id"] for e in record["evidence"]}
    newly_supported = []
    for item in record["action_history"]:
        action, transitions = item["action"], item["transitions"]
        last = transitions[-1]
        actions.append(
            {
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "rationale": action["analyst_rationale"],
                "status": last["to_status"],
                "reason": last.get("reason_code"),
                "reason_detail": last.get("reason_detail"),
                "outcome_notice": "Administrative history; not evidence truth",
            }
        )
        for t in transitions:
            if t["to_status"] == "EVIDENCE_ACCEPTED":
                for ref in t.get("evidence_references", []):
                    if ref in accepted_refs:
                        newly_supported.extend(
                            x
                            for x in record["evidence"]
                            if x["reference_id"] == ref and x not in newly_supported
                        )
    brief = {
        "manifest": manifest,
        "notice": NOTICE,
        **{
            k: record[k]
            for k in (
                "bank_question",
                "bank_disposition",
                "bank_reasons",
                "candidate_structure_questions",
                "human_signoffs",
            )
        },
        "verified_observations": r["observed_values"],
        "merchant_claims": r["claimed_values"],
        "arithmetic_derivations": r["derived_values"],
        "unknowns": r["unresolved_quantities"],
        "phase3_unknowns": r["phase3_unknowns"],
        "reconciliation_disagreements": r["contradictions_carried_forward"],
        "coverage": r["coverage_diagnostics"],
        "human_actions": actions,
        "newly_supported_evidence": newly_supported,
        "newly_supported_notice": "Current usable references linked to accepted human-action outcomes. Verification applies only to each reference's proposition and verification status; attributed claims remain claims, not independently established truth.",
        "next_action": "See recorded human action status/reason; no automated recommendation"
        if actions
        else "NOT PROVIDED",
        "limitations": "Bank inflows are not total revenue. Complete bank-account coverage is not channel completeness. Unknown costs/debt are not zero. Arithmetic difference is not fraud or proof of a false claim.",
    }
    annex = {
        "manifest": manifest,
        "notice": NOTICE,
        **{
            k: record[k]
            for k in (
                "reconstruction",
                "evidence",
                "action_history",
                "human_signoffs",
                "historical_snapshot_invalidations",
            )
        },
        "eligibility": "Evidence accepted as usable through the current Phase 3/4 boundary AS OF checked_at; not continuing authority",
        "corrections": "Supersession/lineage metadata appears in evidence references where recorded. Historical snapshot invalidations are audit metadata, not renewed authority. No current snapshot invalidation passed the boundary; no inference about unrecorded corrections.",
    }
    return {
        "manifest": manifest,
        "brief": brief,
        "annex": annex,
        "printable_html": {
            "brief": render_html("Analyst Brief", brief),
            "annex": render_html("Audit Annex", annex),
        },
    }


def render_html(title, content):
    if title == "Analyst Brief":
        return _brief_html(content)
    sections = "".join(
        "<section><h2>"
        + html.escape(k.replace("_", " "))
        + "</h2><pre>"
        + html.escape(json.dumps(v, ensure_ascii=False, indent=2))
        + "</pre></section>"
        for k, v in content.items()
    )
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='referrer' content='no-referrer'><title>"
        + html.escape(title)
        + "</title><style>body{font:14px system-ui;max-width:960px;margin:2rem auto;padding:1rem;color:#17231d}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}h2{text-transform:capitalize;font-size:1.1rem}section{border-bottom:1px solid #ccc;padding:.5rem} @media print{body{margin:0}h2{break-after:avoid}}</style><h1>"
        + html.escape(title)
        + "</h1>"
        + sections
        + "</html>"
    )


def _brief_html(brief):
    """Concise human-facing view; full lineage is in the paired annex/JSON."""
    esc = lambda value: html.escape(str(value))
    m = brief["manifest"]

    def listing(items):
        return "<ul>" + "".join("<li>" + esc(x) + "</li>" for x in items) + "</ul>"

    sections = [
        (
            "Case and authorization",
            listing(
                [
                    "SYNTHETIC DEVELOPMENT",
                    "Case: " + m["case_id"],
                    "AS OF: " + m["checked_at"],
                    NOTICE,
                ]
            ),
        ),
        (
            "Original bank information",
            listing(
                [
                    "Question: " + brief["bank_question"],
                    "Disposition: " + brief["bank_disposition"],
                    "Reasons: " + brief["bank_reasons"],
                ]
            ),
        ),
    ]
    for title, key in (
        ("Verified observations — not business-total revenue", "verified_observations"),
        ("Merchant claims — not verified observations", "merchant_claims"),
        ("Arithmetic only — not missing revenue or fraud", "arithmetic_derivations"),
    ):
        sections.append(
            (
                title,
                listing(
                    [
                        f"{v['quantity']}: {v['value']} {v['unit']} ({v['period_start']} to {v['period_end']}); scope {v['dimensional_scope']}; rule {v['rule_id']}"
                        + (
                            "; " + "; ".join(v.get("assumptions", []))
                            if v.get("assumptions")
                            else ""
                        )
                        for v in brief[key]
                    ]
                )
                or "NOT PROVIDED",
            )
        )
    sections.extend(
        [
            (
                "Coverage",
                listing(
                    [x["coverage_type"] + ": " + x["status"] for x in brief["coverage"]]
                ),
            ),
            (
                "Unknowns",
                listing(
                    [
                        x["quantity"] + ": UNKNOWN — " + x["why_unresolved"]
                        for x in brief["unknowns"]
                    ]
                ),
            ),
            (
                "Reconciliation disagreements",
                listing(
                    [
                        x["contradiction_type"] + " · " + x["rule_id"]
                        for x in brief["reconciliation_disagreements"]
                    ]
                ),
            ),
            (
                "Other unresolved questions",
                listing(
                    [
                        x["question"] + " — " + x["why_unresolved"]
                        for x in brief["phase3_unknowns"]
                    ]
                ),
            ),
            (
                "Newly established during investigation",
                listing(
                    [
                        e["proposition_verification"]["proposition_type"]
                        + " = "
                        + e["proposition_verification"]["proposition_value"]
                        + " · reference "
                        + e["reference_id"]
                        for e in brief["newly_supported_evidence"]
                    ]
                )
                if brief["newly_supported_evidence"]
                else "None linked to accepted action outcomes in this capture.",
            ),
            (
                "Human-selected actions and outcomes",
                listing(
                    [
                        x["action_type"]
                        + " · "
                        + x["status"]
                        + " · "
                        + x["rationale"]
                        + " · "
                        + str(x["reason"] or "No terminal reason recorded")
                        + " · "
                        + str(x["reason_detail"] or "")
                        for x in brief["human_actions"]
                    ]
                )
                if brief["human_actions"]
                else "NOT PROVIDED",
            ),
            (
                "Next action / limitations",
                listing(
                    [
                        brief["next_action"],
                        brief["limitations"],
                        "Structure questions: NOT ASSESSED",
                        "Human sign-offs: NOT PROVIDED",
                    ]
                ),
            ),
            (
                "Reproducibility",
                listing(
                    [
                        "Snapshot: " + m["snapshot_id"],
                        "Snapshot digest: " + m["snapshot_digest"],
                        "Report input digest: " + m["report_input_digest"],
                        "Event cutoff: " + str(m["event_cutoff"]),
                        "Action history digest: " + m["action_history_digest"],
                        "Template: " + TEMPLATE_VERSION,
                        "Full source/rule bindings: paired Audit Annex and JSON.",
                    ]
                ),
            ),
        ]
    )
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Analyst Brief</title><style>body{font:14px system-ui;max-width:960px;margin:1rem auto;padding:1rem;color:#17231d}h2{font-size:1rem;border-bottom:1px solid #ccc}li{margin:.25rem 0;overflow-wrap:anywhere}h2{break-after:avoid}@media print{body{margin:0}}</style><h1>Analyst Brief</h1>"
        + "".join(
            "<section><h2>" + esc(title) + "</h2>" + body + "</section>"
            for title, body in sections
        )
        + "</html>"
    )
