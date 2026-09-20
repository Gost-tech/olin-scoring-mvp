# Phase 7 focused review evidence

Reviewer: independent agent `phase7_feedback_review`, 2026-09-20.
Scope: Phase7 worktree over accepted7780821; attribution/source promotion,
isolated writes, historical report receipts, cohort completeness, corrections,
replay and concurrency. Same focused review including small final deltas;
not a platform/Phase0–6 rereview. Evidence summarized by implementer from the
reviewer's messages; not founder acceptance.

## Judgment

Go-with-conditions, medium-high confidence: complete final candidate database,
browser and CI gates. No remaining blocking finding identified after correction.
Assumptions: synthetic-only development; authenticated app trusted for browser
actor attribution; service credentials never issued to analysts. No monetary,
canonical-evidence, research-inference or bank event authority is granted.
No material dissent remains. Production/usefulness conclusions remain unavailable.

## Findings and disposition

- Medium/high-confidence setup-safety defect: direct fixture setUpClass bypassed
  unittest's disposable-availability decorator. A *_investigator_test DSN alone
  could start setup without explicit disposable confirmation, contradicting the
  launch contract. Corrected with a pre-setup guard requiring both availability
  and disposable confirmation. Reviewer inspected closure and personally ran
  `test_demo_refuses_before_setup_without_disposable_confirmation`:1passed,
  zero failures/errors/skips. Finding CLOSED.
- Low/high-confidence display issue: case switch could retain prior feedback or
  accept a delayed history response. Server receipt binding already prevented
  wrong-case writes. Corrected by clearing the view and checking requested case;
  ambiguous write payload/key/case are retained. Reviewer inspected correction.
- Informational/high-confidence limitation: whole history reads are appropriate
  only for this bounded synthetic development workload, not large production
  histories. Pagination/retention policy is deferred, not added in this task.

## Supporting inspection

Migration0008 uses constrained functions, isolated non-owner roles, forced RLS,
tenant/session binding, recursive membership checks, immutable rows, command
digests and expected-version correction checks. Cohort versions retain prior
members. Application closed fields and domain-separated receipts prevent caller
trust/actor/report substitution; historical access does not reactivate evidence.
Unknown database outcomes return503 and retain an identical browser retry;
known SQL rejections are distinguished. Child demo app environment excludes
operator/admin/canonical-writer/model credentials. Existing cost/action/research
history is reused, not duplicated. No fairness/performance findings are inferred.

The reviewer did NOT execute PostgreSQL/browser/full suites. Those are separately
attributed implementation/CI evidence. The next acceptance check should inspect
the exact committed candidate and final gates, not treat source review alone as
production or bank approval. New contradictory race/access evidence would reopen
the relevant finding; optional UI wording does not expand this scope.
