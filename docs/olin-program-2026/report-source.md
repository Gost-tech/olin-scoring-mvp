# Olin Evidence Passport and bank-readiness program

**Canonical report source**  
**Date:** 27 August 2026  
**Status:** Founder working plan; legal and bank-policy drafts require human approval

## Executive decision

Olin should not promise “a loan with anything” or “a loan with nothing.” It
should promise a **fair next-best-evidence route**: when a conventional document
is absent, Olin identifies another independently verifiable way to evidence the
same fact. If identity, informed consent, authority, or repayment capacity still
cannot be evidenced, the answer is **not yet eligible**, with a concrete plan to
build evidence. Collateral can reduce loss severity; it does not establish the
ability to repay.

The immediate company goal remains one ten-case, bank-controlled shadow pilot.
The new Evidence Passport is the differentiator inside that pilot, not a second
live lending business. Olin remains decision support. The partner owns policy,
the customer relationship, the credit decision, contracting, funding,
servicing, complaints, and collections.

## What is already built

- Named-user bearer authentication with partner, analyst, and admin roles.
- Partner-level case filtering, immutable audit events, corrections, consent
  withdrawal, partner decisions, outcome events, and pilot readiness checks.
- A default-on live-lending kill switch and shadow-only controls.
- Bank, TPV, supplier, fiscal/public-data concepts and source provenance.
- A viral institutional design-partner waitlist with encrypted email and referral
  codes; it is deliberately separate from borrower applications.
- AWS Terraform, container configuration, a PostgreSQL compatibility adapter,
  schema documentation, and readiness hooks, but not an applied and restored
  bank-approved production environment.
- A shadow-pilot agreement draft and legal-review workflow.
- Evidence Passport v2 policy engine and authenticated assessment endpoint.
  It accepts only server-registered, case/tenant/consent/source/origin/expiry-
  bound evidence IDs; it does not accept caller-asserted verification labels:
  `GET /api/v1/evidence-passport` and
  `POST /api/v1/evidence-passport/assessments`.

## The 18 items, rethought

| # | Decision | What to do now | Proof required |
|---|---|---|---|
| 1 | Pilot partner | Continue current outreach; do not wait to finish every production feature. | Named sponsor and signed pilot scope. |
| 2 | Decision-makers | Name bank owners for credit, model risk, privacy, security, engineering, operations, and procurement. Hire Olin owners listed in the hiring pack. | RACI with names, emails, backup, and authority. |
| 3 | Pilot agreement | Use the existing shadow agreement plus the outcome-data addendum. | Counsel-approved and signed copies, version IDs, dates. |
| 4 | Ten real cases | Use ten genuine, consented cases selected across evidence routes. Do not scrape people from the internet. | Ten audit trails and partner decisions. |
| 5 | Consent | Use a short layered flow with separate privacy, provider-access, and credit-bureau artifacts. | Exact text/version/hash, identity evidence, timestamp, channel, receipt, withdrawal path. |
| 6 | Data access | Start with partner-supplied bank features, Syncfy Widget, DENUE, and a partner-owned Círculo route. | Commercial contract, DPA, credentials, security review, sandbox and production acceptance. |
| 7 | Outcome contract | Make delivery of decisions and performance events a contractual pilot obligation. | Monthly data feed with immutable case ID and correction protocol. |
| 8 | Credit policy | Bank credit owner fills the policy template; Olin encodes and tests it. | Signed policy version and test evidence. |
| 9 | Work saved | Time the same workflow before and with Olin. | Handling-time events, missingness, overrides, usability, audit coverage. |
| 10 | Commercial offer | Sell a fixed-fee pilot, paid implementation, then platform plus case volume. | Price acceptance, procurement path, conversion rule. |
| 11 | Infrastructure | Exercise the PostgreSQL adapter and deploy only in the bank-approved AWS account. | Migration test, Terraform plan/apply, TLS, encrypted storage, monitoring, backup and restore evidence. |
| 12 | Access control | Replace long-lived bearer tokens with an approved IdP, short sessions, MFA, tenant claims, and quarterly access reviews. | Access matrix, test results, joiner/mover/leaver logs. |
| 13 | Operations | Build one control-room queue for exceptions, withdrawals, corrections, outages, alerts, and kill switch. | Named owner, SLA, daily review log, rehearsed escalation. |
| 14 | Approvals | Use the pilot manifest as the approval ledger; attach evidence rather than accepting a checkbox alone. | Written sign-offs by each accountable approver. |
| 15 | Validation data | Use public data only for engineering and research. Predictive validation needs partner labels and mature repayment outcomes. | Larger representative cohort, data dictionary, observation window, leakage and bias review. |
| 16 | Reference proof | Pre-negotiate permission for an anonymized report and optional named case study. | Signed publication/testimonial clause after successful pilot. |
| 17 | Distribution | Keep the institutional referral waitlist; add merchant interest only as a non-credit “Evidence Passport early access” fake door after privacy approval. | Qualified meetings and partner referrals, not vanity signup count. |
| 18 | Live lending | Build controls later, after role, contract, regulatory, provider and operational authority exist. | Dual approval, authoritative reconciliation, durable transfer states, portfolio limits, complaints and collections ownership. |

