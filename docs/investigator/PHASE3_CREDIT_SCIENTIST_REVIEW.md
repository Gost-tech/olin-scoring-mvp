# Phase 3 Credit Scientist review

## Review metadata

- **Review:** Independent review of Phase 3 proposition, claim, unknown,
  contradiction, independence, and hypothesis semantics
- **Reviewer:** OLIN Credit Scientist agent
- **Date:** 2026-09-12
- **Repository state:** `codex/investigator-v1` at accepted base
  `1bf225eef5189f9da81189d294d43fb32402dd1d`, with the frozen uncommitted
  Phase 3 change set
- **Mode:** Read-only implementation review; this document is the only review
  artifact written
- **Files examined:** `olin/investigator/claims.py`,
  `olin/investigator/evidence.py`, `olin/investigator/evidence_boundary.py`,
  `test_investigator_phase3_claims.py`,
  `test_investigator_postgres_evidence.py`,
  `docs/investigator/PHASE2_5_EVIDENCE_REASONING_READINESS.md`, and
  `docs/investigator/PHASE3_CLAIMS_UNKNOWNS_CONTRADICTIONS.md`
- **Checks run:** `python3 -m unittest -q test_investigator_phase3_claims`
  (18 tests passed), `git diff --check` (passed), and two direct deterministic
  probes of unknown-independence and same-lineage contradiction behavior

## Executive judgment

- **Decision:** `go-with-conditions`
- **Confidence:** high
- **Uncertainty:** The 20% reconciliation threshold has only synthetic boundary
  evidence. No adjudicated reconciliation sample establishes its investigation
  precision, review burden, stability across merchant types, or economic value.
  `bank_visible_inflows` also lacks an explicit account/channel coverage
  dimension, so the practical compatibility of visible inflows with total
  business revenue remains underspecified.
- **Material dissent:** Phase 3 must not use distinct lineage identifiers as a
  substitute for authority-verified independence, and the revenue rule must not
  emit the same contradiction from circular/same-lineage evidence without an
  explicit rule for that dependence. These conditions can change which cases
  are surfaced as contradictions.

## Findings

### Finding: Contradiction rules do not consistently preserve independence uncertainty

- **Finding:** Same-proposition contradiction eligibility treats disjoint
  `ORIGINAL` lineage IDs as sufficient even when both inputs are
  `INDEPENDENCE_UNKNOWN`. The revenue reconciliation rule does not consult
  lineage or independence and emits a contradiction when the claim and fact
  share one lineage. This does not inflate a numeric support count, but it uses
  dependence metadata inconsistently when deciding whether a contradiction
  exists.
- **Evidence:** `olin/investigator/claims.py:428-445` implements
  `_has_distinct_original_lineage` without checking `INDEPENDENT_VERIFIED`;
  `olin/investigator/claims.py:610-619` and `665-673` use that predicate for
  same-proposition conflicts; `olin/investigator/claims.py:538-557` applies the
  revenue rule without a lineage condition. A direct probe produced
  `MATERIAL_DISAGREEMENT_SAME_PROPOSITION` from two
  `INDEPENDENCE_UNKNOWN` references and produced the revenue disagreement from
  a claim and fact with the same `semantic_lineage_id`. The Phase 2.5 contract
  states that unknown independence is neutral and that verified independence
  requires a server-side attestation
  (`docs/investigator/PHASE2_5_EVIDENCE_REASONING_READINESS.md:52-67`).
- **Severity:** high
- **Confidence:** high
- **Assumptions:** Lineage and independence have the meanings established in
  Phase 2.5, and contradiction eligibility is a material interpretation of
  those fields even though it is not evidence voting.
- **Contradictions:** The output retains each reference's actual independence
  status, and grouped references are not assigned a corroboration weight.
  Those are strong controls, but they do not remove the rule-eligibility
  inconsistency.
- **Impact:** Circular or dependence-unknown records can create an apparently
  stronger investigation finding than the authority metadata warrants. A later
  user could treat that finding as independent conflict and escalate a merchant
  without sufficient basis.
