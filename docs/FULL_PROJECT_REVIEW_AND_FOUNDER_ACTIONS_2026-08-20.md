# Olin full-project review and founder action list

**Date:** 20 August 2026  
**Scope:** product, bank integration, credit validity, infrastructure, security,
data sources, geointelligence, market, and finance.

## Executive verdict

Olin is a credible bank-controlled shadow-pilot product, not a production
credit model and not an autonomous lender. The code can demonstrate intake,
consent, evidence normalization, recommendations, bank decision capture,
corrections, outcomes, and auditability. The missing proof is commercial and
statistical: no paid bank conversion path and no representative repayment
outcome set currently demonstrate that Olin improves underwriting.

- VC verdict: **MARKET-FIRST-DERISK** (moderate confidence). The Mexican SME
  financing market is large; demonstrated customer pull is weak or unknown.
- CTO verdict: **SHARPEN before real data** (high confidence). Keep the modular
  monolith, but replace SQLite and local operational controls before production.
- CISO verdict: **GO for synthetic UAT; conditional GO for a controlled shadow
  pilot; NO-GO for real-data production** (high confidence).
- Finance verdict: **unit economics unknown** (high confidence). There is no
  validated price, conversion rate, implementation cost, provider cost,
  support cost, loss/liability allocation, or renewal evidence.

## Geointelligence delivered

- Live INEGI DENUE `Buscar/todos` radius query from 50 m to 5 km.
- All supported SME types, with optional bank-approved SCIAN prefix.
- Establishment density, competitor count, complementary-business count,
  activity concentration, same-activity share, and radius bands.
- Minimized nearest-establishment, competitor, and complement results.
- GeoJSON output for a map client.
- Partner-isolated aggregate snapshots with identical-result deduplication.
- Twelve-month change/closure evidence only when the comparison is 270–460
  days old; a short interval is never mislabeled as annual evidence.
- Attachable evidence for zone density, neighbor ecosystem, neighborhood
  permanence, and directory-change rate.
- Provider contact fields are discarded; no raw phone or email is returned.

The service deliberately does not claim drive time, human footfall, satellite
radiance, sales, ownership, profitability, or repayment capacity.

## What the founder must do personally

### Immediate

1. Free at least 20 GB on the development Mac. The disk reached 100% during
   this review and caused a temporary file write to truncate.
2. Register for an INEGI DENUE token and place it in the deployment secrets
   manager as `INEGI_DENUE_TOKEN`; never paste it into source code or a deck.
3. Ask the bank to name one accountable owner each for credit risk, model risk,
   information security, privacy/legal, integration engineering, and pilot
   operations.
4. Obtain a written pilot decision: target portfolio, underwriting step,
   eligible SME segments, sample size, success metric, stop conditions, outcome
   label, observation window, and paid-conversion owner.
5. Ask the bank for a historical or prospective cohort with repayment outcomes,
   rejection reasons, overrides, and timestamps under an approved data process.

### Accounts, contracts, and approvals Codex cannot perform

6. Sign the bank pilot/SOW, DPA, security schedule, SLA, liability allocation,
   data-return/deletion terms, audit rights, and incident-notification terms.
7. Complete Syncfy or direct-bank onboarding, MFA, commercial approval, widget
   enablement, webhook registration, production origins, and pricing agreement.
8. Decide with the bank whether the bank or Olin is the authorized Círculo de
   Crédito user; complete affiliation, sandbox, production certification, and
   approved consent language.
9. Negotiate data rights with POS/acquirers, distributors, wallet/payment-rail
   providers, payroll sources, and any footfall or mobility provider selected.
10. Obtain bank approval for the SME-to-SCIAN classification catalogue and the
    definition of competitor and complementary activity by segment.
11. Have counsel and the bank approve the final privacy notice, consent text,
    purposes, retention, deletion, correction, adverse-action, and data-subject
    workflows. Permission to launch a product does not substitute for these
    bank vendor requirements.
12. Purchase/configure the production cloud account, domain, TLS certificate,
    managed Postgres, KMS/secrets manager, IAM/SSO, backups, monitoring, and
    paging accounts.
13. Commission an independent penetration test and complete the bank vendor
    security questionnaire. Codex cannot certify its own code.
