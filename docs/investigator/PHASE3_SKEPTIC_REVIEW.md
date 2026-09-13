# Phase 3 adversarial skeptic review

## Review metadata

- Review: frozen first Phase 3 kernel and transaction boundary.
- Reviewer: primary agent applying `olin-adversarial-skeptic`; implementation was
  delegated. Review recorded before reading either specialist review. A third
  fresh review-agent spawn was rejected by the tool's thread limit. The primary
  agent had implementation oversight, so this is not fully independent of design.
- Date: 2026-09-12.
- Repository: `codex/investigator-v1`, base
  `1bf225eef5189f9da81189d294d43fb32402dd1d`, uncommitted Phase 3 working tree.
- Mode: read-only review; reproductions used synthetic fixtures.
- Files: `olin/investigator/claims.py`, `evidence_boundary.py`,
  `test_investigator_phase3_claims.py`, `test_investigator_postgres_evidence.py`,
  Phase 2.5/3 architecture documents and review schema.

## Executive judgment

- Decision: no-go on the initially reviewed version, pending fixes below.
- Confidence: high for reproduced defects; medium for interpretation risks.
- Uncertainty: no outcome evidence validates the threshold or explanation utility;
  PostgreSQL 16 execution was still pending at review time.
- Material dissent: deterministic output and "missing evidence" language are not
  yet reliable for all supported combinations, despite passing initial tests.

## Findings

### S1: same-proposition numeric comparison depends on ambient decimal context

- Finding: `_material_numeric_disagreement` computes `abs` and the denominator
  outside its explicit decimal context. A supported pair with fractional amounts
  raises `decimal.Inexact` under caller precision 6 with the Inexact trap enabled.
- Evidence: synthetic values `260000.123456789` and `118000.123456789` for
  `monthly_revenue`; default context succeeds, altered context raises Inexact.
- Severity: high. Confidence: high.
- Assumptions: Python callers may alter their thread-local decimal context.
- Contradictions: the existing decimal-context test uses whole-number values and
  the cross-proposition path, so it passes while this path fails.
- Impact: violates deterministic, closed synchronous result contract.
- Recommended next check: move every arithmetic operation into the fixed context;
  test fractional same-type values under low precision and enabled traps.

### S2: reconciliation unknown can contradict available verification

- Finding: adding an exact verified `monthly_revenue=260000` proposition to the
  target case still emits an UNKNOWN saying evidence does not verify remaining
  claimed revenue. The kernel did not consider that exact verification when
  wording the reconciliation unknown.
- Evidence: `assess((merchant_claim(), fact(), fact(reference_id=102,
  proposition_type='monthly_revenue', proposition_value='260000')))`, inspected
  `verified_facts` and `unknowns[].why_unresolved`.
- Severity: high. Confidence: high.
- Assumptions: a snapshot can legitimately contain revenue verification and
  bank-visible inflow verification together.
- Contradictions: the result itself contains the matching verified revenue.
- Impact: invents missing proof and overstates uncertainty; an analyst could be
  sent to seek evidence already available.
- Recommended next check: distinguish unknown channel reconciliation from absent
  proposition verification, include all relevant evidence, and add this fixture.

### S3: bank-visible scope is too coarse for same-type conflicts

- Finding: `_same_supported_interpretation` treats all `bank_visible_inflows`
  with the same business subject/period/unit as compatible. `BANK_VISIBLE` does
  not identify which financial accounts are covered.
- Evidence: `Proposition`, `_scope`, and `_same_supported_interpretation` have no
  account-set dimension. Phase 2 references bind the case subject, not an explicit
  bank-account coverage set in these fields.
- Severity: high. Confidence: medium.
- Assumptions: separate original bank sources can cover different accounts.
- Contradictions: different amounts across account sets are compatible, even
  when their reference lineages differ.
- Impact: false contradictions from incompletely defined scope.
- Recommended next check: fail closed for same-type bank comparisons until scope
  is authoritative, or supply a demonstrably existing sealed account-scope
  contract. Keep the explicitly cross-scope reconciliation example distinct.