## Ten-case cohort design

Ten cases prove workflow value and control behavior, not predictive accuracy.
The bank should pre-screen a real pool and select the first eligible case in
each desired stratum without changing the sample after seeing Olin's result.

| Case | Desired real-world condition | What Olin must demonstrate |
|---|---|---|
| 1 | Complete bank-flow evidence | Baseline route and reconstruction. |
| 2 | TPV/platform settlements but weak bank history | Correct TPV route and disclosed cash gap. |
| 3 | Supplier history but no formal sales ledger | Supplier route; purchases are not mislabeled as revenue. |
| 4 | CFDI/fiscal trail | Reconciliation of invoicing and collected cash. |
| 5 | Cash-heavy business | Three-source observed route, committee-only. |
| 6 | Thin-file/new business | “Build evidence first,” not invented approval. |
| 7 | Identity/address mismatch | Correction workflow and re-verification. |
| 8 | Consent withdrawn before provider access | Future ingestion blocked and event audited. |
| 9 | Provider unavailable/stale data | Degraded route, no silent fallback to synthetic data. |
| 10 | Collateral offered but weak capacity | Collateral separated from repayment capacity. |

If the real pool does not contain every condition, keep the real cohort natural
and exercise the missing control condition in synthetic UAT. Never manufacture
a borrower event to fill a table.

### Per-case sequence

1. Partner confirms eligibility and ownership of the customer relationship.
2. Applicant sees layered privacy and purpose notices.
3. Identity and authority are verified.
4. Consent artifact is captured and versioned.
5. Evidence Passport suggests the next-best route.
6. Provider or partner verifies the evidence; missingness remains visible.
7. Olin produces a recommendation and reasons.
8. Bank analyst records an independent decision and override reason.
9. Olin records workflow time, exceptions, corrections, and audit completeness.
10. Partner returns performance outcomes under the agreed window.

## Credit-policy construction

The qualified bank credit owner—not Olin—must approve the following versioned
policy fields:

- eligible borrower, geography, sector, legal form, minimum operating history;
- prohibited uses and hard declines;
- mandatory identity, consent, authority, bureau, and AML/KYC evidence;
- accepted capacity routes and source-quality thresholds;
- cash-heavy route requirements and committee rules;
- amount, term, pricing, exposure, concentration, and collateral limits;
- DSCR/cash-flow definitions, stress assumptions, and exception authority;
- missing/stale/conflicting evidence treatment;
- reason codes, override permissions, stop conditions, and review cadence;
- outcome label, delinquency definition, observation window, and model-change
  process.

Olin then implements policy-as-code, creates a golden test suite, and compares
every release against the signed policy version. No segment enters autonomous
approval until model risk accepts sufficient representative outcome evidence.

## Simple consent without “auto-signing”

A typed name followed by “boom, signed” is too weak for this use. The practical
fast flow is:

1. Plain-language purpose summary and link to the full privacy notice.
2. Separate, unchecked acceptance for the exact data purpose.
3. Phone/email OTP or an approved e-sign provider to bind the person to the act.
4. Separate special authorization for credit-bureau access when applicable.
5. Provider-hosted bank/fiscal credential entry; Olin never collects those
   credentials directly.
6. Downloadable receipt containing document/version, hash, signer identifier,
   timestamp, channel, authentication method, and withdrawal route.
7. NOM-151 preservation when counsel determines it is required or prudent.

This is a product specification, not final Mexican legal wording. Counsel and
the actual Círculo user must approve the exact authorization and retention rule.

## Commercial offer

### Recommended model

Use a hybrid model: fixed platform fee plus included case volume and transparent
overage. Do not charge per approval or as a percentage of loan value during the
pilot; that can distort incentives and makes procurement harder to explain.

### Price hypotheses to test, not claimed market facts