14. Recruit real bank analysts for UAT and observe them completing cases. Record
    task time, missing fields, override reasons, usability failures, and whether
    the report changes or accelerates a decision.
15. Obtain written pricing feedback and a named procurement/budget owner. A
    friendly pilot without a paid next step is not commercial validation.

## Everything still missing

### Credit and model risk

- Representative repayment outcomes and a frozen outcome definition.
- Segment sample-size analysis, missingness analysis, leakage review,
  out-of-time validation, calibration, ranking metrics, and stability tests.
- Fairness/proxy review for geography, WhatsApp behavior, psychometrics,
  payroll, device or mobility-derived evidence.
- Bank-approved thresholds, reason codes, override policy, concentration caps,
  loss limits, drift triggers, and rollback procedure.
- Validation showing geointelligence adds predictive or workflow value beyond
  the bank's existing data.

### External data

- Production bank/Syncfy consent widget and certified callback.
- Círculo de Crédito production integration.
- Distributor/invoice feeds for inventory-led businesses.
- POS/acquirer settlement feed and ecommerce-platform settlements.
- Merchant-level CoDi, DiMo, OXXO Pay, Spin, and classified SPEI data.
- Authorized payroll/employer evidence.
- True footfall/mobility source, if the bank approves its purpose.
- VIIRS night-light ingestion, geospatial baselines, and QA.
- Bank-selected INEGI inflation series per SCIAN profile.
- Drive-time/walking-time routing provider if radial catchments are insufficient.

### Infrastructure and reliability

- Managed Postgres migration and tenant-isolation design for real data.
- Production API gateway, TLS, optional mTLS/IP allow-list, distributed rate
  limiting, WAF policy, and request-size enforcement.
- Managed identity, short-lived credentials, key rotation, and break-glass flow.
- Encrypted backups, restore test, failover test, RTO/RPO, and disaster runbook.
- Central logs, metrics, traces, SIEM export, alerts, on-call, and SLOs.
- CI/CD gates for tests, migrations, SAST, dependency/container scanning, and
  OpenAPI compatibility.
- Capacity evidence beyond the current controlled SQLite pilot envelope.
- Resolution of the remaining full-suite SQLite `ResourceWarning` originating
  outside the new geo snapshot connection, even though all tests pass.
- Adequate local disk capacity and build-artifact retention/cleanup policy.

### Product and bank workflow

- Production analyst UX for the new GeoJSON and competitor results.
- Bank-configurable sector/SCIAN profiles with approval/version history.
- Case-level attachment workflow from geo analysis into the application.
- Export format agreed by the bank: API payload, PDF memo, LOS fields, or all.
- Notifications, exception queue, support workflow, and operational dashboard.
- Accessibility and Spanish-language usability validation.
- General automated routing remains limited; non-calibrated sectors correctly
  require bank committee review.

### Security and governance

- Formal threat model, data-flow diagram, asset inventory, data classification,
  subprocessor register, and vendor reviews.
- Production retention/deletion enforcement for case and geo snapshot data.
- Immutable off-system audit export and periodic access review.
- Incident-response tabletop, credential-revocation drill, breach decision tree,
  and bank communication templates.
- Independent penetration test with no unresolved critical/high findings.
- SOC 2/ISO 27001 control-evidence program if required by the bank.

### Business and finance

- Signed design partner or paid pilot.
- Pricing model: implementation fee, annual platform minimum, per-case charge,
  data-provider pass-through, and support tier.
- Cost model for cloud, providers, implementation, security, support, legal,
  insurance, and bank-specific customization.
- Sales-cycle, procurement, conversion, renewal, gross-margin, CAC/payback, and
  revenue-concentration assumptions backed by actual data.
- Defined commercial boundary: Olin sells decision infrastructure to lenders;
  it does not take credit risk or operate collections in the current model.
- Evidence that workflow savings or improved approvals/losses exceed Olin's
  total cost to the bank.

## Next operating milestone

Complete one bank-controlled shadow pilot with real authorized evidence and
later repayment outcomes, then obtain a written paid deployment decision. Do
not expand the signal catalogue again until that experiment proves which
signals and workflow outputs the bank actually values.