### S4: useful classification is not demonstrated underwriting improvement

- Finding: fixed 20% gap and explanation families are engineering policy,
  not validated economic materiality, calibrated risk, or evidence of lift.
- Evidence: rules constant, hypothesis-only explanation statuses, no outcome
  dataset or experimental comparison introduced by this change.
- Severity: informational. Confidence: high.
- Assumptions: this remains a foundation rather than production credit authority.
- Contradictions: none; the architecture document acknowledges this limit.
- Impact: easily copied rules may still improve representation; they do not
  establish defensibility, approval lift, loss reduction, or analyst utility.
- Recommended next check: later measure correct reconciliation identification
  and analyst error versus a plain evidence table. Kill or revise explanations
  if they anchor analysts toward unsupported overstatement conclusions.

## Evidence and monetary integrity

No scoring, monetary terms, money movement, external acquisition, LLM execution,
or explanation voting was found. Claims and hypotheses retain distinct classes;
lineage metadata is preserved without weights. Existing consent/history and
authority checks remain the relevant owner boundaries. S2 affects provenance
completeness and S3 affects evidence interpretation. No new customer-data storage,
proxy feature, retention contract, or consequential decision owner is introduced.
Version bindings support reproducibility subject to S1. Production deployment,
revocation propagation, and an audit trail for persisted assessments are not
proved here; persistence is correctly absent.

## Closing

- Residual strengths: narrow sealed input, explicit rule identifiers, no model
  calls, immutable returned records, and hypotheses visibly separated from facts.
- Open questions: account-scope contract and future evidence-acquisition owner.
- Required owner/action: implementation owner fixes S1-S3, then reruns focused
  tests and the PostgreSQL 16 gate before acceptance.
- Evidence changing judgment: passing the adversarial fixtures above, a closed
  comparison scope, and passing final gates on the reviewed diff.

## Follow-up disposition, 2026-09-12

The primary reviewer re-ran the original adversarial probes on the revised
implementation after the PostgreSQL-required full suite passed 326 tests without
skips. The initial findings above are retained as the history of the first review.

- S1 resolved: fractional same-proposition comparisons produced identical
  canonical bytes with precision 6 and the Inexact trap enabled. Arithmetic now
  stays inside the fixed context and compares the gap against the threshold
  product, avoiding ratio-rounding at the boundary.
- S2 resolved: the target plus exact verified revenue now acknowledges that
  verification in its reconciliation UNKNOWN and includes the supporting reference.
  The final Credit Scientist follow-up also removed `MERCHANT_OVERSTATEMENT`
  from that case's hypotheses; the original unverified-revenue example retains it.
- S3 resolved for version 1: differing bank-visible inflows alone produce no
  same-type contradiction; the missing account-set dimension is not inferred.
  The cross-scope example remains an explicitly bounded reconciliation gap.
- S4 remains a validation limitation: no economic lift or risk calibration has
  been demonstrated. Materiality is now explicitly named for the 20% reconciliation
  threshold, with a machine-readable threshold and denominator identifier.

The fixed wrapper also checks a live identity-bound operation lease and metadata
fingerprint. Tests cover a copied context after success and after failure, direct
activation, modified capability bindings, and deferred returns. Closed assertion
profiles replace artifact-origin inference. Migration `0005` only changes the
existing evidence-input CHECK constraint, uses an atomic transaction and migration
owner, rejects SQL NULL/partial assertion shapes, and adds no table or grant.
The PostgreSQL target exercises actual projection publication, evidence acceptance,
snapshot sealing, and reasoning rather than bypassing them with a Python fixture.

**Revised skeptic judgment: go-with-conditions; confidence high in these bounded
fixes, medium in the rule's eventual usefulness.** Keep the documented v1 scope,
no evidence voting, no persistence of assessments, and no downstream credit
authority. This follow-up is by the primary agent with implementation oversight;
it does not replace the separately requested specialist follow-up reviews.