| Stage | Test range (MXN, before VAT and third-party data fees) | Included |
|---|---:|---|
| 6–8 week shadow pilot | 150,000–300,000 | Setup, policy workshop, UAT, up to 10 real cases, joint report. |
| Production implementation | 350,000–900,000 | SSO, tenant setup, integrations, security evidence, training, deployment support. |
| Recurring platform | 60,000–180,000/month | Core workflow, audit, support, agreed case allowance. |
| Volume overage | 100–350/case | Olin processing only; providers passed through or contracted by partner. |

Offer one founder-pilot concession only in exchange for the full outcome feed,
fast named owners, a conversion meeting on a fixed date, and conditional case-
study rights. Validate willingness to pay with at least 30 qualified responses
before treating any range as a pricing conclusion.

### Paid-conversion rule

Convert when all critical controls pass, at least 8/10 cases are usable by the
bank, consent/provenance/audit coverage is 100%, no critical incident occurs,
and the agreed handling-time target is met. Agreement with bank decisions is
reported descriptively; ten cases cannot validate default prediction.

## Hiring order

Do not hire a large team before the pilot. The first four capabilities are:

1. Fractional Mexico fintech counsel/privacy lead.
2. Founding Credit & Risk Lead with Mexican SME lending authority.
3. Founding Backend/Security Engineer who can productionize PostgreSQL, SSO, audit,
   monitoring, and provider integrations.
4. Pilot Operations & Risk Analyst who owns the control-room queue and timing.

The founder should lead enterprise partnerships until a repeatable sale exists.
A data scientist/model developer comes after a materially larger labeled cohort,
not to invent a model from ten cases.

## Distribution and viral mechanism

The institutional referral loop already exists: applicants get a referral link
and a qualified introduction can improve review priority. Keep its KPI as
qualified design-partner meetings and signed pilots.

A later merchant loop should be an **Evidence Passport early-access list**, not
a credit application:

- asks only business type, municipality, missing-evidence category, preferred
  contact, and marketing/privacy consent;
- does not collect statements, IDs, bureau data, collateral documents, or bank
  credentials;
- says there is no loan offer, approval, rate, or guaranteed placement;
- returns an educational checklist and lets the merchant invite a supplier,
  accountant, TPV provider, or lender to verify an evidence route;
- referral reward is priority or a free evidence-readiness report, never a
  promised loan or better credit terms.

Run this as a two-week fake-door test only after privacy review. Success means
qualified merchants who complete a route and introduce an institution—not raw
email count.

## Why live lending is not enabled now

The code can represent payment states, but code cannot grant the legal and
operational authority to lend or move a partner's money. Before live lending,
Olin needs the actual regulated/contractual role, approved product contract,
funding account and limits, authoritative STP reconciliation, dual approval,
durable `pending/confirmed/failed/unknown` states, manual handling of ambiguous
transfers, servicing and collections ownership, complaints and UNE routing,
fraud/AML operations, and regulator/counsel confirmation. A retry after an
unknown transfer can double-pay a borrower. That is why the kill switch stays
on during the shadow pilot.

## Questions that must be answered with the partner

1. Which entity is the lender and which entity is the Círculo Usuario/Otorgante?
2. Who has final authority to approve exceptions and set exposure limits?
3. Which evidence routes will the bank accept for each initial sector?
4. What fact must each route prove, and what minimum source quality is required?
5. What does “default,” “delinquent,” “restructured,” and “paid” mean, on what date?
6. Will the partner return rejected cases and approved cases to prevent label bias?
7. What is the observation window and delivery cadence?
8. Where must data reside, who owns encryption keys, and which IdP is approved?
9. Which vendors are already approved for bank aggregation, e-signature, and
   monitoring?
10. What events stop intake immediately, and who holds the kill switch?
11. Who owns complaints, corrections, ARCO/withdrawal requests, and collections?
12. What exact procurement budget and paid-conversion date are available?

## Next 14 days

1. Put the institution and seven named partner owners into the pilot manifest.
2. Send the shadow agreement and outcome addendum through the prepared lawyer
   review package; do not send externally without founder approval.
3. Run a 90-minute credit-policy workshop and lock three evidence routes.
4. Obtain Syncfy Widget and Círculo commercial/integration answers in writing.
5. Select a bank-approved cloud account and IdP; only then apply Terraform.
6. Run the ten-condition synthetic UAT and rehearse one consent withdrawal,
   provider outage, tenant-isolation failure, and kill-switch event.
7. Freeze scoring changes and begin the genuine ten-case shadow cohort.

## Boundary of this report

This report provides product, commercial, technical, and preliminary legal-risk
analysis. It is not a legal opinion, a credit policy, a regulatory authorization,
or approval to lend. Exact Mexican legal wording and the allocation of regulated
roles require qualified counsel and the partner institution.
