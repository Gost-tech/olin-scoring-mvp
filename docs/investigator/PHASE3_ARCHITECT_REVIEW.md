# Phase 3 Chief Architect review

## Review metadata

- **Review:** Phase 3 claims, unknowns, contradictions, and transaction-bound entrypoint
- **Reviewer:** OLIN Chief Architect agent
- **Date:** 2026-09-12
- **Repository state:** `codex/investigator-v1` at accepted HEAD `1bf225eef5189f9da81189d294d43fb32402dd1d`, with the uncommitted Phase 3 working tree reviewed
- **Mode:** Read-only architecture review; only this review record was added
- **Files examined:** `olin/investigator/claims.py`; `olin/investigator/evidence_boundary.py`; `olin/investigator/evidence.py`; `olin/investigator_evidence_adapter.py`; `olin/investigator/__init__.py`; `test_investigator_phase3_claims.py`; the Phase 3 PostgreSQL integration in `test_investigator_postgres_evidence.py`; `docs/investigator/PHASE3_CLAIMS_UNKNOWNS_CONTRADICTIONS.md`; `docs/investigator/PHASE2_5_EVIDENCE_REASONING_READINESS.md`; `docs/investigator/INVESTIGATOR_V1_BLUEPRINT.md`

## Executive judgment

- **Decision:** `no-go`
- **Confidence:** `high`
- **Uncertainty:** This review did not rerun the reported 52-test scoped suite or PostgreSQL CI. Passing those tests would not resolve the two structural blockers below because both follow directly from current code. The authoritative projection can carry unverified proposition metadata, but the inspected PostgreSQL Phase 3 test does not exercise an assertion-bearing record.
- **Material dissent:** The fixed PostgreSQL wrapper is a sound production-shaped path, but the kernel does not mechanically require that path, and it does not distinguish an authority-recorded assertion from other proposition-bearing artifacts. Those gaps conflict with Phase 3 entry conditions and claim semantics.

## Ranked findings

### Finding 1: Phase 3 authorization can be activated outside the approved wrapper

- **Finding:** `assess_claims` authorizes execution from mutable private fields on `ReasoningReadySnapshot`. Python callers can activate an otherwise inactive capability and obtain a `ClaimsAssessment` without the server-derived pre-invocation or final currentness checks. The issuer sentinel and factory are also importable, so issuance is not mechanically confined to `PostgresReasoningSnapshotGate`.
- **Evidence:** `assess_claims` checks only `isinstance`, `_phase3_active`, and non-null `_connection` at `olin/investigator/claims.py:448-453`. `_phase3_active` is set with `object.__setattr__` at `olin/investigator/evidence_boundary.py:292`, and the class is already constructed with `object.__new__` at lines 127-145. `_REASONING_GATE_ISSUER` and `_issue_values` are module-accessible at lines 105-146 and 328. The Phase 3 test imports that issuer at `test_investigator_phase3_claims.py:24-27`. A read-only probe executed `object.__setattr__(capability, "_phase3_active", True); assess_claims(capability)` and returned `ClaimsAssessment 0 1`, where `0` was the connection's currentness-check count.
- **Severity:** `high`
- **Confidence:** `high`
- **Assumptions:** In-process application code and tests are within the boundary that “mechanically enforce” is intended to constrain. Python privacy conventions alone are not an authorization mechanism.
- **Contradictions:** `PostgresReasoningSnapshotGate.assess_claims_current` correctly issues and consumes the capability inside the read-only transaction at `olin/investigator/evidence_boundary.py:668-686`; that supported path does not remove the callable direct path.
- **Impact:** A caller can run Phase 3 over references that were not freshly sealed by the approved wrapper and receive an assessment carrying authoritative-looking snapshot and authority bindings. This undermines provenance and audit meaning even though the result does not move money.
- **Recommended next check:** Add a negative test that uses a real issued but inactive capability, mutates or otherwise bypasses activation, and proves no assessment can be returned without both server currentness checks. Make the fixed gate method the only API that can produce the authoritative assessment envelope; keep any pure-kernel fixture API explicitly unbound and unable to emit that envelope.

### Finding 2: Phase 3 treats every proposition-bearing supplied artifact as a claim