- **Recommended next check:** Add explicit fixtures for (a) same lineage,
  (b) derived/correction lineage, (c) disjoint lineages with independence
  unknown, and (d) independently verified lineages. Specify separately whether
  each case is a record inconsistency, a reconciliation unknown, or an eligible
  contradiction. Require attested independence wherever the rule's conclusion
  depends on independence; never infer it from different lineage IDs.

### Finding: Revenue compatibility lacks account and channel coverage identity

- **Finding:** The initial rule conservatively preserves `monthly_revenue` and
  `bank_visible_inflows` as different propositions, but its proposition model
  gives bank-visible inflows only the broad scope `BANK_VISIBLE`. It cannot
  identify which accounts, processors, or channels the 118,000 MXN observation
  covers. Subject, period, schema version, and currency equality therefore do
  not by themselves establish comparable economic coverage.
- **Evidence:** `Proposition` contains type, subject, value, unit, period, and a
  three-value dimensional scope (`olin/investigator/claims.py:53-56` and
  `72-93`). `_scope` derives scope only from proposition type
  (`olin/investigator/claims.py:299-304`), while `_compatible_revenue_pair`
  checks type, version, subject, unit, and exact period but no account/channel
  coverage (`olin/investigator/claims.py:378-388`). The emitted unknown correctly
  asks for remaining channels and scope/classification reconciliation
  (`olin/investigator/claims.py:574-590`). The design note explicitly says the
  kernel does not infer account coverage
  (`docs/investigator/PHASE3_CLAIMS_UNKNOWNS_CONTRADICTIONS.md:49-51`).
- **Severity:** medium
- **Confidence:** high
- **Assumptions:** `bank_visible_inflows` may cover fewer than all accounts or
  settlement channels; no external proposition registry reviewed here gives
  the type a stricter coverage definition.
- **Contradictions:** The finding is named a material disagreement rather than
  proof that revenue is false, and the deterministic explanation families
  explicitly include cash, another account, and platform settlements. This
  substantially limits overclaiming.
- **Impact:** The first rule is suitable as a reconciliation prompt but can be
  misread as a contradiction between two mutually exclusive facts. Partial
  visibility is a normal coverage limitation and must remain uncertainty, not
  adverse evidence.
- **Recommended next check:** Define the versioned meaning of
  `bank_visible_inflows`, including covered account/channel set and gross/net
  basis, or constrain the contradiction type to state explicitly that it is a
  coverage-limited reconciliation disagreement. Test one-account versus
  all-account observations and processor settlements before broadening the
  rule.

### Finding: Generic MATERIAL can be mistaken for credit materiality

- **Finding:** The 20% threshold is explicit, deterministic, and documented as
  an unvalidated engineering policy, but the output reduces its meaning to the
  generic enum value `MATERIAL`. The canonical result does not carry the ratio,
  threshold, denominator, or a named `RECONCILIATION` materiality basis.
- **Evidence:** `MATERIAL_RECONCILIATION_GAP_RATIO` is 0.20 and expressly not a
  credit-risk threshold (`olin/investigator/claims.py:33-41`). The revenue rule
  divides the positive gap by claimed revenue (`olin/investigator/claims.py:544-553`)
  and emits `Materiality.MATERIAL` (`olin/investigator/claims.py:561-590`). The
  design note calls usefulness unvalidated
  (`docs/investigator/PHASE3_CLAIMS_UNKNOWNS_CONTRADICTIONS.md:40-43`).
- **Severity:** medium
- **Confidence:** high
- **Assumptions:** Later consumers may receive canonical results without the
  design note and may map generic materiality into investigation priority or
  credit treatment.
- **Contradictions:** The kernel contains no score, PD, approval, pricing,
  facility, fraud, or action ranking, and the rule ID/version permits audit.
- **Impact:** A downstream consumer could silently convert an investigation
  threshold into adverse credit significance. That would violate unknown-is-not-
  bad and introduce an unvalidated feature into a consequential decision.
- **Recommended next check:** Make the basis machine-readable, for example
  `MATERIAL_RECONCILIATION_GAP`, and include the threshold/denominator rule in
  the rule contract or output. Add a boundary test proving downstream-neutral
  semantics. Do not calibrate this as a credit threshold in Phase 3.

