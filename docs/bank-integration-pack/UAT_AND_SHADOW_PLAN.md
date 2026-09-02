# UAT and shadow-pilot plan

## Phase 1 — synthetic contract UAT

Bank engineering creates fake merchants covering every business segment plus malformed, duplicate, cross-tenant, withdrawn-consent, stale-evidence, and provider-outage cases. Exit requires 100% pass on authorization, consent, provenance, idempotency, terminology, and audit controls.

## Phase 2 — security and operations rehearsal

Rotate a webhook secret, revoke a partner token, restore a backup, simulate provider timeout, exercise alert paging, export one audit trail, and execute incident containment. Exit requires named owners and measured RTO/RPO.

## Phase 3 — controlled shadow pilot

The bank makes its normal decision without Olin affecting credit or money movement. Olin recommendations are revealed only for approved evaluation purposes. Capture agreement, overrides, reason codes, decision time, subsequent repayment outcomes, missing evidence, and segment.

Suggested initial limits are governance choices for the bank, not model claims: one institution, one approved cohort, a small fixed case ceiling, no automated disbursement, daily exception review, and an immediate kill switch.

## Phase 4 — model-risk review

Evaluate coverage, stability, calibration, false positive/negative cost, override patterns, segment performance, and prohibited/proxy feature risk on real labeled outcomes. Synthetic pass rates validate software behavior only; they do not validate default prediction.

## Stop conditions

Stop intake on cross-tenant exposure, consent bypass, unverifiable evidence, corrupted audit history, unresolved high-severity security event, material drift, or any money movement initiated outside the bank's approved workflow.