- **Finding:** Phase 3 maps `MERCHANT_SUPPLIED_ARTIFACT` directly to `MERCHANT_CLAIM` and `EXTERNAL_EVIDENCE` directly to `EXTERNAL_CLAIM` whenever proposition fields are present, although those Phase 2 classes describe evidence origin rather than an assertion event. The active PostgreSQL canonical reader can preserve unverified proposition fields, so the problem is over-broad interpretation of sealed metadata, not absence of a production transport.
- **Evidence:** The mapping is at `olin/investigator/claims.py:480-497`, and `assertion_timestamp` is hard-coded to `None` at lines 487-495. Phase 2 defines evidence-origin classes at `olin/investigator/evidence.py:54-59`; `EvidenceReference` has no dedicated claim class or assertion timestamp at lines 576-631. `PostgresCanonicalEvidenceReadPort` reads `evidence_class`, `verification_status`, proposition fields, `verification_method`, `observed_at`, `issuer_id`, and lineage fields from the owner-maintained projection at `olin/investigator_evidence_adapter.py:471-537` and passes them intact into `EvidenceAuthorityResolution` at lines 735-774. Migration `0004` exposes those fields at `db/migrations/0004_investigator_evidence_reasoning_readiness.sql:275-298`. The current PostgreSQL Phase 3 test contains only a verified fact and asserts empty claims at `test_investigator_postgres_evidence.py:2119-2141`; therefore it does not validate claim semantics. `ExistingEvidencePassportReadPort` strips legacy proposition truth, but it is not the active canonical projection reader for this conclusion.
- **Severity:** `high`
- **Confidence:** `high`
- **Assumptions:** `MERCHANT_SUPPLIED_ARTIFACT` can include documents supplied by a merchant without an explicit merchant assertion of every proposition extracted from them; `EXTERNAL_EVIDENCE` likewise does not by itself identify an external claimant.
- **Contradictions:** The synthetic fixture labels `verification_method` as `merchant_assertion_recorded`, which could support a narrow interim assertion rule, but the kernel ignores that field and treats all proposition-bearing merchant artifacts alike. The Phase 3 document says claims preserve asserted meaning; evidence origin alone does not establish that meaning.
- **Impact:** Ordinary merchant-uploaded or external artifacts with extracted proposition metadata can be mislabeled as assertions by the named issuer, producing unsupported claims, unknowns, contradictions, and explanations.
- **Recommended next check:** Without changing SQL or the Phase 2 schema, define a closed Phase 3 assertion-profile allowlist over existing sealed fields: `UNVERIFIED`, the appropriate evidence class, complete proposition identity, an exact authority-owned assertion-recording method, and a nonempty issuer. Leave assertion time `None` unless a dedicated authoritative field exists. Reject all other supplied artifacts from claim classification. Add negative tests for proposition-bearing uploads with extraction/document methods and a PostgreSQL end-to-end fixture for each allowed assertion profile. A later schema version should replace this compatibility profile with explicit claim class and assertion time.

### Finding 3: The revenue reconciliation rule does not exclude circular lineage

- **Finding:** The cross-scope revenue rule emits a material contradiction without checking semantic lineage or independence. A merchant claim and bank-visible fact marked with the same semantic lineage produce the contradiction despite the requirement to account for duplicated or circular evidence.
- **Evidence:** `_compatible_revenue_pair` checks type, schema, subject, unit, and exact period only at `olin/investigator/claims.py:378-388`. The rule applies it directly at lines 538-573. The distinct-original-lineage guard exists for same-proposition rules at lines 428-445, 610-619, and 665-673, but not for revenue reconciliation. A read-only synthetic probe with both references assigned `semantic_lineage_id="shared"` returned `MATERIAL_DISAGREEMENT_DECLARED_REVENUE_EXCEEDS_BANK_VISIBLE_INFLOWS`.
- **Severity:** `medium`
- **Confidence:** `high`
- **Assumptions:** Same-lineage metadata means the two states may share an underlying semantic source and therefore cannot automatically support an evidence-vs-claim disagreement without an explicit compatibility rule.
- **Contradictions:** The kernel does not count references or increase confidence, and it correctly retains independence metadata. The gap is limited to whether this rule may fire at all.
- **Impact:** The result can surface a false or circular contradiction and generate five unsupported reconciliation hypotheses, reducing investigation quality and audit defensibility.
- **Recommended next check:** Add SAME_LINEAGE, DERIVED_COPY, CORRECTION, and INDEPENDENCE_UNKNOWN cases for the revenue rule. Define explicitly whether disagreement detection requires distinct authoritative semantic lineages or a narrower source relationship, then encode that rule without evidence voting.

