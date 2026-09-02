# Olin adversarial review

Date: 27 July 2026  
Verdict: **BLOCK for live lending. CONCERNS for a partner shadow pilot.**

## Executive conclusion

Olin has a real working decision prototype. It does not yet have evidence that
a lender will buy it, that the policy predicts repayment, or that the company
can safely operate a live loan book. The most important next deliverable is not
another feature. It is a partner agreement that grants lawful data access and
produces labeled cases.

The business should remain one product:

> credit-decision infrastructure for institutions serving Mexican small
> businesses.

Direct lending should remain a separate, gated future option. Combining both
stories now makes the buyer, regulatory perimeter, capital need and economics
impossible to evaluate.

## Persona 1: Saboteur

How I would make the project fail while appearing busy:

1. Keep polishing the website and deck while no institution commits cases,
   data access, a decision owner or a budget.
2. Call ten shadow cases “validation” even though they cannot validate
   repayment or policy accuracy.
3. Market one scorecard across every business sector before outcomes show
   whether sector-specific thresholds are required.
4. Promise settlement-linked collection before a signed acquirer or bank
   integration exists.
5. Raise lending capital before deciding whether Olin is software or a lender.

Severity: **critical strategic risk**. This creates an attractive demo with no
repeatable business.

## Persona 2: New hire

What a capable new product or credit lead cannot determine from the repository:

1. Which document is the single source of truth for positioning. Multiple decks
   and two video projects tell different versions.
2. Which integrations are real, contracted, mocked or only contemplated.
3. Whether `evidence_route` changes underwriting or is descriptive metadata.
4. What quantitative go/no-go result advances a 10-case pilot into backtesting.
5. Who legally owns underwriting, AML, servicing, complaints and data-controller
   obligations in a live cohort.

Severity: **high operational risk**. A partner cannot approve a pilot while
ownership and acceptance criteria remain implicit.

## Persona 3: Security auditor

Blocking findings for live lending:

1. Named static API tokens are an MVP control, not enterprise identity. There
   is no SSO, MFA, rotation UI, device policy or session revocation.
2. SQLite and local files are unsuitable as the production system of record for
   concurrent financial operations and durable evidence.
3. Evidence is represented by references, but the product has no immutable
   document store, checksum, retention rule or legal-hold workflow.
4. Consent records lack a privacy-notice version and purpose-specific consent
   version.
5. Live third-party integrations, retry/idempotency contracts, reconciliation
   and vendor outage behavior are not implemented.
6. Payment and servicing code exists, but there is no approved production
   operating model around it.

Controls strengthened in this review:

- the chosen evidence route now requires the corresponding verified evidence
  reference in production;
- hybrid requires at least two verified operating sources;
- live money movement is off by default and requires an explicit production
  feature flag in addition to the existing shadow and role gates.

Severity: **critical for live money; manageable for an isolated shadow pilot**.

## What ten cases can and cannot prove

Ten cases can prove:

- the partner can submit authorized evidence;
- analysts understand the output;
- missing sources remain visible;
- cases are isolated by role;
- decisions and reasons are recorded;
- no shadow case can move money.

Ten cases cannot prove:

- default rate;
- approval lift at constant loss;
- score discrimination;
- stable thresholds;
- sector portability;
- portfolio profitability.

Predictive claims require a historical backtest with hundreds of labeled cases
and later a governed live cohort with mature outcomes.

## Business verdict

Andreessen-style market-first score: **6.05/10, MARKET-FIRST-DERISK**.  
Product-market-fit signal: **0.3/10, BEFORE-PMF**.

The strongest counterargument is that Olin currently combines commodity data
providers and an unvalidated scorecard while the lender already owns credit
policy, distribution and outcomes. Olin becomes defensible only if it owns the
cross-source case graph, integration speed, auditability and accumulating
partner-specific outcome data.

Recommendation: **continue, but stop treating product polish as commercial
proof.** Win one paid design partner before expanding scope or funding loans.

Confidence: high on the product-status assessment; medium on market potential;
low on willingness to pay until a design partner signs.
