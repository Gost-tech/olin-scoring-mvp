# Phase 5A: bounded human investigation workflow

Phase 5A adds administrative action history around the frozen Phase 3/4
reasoning path. It does not persist `ClaimsAssessment` or
`EconomicReconstruction` and does not grant evidence, consent, credit, provider,
or money authority.

## Components and custody

- `olin.investigator_app` is a separate analyst entry point. A named analyst is
  bound server-side to one tenant and receives a short-lived signed session.
- The reasoning connection retains the exact Phase 3/4 PostgreSQL runtime
  custody. Every refresh finds a current snapshot and reruns the reviewed
  `reconstruct_economics_current` path. The response is `no-store` and the
  transaction is complete before display.
- The action connection is a separate tenant login with only the non-login
  `olin_investigator_action_writer` role. It cannot mutate canonical evidence.
- `olin.investigator_synthetic_operator` is loopback-only and development-only.
  It holds fixed synthetic runtime/evidence-authority credentials that are never
  sent to the browser or analyst process. It accepts only three closed fixture
  outcomes and is not an upload endpoint.

## Catalogue and states

Catalogue version `investigator-action-catalogue-1.0` permits:

1. Request a missing account/payment-channel coverage record.
2. Clarify the period and scope of the merchant revenue assertion.

V1 release cleanup removes the fixture amount from the second action's display
question. Catalogue1.0 is retained: this is amount-neutral wording, not a change
to action identifiers, questions, prerequisites, effects or executable semantics.
Migration0006 pins the existing semantic version; no migration/grant change is
needed. Historical selections retain their original wording and selection digest.

The append-only lifecycle is `SELECTED -> REQUESTED -> RESPONSE_RECEIVED`, then
either `EVIDENCE_ACCEPTED`, `COMPLETED_UNRESOLVED`, `STOPPED`, or `ESCALATED`.
This bounded catalogue cannot mark a question resolved: the supported coverage
fixture narrows bank-account coverage but leaves revenue-channel coverage and
sustainable revenue unknown. Accepted evidence may therefore be completed only
as unresolved or escalated. Administrative completion never establishes evidence
truth or question resolution.

Unknown effort and cost are stored as null. Stop/escalation uses a closed reason
set. `SYNTHETIC_DEMO_LIMIT_REACHED` is a development limit, not bank policy.

## Write boundary

Migration `0006` is additive. Action selection stores the selected snapshot and
digest, authority revision/digest, evidence-state digest, assessment digest,
rules/schema versions, catalogue definition, bounded rationale, and the
server-derived database actor/time. The command takes the existing reasoning
advisory fence and rejects a stale snapshot or authority revision. It does not
reuse the consumed Phase 3/4 capability.

Action transitions are append-only, expected-sequence constrained, and
idempotent. The database rejects an `EVIDENCE_ACCEPTED` transition unless every
referenced UUID is absent from the action's immutable selection snapshot,
present in the current canonical snapshot, and matches the action's permitted
proposition and synthetic evidence identity. The application independently
checks the same action-bound delta before recording the administrative outcome.
Both the isolated service login and the authenticated analyst name are retained.
Corrections add history. Concurrent stale transitions fail. Raw evidence bodies
and full reasoning results are not stored.

## Synthetic evidence handoff

The useful fixture commits a proposition-specific
`bank_account_coverage=COMPLETE` record through the existing canonical evidence
projection and `accept_evidence_reference_v2`, creates a new snapshot, and then
reruns Phase 3/4. Revenue-channel coverage and sustainable revenue remain
unknown. The duplicate fixture is recorded as received but unresolved and adds
no canonical support. The unavailable fixture stops with an explicit reason.
The application independently reruns the current Phase 3/4 path and confirms the
returned reference, authority revision, and replacement snapshot before adding
an accepted administrative transition. If snapshot creation is interrupted
after canonical acceptance, an idempotent retry detects the accepted reference
and creates or reuses the missing current snapshot.

A durable `RESPONSE_RECEIVED` records receipt only, not completed processing.
An exact retry resumes the missing outcome from that receipt's sequence without
duplicating receipt or canonical evidence. Accepted retries rerun canonical
currentness and the action-bound evidence delta before completing history;
revocation cannot be bypassed by a receipt. A finalized retry returns the original
response outcome, not an unrelated later action status. Concurrent retries use
the existing idempotency/sequence constraints; an intervening human terminal
transition is not overwritten. No transaction spans operator and action history.

This development operator simulates acquisition. It does not represent a real
bank, provider, merchant response, or production verification.