### Finding 4: The lower-level currentness boundary owns a Phase 3 output allowlist

- **Finding:** `ReasoningReadySnapshot._is_closed_eager` imports and enumerates every Phase 3 type. This makes the Phase 2.5 transaction/capability layer depend on the Phase 3 domain model and requires editing the lower layer for each future closed result type.
- **Evidence:** The lazy imports and explicit allowlist are at `olin/investigator/evidence_boundary.py:148-193`; `claims.py` imports `ReasoningReadySnapshot` at `olin/investigator/claims.py:31`, creating bidirectional module knowledge.
- **Severity:** `low`
- **Confidence:** `high`
- **Assumptions:** Phase 2.5 should remain a reusable readiness boundary for later deterministic reasoning phases without owning their domain classes.
- **Contradictions:** The strict allowlist usefully rejects mappings, arbitrary dataclasses, iterators, awaitables, and subclassed scalar values. That safety property should be preserved.
- **Impact:** Future phases will expand a sensitive boundary module and increase circular-import and regression risk. It is not current Phase 4 behavior, but it encourages Phase 4 coupling.
- **Recommended next check:** Compare the current design with a fixed Phase 3 gate that validates exactly `ClaimsAssessment` outside the generic readiness primitive, or a small boundary-owned immutable closed-value contract. Preserve exact-type recursion and rejection of user-defined containers.

### Finding 5: The bounded kernel preserves the essential non-credit boundaries

- **Finding:** The implemented output has no scoring, approval, pricing, facility, reconstruction, persistence, provider, network, AI, or action-ranking authority. Facts require exact Phase 2 proposition verification; unknowns and hypotheses remain explicit; canonical output is versioned and ordered.
- **Evidence:** `ClaimsAssessment` fields are limited to bindings and epistemic outputs at `olin/investigator/claims.py:243-286`. Fact promotion requires both `EvidenceClass.VERIFIED_FACT` and `VERIFIED_FOR_PROPOSITION` at lines 467-478. Unknown, contradiction, and explanation constructors assign distinct epistemic types and confidence at lines 561-603 and 624-717. Canonical ordering is explicit at lines 460-462, 499-525, and 762-779. The Phase 3 document expressly preserves these boundaries.
- **Severity:** `informational`
- **Confidence:** `high`
- **Assumptions:** No unexamined caller treats this in-memory assessment as a credit or money authorization.
- **Contradictions:** Findings 1-3 limit whether the provenance and claim/contradiction classifications can yet be trusted.
- **Impact:** These are assets worth preserving through the required corrections and keep the work within Phase 3 rather than leaking into Phase 4.
- **Recommended next check:** Retain the current output exclusions and canonical byte-equivalence tests after resolving the blockers.

## Alternative architecture and migration path

Preserve the PostgreSQL lock/currentness transaction, exact proposition verification, immutable result types, canonical serialization, explicit rules version, and absence of persistence. The smallest credible correction is incremental:

1. For this Phase 3 increment, recognize claims only through a closed assertion-profile allowlist over the existing sealed evidence class, unverified status, complete proposition fields, exact authority-owned assertion-recording method, and issuer. Treat every other artifact as non-claim. Version this rule. A future canonical schema can add dedicated claim class and assertion time without blocking this increment.
2. Separate a pure deterministic classifier from the authoritative result envelope. Pure-kernel fixtures may accept explicit sealed test inputs, but only `PostgresReasoningSnapshotGate.assess_claims_current` should attach tenant, case, snapshot, authority, and evidence-state bindings.
3. Remove mutable capability state as the kernel's authorization test. Bind authoritative envelope creation to successful pre- and post-kernel currentness checks in the fixed gate path, and add direct-call/activation-forgery negative tests.
4. Add lineage compatibility to the first revenue rule, then rerun focused and PostgreSQL tests. No migration for reasoning results and no Phase 4 component is warranted.

The current alternative—retaining artifact-class inference and treating underscore fields as sealing—is smaller in code but does not satisfy the stated authority semantics. A long-term service split is unnecessary for this pilot.

## Evidence and monetary integrity checks