### Finding: Epistemic separation and proposition-specific verification are strong

- **Finding:** Claims do not self-promote, verified facts require the exact
  Phase 2 class/status pair, unsupported claims create neutral unknowns, and
  possible explanations remain deterministic hypotheses. The 118,000 MXN bank
  observation is not widened into 118,000 MXN business revenue.
- **Evidence:** Fact creation requires `EvidenceClass.VERIFIED_FACT` and
  `VerificationStatus.VERIFIED_FOR_PROPOSITION`
  (`olin/investigator/claims.py:460-479`). Merchant and external classes map to
  distinct claim types with `CLAIM_ONLY` confidence
  (`olin/investigator/claims.py:480-517`). Unmatched claims receive
  `NOT_CLASSIFIED` unknowns (`olin/investigator/claims.py:725-759`). Explanation
  families are closed constants with `HYPOTHETICAL` confidence and
  `HYPOTHESIS` status (`olin/investigator/claims.py:531-537` and `593-603`).
  Focused tests cover the target case, claim retention, proposition narrowing,
  incompatible period/unit/schema/type, hypothetical explanations, and absence
  of decision/fraud fields; all 18 passed.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** The Phase 2.5 capability contains only current, usable,
  authority-derived references, as enforced by the reviewed boundary.
- **Contradictions:** `verification_status` has only `UNVERIFIED` and
  `VERIFIED_FOR_PROPOSITION`; it does not encode an explicit failed-verification
  event. The documentation's statement that failed verification remains
  uncertainty is therefore doctrinal rather than directly exercised by a
  distinct Phase 3 input state.
- **Impact:** The current kernel does not create an adverse label, fraud
  conclusion, or credit decision from missing or unverified evidence.
- **Recommended next check:** Add a focused neutral-outcome test if Phase 2 later
  exposes an authoritative failed-verification state. Until then, do not infer
  a failure reason from `UNVERIFIED` or from absence.

### Finding: Period, unit, schema, and proposition-type handling is conservative

- **Finding:** Comparisons require exact unit and exact period equality, support
  only proposition schema version 1, and reject unspecified proposition meaning.
  There is no currency conversion, period normalization, gross/net conversion,
  or comparison of unsupported types.
- **Evidence:** Compatibility predicates are at
  `olin/investigator/claims.py:378-407`; numeric disagreement is bounded and
  finite (`olin/investigator/claims.py:366-425`). Tests at
  `test_investigator_phase3_claims.py:221-267` cover different periods,
  currencies, schema versions, types, unspecified scope, and sub-threshold
  differences.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** Exact periods are intentionally required in version 1; no
  overlap or calendar-month normalization is expected.
- **Contradictions:** Currency is represented in the generic `unit` string, and
  gross/net or account coverage is represented only indirectly by proposition
  type. This is safe because unknown types do not compare, but it limits the
  model's useful domain.
- **Impact:** The implementation favors false negatives over false
  contradictions outside its narrow supported interpretation, which is the
  appropriate initial credit-safety posture.
- **Recommended next check:** Keep overlap, currency conversion, gross/net
  normalization, and scope expansion out of this rules version. Add explicit
  schema definitions and boundary fixtures before any such rule is introduced.

## Feature thesis

- **Hypothesis:** Surfacing a versioned reconciliation unknown when claimed
  monthly revenue exceeds same-period bank-visible inflows by at least 20% helps
  investigators identify unresolved revenue coverage without turning missing
  visibility into adverse credit evidence.
- **Evidence source and provenance:** One synthetic deterministic case (260,000
  MXN claimed; 118,000 MXN bank-visible), versioned code and focused unit tests.
  There is no production or adjudicated-case evidence.
- **Expected economic value:** Unknown. Plausible value is lower reconciliation
  omission and clearer evidence requests; no approval lift, loss reduction,
  review-time benefit, or unit-economic effect has been demonstrated.
