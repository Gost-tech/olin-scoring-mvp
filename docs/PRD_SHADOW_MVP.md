# Olin Shadow MVP

Status: locked for the first partner pilot  
Owner: Brice Garnier  
Product mode: B2B decision support  
Pilot population: 10 authorized abarrotes cases  
Money movement: prohibited

## Problem

Financial institutions that evaluate small Mexican businesses often receive
incomplete and inconsistent evidence. The analyst must reconstruct capacity,
credit history, operating continuity, and missing information across several
sources. Olin should make that work faster and auditable without replacing the
institution's policy or decision.

## User and customer

- Customer: a bank, SOFOM, or lending fintech.
- Primary user: a credit analyst or risk manager.
- Evaluated subject: a small merchant.
- Olin is not the lender and does not accept public loan applications in this
  MVP.

## Core outcome

An authenticated analyst can create one consented case, attach the provenance
and verification status of its evidence, run the current Olin scorecard, review
the explainable route, record the partner's independent decision, and include
the case in a cohort export.

The MVP succeeds when 10 partner-authorized cases can complete this loop with:

- 100% consent artefacts recorded before scoring;
- 100% signal sources and verification states visible;
- 100% recommendations reconstructable from stored inputs;
- 100% partner decisions recorded with a reason;
- zero public exposure of case or merchant data;
- zero possible disbursement from a shadow case.

Agreement rate and default rate are observations, not success targets, because
10 cases are not a statistically meaningful performance sample.

## Required workflow

1. Authenticated partner user creates a shadow case.
2. User records the merchant's consent text, version, channel, actor, and time.
3. User adds evidence and identifies each source as verified, missing, or
   rejected.
4. Olin runs the existing Círculo, DSCR, and internal-score matrix.
5. Olin displays the route, amount evaluated, reasons, missing evidence, source
   status, and engine version.
6. Partner records its independent approved, declined, or pending decision and
   rationale.
7. Olin includes the case in a 10-case pilot export.

## Must have

- Named-user authentication before any case data is returned.
- Spanish partner interface.
- Persistent case queue backed by the same database as the scorecard.
- Versioned consent artefact.
- Evidence provenance and verification status.
- Current scorecard and repayment gates, unchanged unless separately approved.
- Clear separation of engine recommendation and partner decision.
- Immutable audit events for case creation, scoring, and partner outcome.
- Shadow-mode disbursement block enforced by the backend.
- API and browser tests for every step of the core loop.

## Should have

- Missing-evidence checklist.
- Cohort filters and CSV export.
- Synthetic demonstration mode using the same workflow and API contract.
- Readable partner-facing report for one case.

## Explicitly out of scope

- Public merchant loan application form.
- Public investor dashboard containing operational data.
- Live origination, STP transfer, repayment, or collection.
- Automated approval without a human partner decision.
- Machine learning or claims of predictive accuracy.
- Policies calibrated for business types beyond the first abarrotes cohort.
- Claims of a live integration or partnership without written confirmation.

## Product guardrails

- `case_mode` is required and must be `shadow` for this MVP.
- Production scoring rejects mocked or unverified bank and FMCG evidence.
- A shadow case can never call a money-movement connector.
- Public routes never return merchant names, phone numbers, CURP, scores,
  decisions, or amounts.
- Synthetic data is visibly labelled and stored separately from production
  cases.
- Reloading the browser must not erase a completed action.

## Rollout

1. Local synthetic tests.
2. Deployed synthetic demo with no personal data.
3. Internal walkthrough using three synthetic cases.
4. Partner security and workflow review.
5. Ten consented shadow cases.
6. Joint report and go/no-go decision for any later live pilot.

Any failed security guardrail rolls the product back to synthetic-demo-only
mode.