- **Authoritative provenance and verification:** Fact promotion is narrow and correct; claim assertion qualification is missing, and the authoritative envelope is bypassable.
- **Unknown-versus-bad treatment:** No adverse conversion found. Unknowns are explicit and `NOT_CLASSIFIED` or reconciliation-material.
- **Reason-code and consent-history preservation:** No mutation found. Live consent and expiry checks remain in the wrapper.
- **Deterministic scoring boundaries:** No scoring exists. The 20% threshold is documented as reconciliation policy, not credit calibration.
- **Approved amount, facility, tenor, pricing, repayment schedule, and outstanding balance:** No new monetary truth or terms found.
- **LLM/agent authority boundaries:** No model or agent invocation found.
- **Reproducibility and version provenance:** Overall schema/rules versions, snapshot digest, authority revision/digest, and evidence-state digest are present; individual findings carry rule IDs.
- **Evidence-type classification:** Verified facts are sound; merchant/external claim classification is not supported by an assertion-specific authority field.
- **Fairness and proxy risk:** No protected-class, geo, or behavioral feature introduced.
- **Accountable owner:** No production credit decision is introduced; the Evidence Authority owner must own the allowed assertion-recording method values.
- **Data lifecycle controls:** No persistence added; live source, consent, retention, and evidence expiries are rechecked.
- **Audit integrity:** Canonical outputs bind references and rules, but bypassable envelope creation and inferred claimant semantics weaken audit integrity.
- **Production-boundary compliance:** No money-moving action exists. The hard Phase 3 entrypoint condition is not yet met.

## Closing

- **Open questions:** Which existing authority-owned `verification_method` values unambiguously mean that an assertion was recorded? Can a later projection version add assertion time without importing raw artifact bodies? Is same-lineage revenue reconciliation ever valid, and if so under which explicit relationship?
- **Required owner and next action:** Investigator architecture and Evidence Authority owners should approve the closed assertion-profile allowlist, close the direct activation/issuance bypass, and add artifact/lineage-negative tests before Phase 3 CI candidacy.
- **Evidence that would change the judgment:** A real PostgreSQL end-to-end merchant-claim case with server-derived claimant and assertion metadata; negative tests proving direct activation, direct construction, raw payload, async/lazy callback, and post-transaction paths cannot emit an authoritative assessment; and lineage tests proving circular evidence cannot trigger the revenue contradiction. With those conditions met and the reported suites passing, this review would support `go-with-conditions` or `go`.

## Follow-up disposition after remediation

This section preserves the original findings above as the review history and records their disposition against the frozen remediation.

- **Additional files examined:** `db/migrations/0005_investigator_phase3_assertion_metadata.sql`; migration assertions in `test_investigator_authority.py`; durable assertion-profile and target-case tests in `test_investigator_postgres_evidence.py`; remediation tests in `test_investigator_phase3_claims.py`
- **Historical correction:** The original Phase 3-only recommendation under Finding 2 proved insufficient because migration `0003` required all unverified proposition fields to be null. The additive CHECK change in migration `0005` was therefore necessary for a durable assertion path; it does not persist reasoning results.

### Final executive disposition

- **Decision:** `go-with-conditions`
- **Confidence:** `high`
- **CI candidacy:** Architecture supports `READY-FOR-PHASE3-CI-CANDIDATE`.
- **Condition:** Before applying migration `0005` to a populated production table, measure the row count and acceptable lock window or use a staged `NOT VALID` / `VALIDATE CONSTRAINT` replacement. Production deployment was not part of this review.
- **Residual uncertainty:** The reconciliation threshold remains an explicitly unvalidated investigation policy, and the generic readiness boundary still knows the Phase 3 output allowlist. Neither gives credit or money authority in this increment.

### Disposition of Finding 1: resolved

- **Evidence:** `ReasoningReadySnapshot._require_phase3_operation` now requires an operation-local context value containing the exact capability object, its full binding/reference fingerprint, and an active shared lease at `olin/investigator/evidence_boundary.py:147-175`. The fixed gate creates the lease only around the Phase 3 call and revokes it in `finally` at lines 695-708. `_consume_phase3` checks the lease before invocation and immediately before the final database check at lines 344-350; `assess_claims` checks it on entry at `olin/investigator/claims.py:491-495`. The fingerprint covers transaction/backend/deadline, tenant, case, snapshot, authority/evidence bindings, and the canonical reference digest.
- **Independent check:** Direct `assess_claims(capability)` and direct `capability._consume_phase3(assess_claims)` both failed with `TypeError` and caused zero currentness queries. `copy.copy(capability)` failed. A context captured during a valid operation failed after return because it retained the revoked shared lease. The focused raw/dict, copy/JSON/field activation, active mutation, and copied-context success/exception tests passed.
- **Assumptions:** This enforces the application API and operation lifetime. As documented, trusted code with arbitrary reflection or monkeypatch authority in the same Python interpreter is outside this mechanism's security boundary.
- **Next check:** Preserve the copied-context and fingerprint-mutation regressions whenever the readiness wrapper changes.