- **Failure mode:** Partial account coverage, cash-heavy operations, platform
  settlement timing, refunds, taxes, gross/net mismatch, seasonality, or period
  definition differences create frequent alerts with little information gain;
  downstream users treat `MATERIAL` as adverse.
- **Validation method:** On a versioned, consented, representative historical
  sample, have accountable reviewers adjudicate coverage and reconciliation
  outcomes without access to the rule result first. Measure alert precision,
  unresolved-rate reduction, incremental evidence discovered, handling time,
  inter-reviewer agreement, subgroup stability, and false escalation. Any later
  credit-outcome study must be prospective or otherwise control selection,
  reject-inference, leakage, and policy feedback.
- **Kill condition:** Remove or revise the rule if it does not improve resolved
  evidence per unit of review time, if false escalation is operationally
  material, if performance is unstable across legitimate cash/channel patterns,
  or if users systematically convert the alert into adverse credit treatment.

## Evidence and monetary integrity checks

- **Authoritative provenance and verification:** Sound for fact promotion;
  condition required for contradiction use of independence metadata.
- **Unknown-versus-bad treatment:** Sound. Unknowns are unresolved or
  not-classified and no adverse credit class is emitted.
- **Reason-code and consent-history preservation:** Existing authority references
  and currentness checks are preserved. Phase 3 does not create credit reason
  codes or rewrite consent history.
- **Deterministic scoring boundaries:** Sound. The threshold is a deterministic
  reconciliation rule, not a score; its generic materiality label needs clearer
  machine-readable scope.
- **Approved amount, facility, tenor, pricing, repayment schedule, and
  outstanding balance:** Untouched; no competing monetary truth is introduced.
- **LLM/agent authority boundaries:** Sound. No model/provider invocation or
  autonomous decision path exists.
- **Reproducibility and version provenance:** Sound for the current kernel:
  canonical output binds rules/schema, snapshot, authority, and evidence-state
  versions/digests, and focused determinism tests pass.
- **Evidence-type classification:** Sound for fact/claim/unknown/hypothesis
  separation; independence use in contradiction eligibility requires correction.
- **Fairness and proxy risk:** No protected or geographic feature is introduced.
  Future validation must check alert burden across legitimate business models,
  especially cash-heavy and platform-mediated merchants.
- **Accountable owner:** Not yet identified for consequential use. Acceptable for
  this in-memory foundation; required before operational or credit use.
- **Data lifecycle controls:** No persistence or new acquisition is introduced;
  the result remains transaction-current at creation and historical afterward.
- **Audit integrity:** Rule IDs, provenance, and version bindings are present.
  The exact reconciliation calculation basis should be more explicit in the
  canonical contract.
- **Production-boundary compliance:** Sound in reviewed scope. The kernel does
  not approve, decline, price, structure, disburse, persist, or alter evidence.

## Closing

- **Open questions:** What exact account/channel set does
  `bank_visible_inflows` version 1 cover? Is a contradiction intended to mean a
  logical incompatibility, a record inconsistency, or a material reconciliation
  gap? When is independence required for each meaning? Who owns and can revise
  the 20% investigation threshold?
- **Required owner and next action:** The Phase 3 rule owner should define the
  contradiction/independence matrix, fix the same-lineage revenue case, preserve
  `INDEPENDENCE_UNKNOWN` without inferred independence, and make reconciliation
  materiality scope explicit. The evidence/proposition owner should define bank
  coverage semantics. Re-run the focused suite and this semantic review after
  those fixtures pass.
- **Evidence that would change the judgment:** A rule contract and tests proving
  correct behavior for same-lineage, derived/correction, unknown-independence,
  and attested-independent inputs would clear the high condition. A versioned
  account/channel coverage definition and machine-readable reconciliation
  materiality basis would clear the medium conditions. Conversely, any path
  that maps unknowns, contradictions, or hypotheses directly to score,
  approval, fraud, pricing, facility, or money movement would change the
  judgment to `no-go`.

**Decision: GO-WITH-CONDITIONS.** Do not treat this as evidence of credit-model
lift or begin Phase 4. The deterministic Phase 3 foundation is suitable to
continue toward CI after the independence/lineage condition is resolved and the
scope/materiality semantics are made explicit.

## Follow-up disposition after frozen revisions

- **Date:** 2026-09-12
- **Current decision:** `go`
- **Confidence:** high
- **Scope of disposition:** Re-review of the conditions above against the final
  frozen Phase 3 code, tests, migration, and Phase 3 design note. The historical
  findings above are preserved to show what changed.
- **Validation:** `python3 -m unittest -q test_investigator_phase3_claims` now
  passes 30 tests. `git diff --check` passes. Direct probes covered distinct
  lineages with unknown independence, one shared lineage, a shared economic
  event, a shared upstream issuer, same-proposition disagreement, and an exact
  verified monthly-revenue fact.

### Disposition: Independence and record disagreement

- **Finding disposition:** The former high condition is resolved for this
  bounded rules version.
- **Evidence:** Cross-scope revenue reconciliation now requires original,
  disjoint lineages and rejects a shared semantic lineage, shared known economic
  event, shared upstream issuer, copy, or correction
  (`olin/investigator/claims.py:456-488` and `591-595`). Tests exercise these
  cases (`test_investigator_phase3_claims.py:357-414`). Direct probes produced no
  contradiction for same lineage, shared event, or shared upstream issuer and
  retained a neutral `P3-UNKNOWN-CLAIM-001` unknown. For distinct original
  lineages, each provenance record remains explicitly
  `INDEPENDENCE_UNKNOWN`.
- **Evidence-weighted judgment:** A material disagreement between two current,
  distinct records may validly be surfaced while independence remains unknown.
  The conclusion is that the records disagree under the named deterministic
  comparison; it is not a conclusion that the sources independently corroborate
  either value. Independence would be required to claim an independent support
  count or corroboration weight, neither of which this result contains. Requiring
  `INDEPENDENT_VERIFIED` merely to report a record conflict would hide useful
  inconsistencies and incorrectly conflate independence with logical
  compatibility.
- **Residual limitation:** Same-proposition disagreements require disjoint
  original lineages but do not require independent-source attestation. This is
  acceptable because their output retains the underlying unknown independence,
  assigns no vote or weight, asks which value is correct, and keeps both source
  records in provenance. A later display or policy consumer must not relabel the
  finding as independently corroborated conflict.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** Phase 2.5 continues to exclude superseded evidence and to
  enforce authority-owned lineage fields. No downstream consumer derives a
  support count from the number of provenance references.
- **Contradictions:** Different lineage IDs still do not prove independent
  sources. The revised implementation does not say that they do; it uses them
  only to establish distinct current records and preserves the authoritative
  independence state unchanged.
- **Recommended next check:** When a real consumer is introduced, test its label
  and rendering so `INDEPENDENCE_UNKNOWN` remains visible and the contradiction
  cannot be presented as independently corroborated.

### Disposition: Scope and reconciliation materiality

- **Finding disposition:** The former medium conditions are resolved for the
  Phase 3 CI candidate. Missing account-set identity remains an explicit v1
  limitation rather than a hidden assumption.
- **Evidence:** `Materiality` now names
  `RECONCILIATION_GAP_AT_LEAST_20_PERCENT`; each contradiction carries canonical
  `materiality_threshold_ratio` and `materiality_denominator`
  (`olin/investigator/claims.py:61-63` and `205-229`). The cross-scope rule uses
  claimed revenue as denominator, while same-proposition comparisons use the
  larger absolute value. Tests assert the fields and exact boundary behavior
  (`test_investigator_phase3_claims.py:227-239` and `416-446`). Separate
  bank-visible facts are no longer compared as the same proposition because
  account-set coverage is not sealed (`olin/investigator/claims.py:421-435` and
  `test_investigator_phase3_claims.py:342-355`). The design note identifies the
  first rule as a cross-scope reconciliation disagreement and denies credit
  materiality, account-coverage inference, and currency/gross-net normalization.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** The initial 20% value remains an investigation surfacing
  policy only and is not consumed as score, adverse reason, approval policy, or
  investigator action priority.