### Disposition of Finding 2: resolved by a narrow additive contract

- **Evidence:** The kernel now recognizes claims only for exact versioned pairs `MERCHANT_SUPPLIED_ARTIFACT` / `merchant_assertion_recorded:v1` and `EXTERNAL_EVIDENCE` / `external_assertion_recorded:v1`, with `UNVERIFIED`, schema version 1, complete proposition/period, and nonblank issuer requirements at `olin/investigator/claims.py:33-36`, 342-355, and 522-535. Observation time is still not promoted to assertion time.
- **Database contract:** Migration `db/migrations/0005_investigator_phase3_assertion_metadata.sql` preserves the verified-fact and legacy null-proposition branches and adds only the two exact unverified assertion profiles at lines 30-82. It creates no table, role, grant, or reasoning-result persistence. The PostgreSQL tests exercise the real 260,000 MXN merchant claim plus 118,000 MXN verified inflow through the durable wrapper, an external assertion, and invalid method/class/schema/value combinations at `test_investigator_postgres_evidence.py:2329-2380`.
- **Independent check:** An artifact marked `document_text_extracted:v1` produced zero claims; the valid target produced one claim, one verified fact, one unknown, one contradiction, and five hypotheses. The focused unversioned/upload profile test passed. The full PostgreSQL 16 suite was reported as 326 passing with zero skips before the final bounded explanation-family correction; the independent focused suite passed after that correction, and the final full-suite rerun is owned by the root validation gate.
- **Migration safety:** `DROP CONSTRAINT` followed by `ADD CONSTRAINT CHECK` inside one transaction is logically atomic and validates the old rows, but PostgreSQL holds the strong table lock through that validation. This is acceptable evidence for disposable CI, not evidence of a safe lock window on a populated deployment. A staged new constraint with `NOT VALID`, `VALIDATE CONSTRAINT`, then a short transactional old-drop/new-rename swap is the credible operational alternative.
- **Next check:** Evidence Authority owns the two method markers. Before production migration, record table size, validation duration, lock budget, rollback procedure, and migration-owner accountability.

### Disposition of Finding 3: resolved

- **Evidence:** Cross-scope revenue reconciliation now requires distinct original semantic lineages and rejects shared economic-event and upstream-issuer identities at `olin/investigator/claims.py:455-488` and 592-595. Provenance retains `economic_event_id` and `upstream_issuer_id`, so the rule does not infer independence from reference count.
- **Independent check:** A claim and fact sharing one semantic lineage produced zero contradictions. Focused cases for same lineage, derived copy, correction, shared economic event, shared upstream issuer, and unknown independence passed. Distinct original lineages with `INDEPENDENCE_UNKNOWN` still produce the deterministic disagreement, preserving unknown rather than inventing independence.
- **Next check:** Keep semantic-lineage compatibility versioned with the Phase 3 rule set.

### Disposition of Finding 4: accepted low-severity debt

- **Evidence:** The strict exact-type eager-result allowlist remains in `ReasoningReadySnapshot._is_closed_eager`. It continues to reject arbitrary dataclasses, mappings, scalar subclasses, generators, and asynchronous values.
- **Impact:** This coupling does not leak Phase 4 behavior or create authority in Phase 3. Revisit it only when a second reasoning result type would otherwise require expanding the boundary.
- **Next check:** At the first additional reasoning kernel, compare a boundary-owned closed-value interface with another explicit allowlist entry; do not generalize before that pressure exists.

### Preserved assets and final boundary judgment

The remediation preserves the PostgreSQL shared-lock/currentness transaction, runtime role and tenant custody, exact live authority reconstruction, server-derived pre-invocation expiry check, eager closed return, final fingerprint and database checks, immutable/versioned canonical output, proposition-specific fact promotion, explicit unknowns, hypothetical explanations, and absence of scoring, lending terms, money movement, AI, acquisition, result persistence, or Phase 4 action ranking.

No unresolved architecture blocker remains for a Phase 3 CI candidate. The migration lock-window condition applies before production deployment, and the low output-allowlist coupling is recorded technical debt rather than a reason to expand this phase.