- **Contradictions:** The proposition model still cannot compare two bank
  observations by account set. Suppressing that comparison is the correct
  conservative behavior until Phase 2 seals the missing dimension.
- **Recommended next check:** Keep account-set comparisons disabled. Validate
  the 20% rule on adjudicated reconciliation cases before operational use, using
  the feature thesis and kill condition above.

### Disposition: Assertion reachability and provenance

- **Finding disposition:** Closed claims are now reachable through the durable
  path without treating an upload or extracted text as an assertion.
- **Evidence:** The kernel accepts only complete `UNVERIFIED` proposition
  metadata under exact `merchant_assertion_recorded:v1` or
  `external_assertion_recorded:v1` profiles
  (`olin/investigator/claims.py:342-355` and `522-547`). Migration `0005` adds
  only those closed alternatives while preserving the verified-fact and legacy
  no-proposition clauses
  (`db/migrations/0005_investigator_phase3_assertion_metadata.sql:30-82`). The
  real PostgreSQL test expects the sealed result to retain 118,000 MXN as a fact,
  260,000 MXN as a claim, one unknown, one contradiction, and five hypotheses
  (`test_investigator_postgres_evidence.py:2329-2354`); adjacent tests reject
  unversioned, incomplete, cross-class, and verified-fact-forgery profiles.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** The controlled PostgreSQL 16 run reported by the implementation
  gate used migrations `0001` through `0005`; this reviewer independently ran
  the focused in-memory suite but did not repeat that full database run.
- **Contradictions:** `assertion_timestamp` remains `None`. This accurately avoids
  substituting evidence observation time for an assertion time the sealed input
  does not contain.
- **Recommended next check:** Preserve the closed profile/version allowlist and
  add a distinct authoritative assertion timestamp only through a future
  versioned evidence-input contract.

### Disposition: Verified revenue and bounded hypotheses

- **Finding disposition:** A follow-up medium issue found during re-review is
  resolved.
- **Evidence:** When exact proposition-specific evidence verifies the claimed
  260,000 MXN monthly revenue, the reconciliation unknown now says that overall
  revenue is verified and asks only for channel/account attribution. The kernel
  also removes `MERCHANT_OVERSTATEMENT` from that case while retaining the four
  compatible explanation families (`olin/investigator/claims.py:611-682`). The
  regression at `test_investigator_phase3_claims.py:741-769` checks both the
  wording/provenance change and hypothesis suppression. A direct probe confirmed
  the result contains verified facts for bank-visible inflows and monthly
  revenue, one reconciliation unknown, and no overstatement hypothesis.
- **Severity:** informational
- **Confidence:** high
- **Assumptions:** The exact monthly-revenue verified fact has the same subject,
  period, unit, schema version, value, and business-total scope as the claim.
- **Contradictions:** Other explanation families remain hypothetical because the
  verified total does not attribute revenue to bank, cash, processor, or other
  account channels.
- **Recommended next check:** Add no ranking. If future rules challenge an
  authoritative fact, represent that as an explicit conflicting verified
  proposition and reconciliation unknown rather than reviving an incompatible
  merchant-overstatement hypothesis.

### Current closing judgment

- **Open questions:** The empirical usefulness of 20% remains unknown, as do
  account/channel coverage and performance across cash-heavy or platform-heavy
  merchants. These are bounded validation limits and do not block this
  deterministic Phase 3 foundation.
- **Required owner and next action:** The Phase 3 rule owner should take the
  frozen implementation through CI while preserving its in-memory, non-credit,
  non-persistent boundary. Before operational use, an accountable investigation
  owner must validate alert usefulness and false escalation on representative
  adjudicated cases.
- **Evidence that would change the judgment:** Any downstream conversion of
  provenance count into independent support, any adverse treatment of unknowns,
  or any direct mapping from contradiction/materiality to score, fraud, approval,
  pricing, facility, or money movement would change this judgment to `no-go`.

**Current decision: GO.** No remaining proposition-semantic blocker prevents the
frozen implementation from becoming a Phase 3 CI candidate. This decision does
not validate the 20% threshold as economically useful and does not authorize
Phase 4 or consequential credit use.
