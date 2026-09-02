# CISO go-live review — 2026-08-20

## Verdict

**NO-GO for real-data production. GO for isolated synthetic UAT. Conditional GO for a shadow pilot only after bank security and privacy approval.** The local software controls materially reduce risk, but production infrastructure and independent evidence do not yet exist.

## Highest risks

1. **Credential or tenant compromise.** Blast radius could include one or more partner case dossiers if production isolation, gateway controls, and centralized detection are absent. Current mitigation: named Bearer identities, role permissions, partner ownership filtering, rate limiting, and cross-tenant tests. Required: managed IAM/secrets, network controls, SIEM, revocation drill, and external test.
2. **Forged or replayed financial evidence.** This can corrupt recommendations without necessarily exposing data. Current mitigation: exact-body HMAC, consent and connection binding, provider-scoped rotating keys, immutable payload hashes, exact duplicate acknowledgment, and changed-payload conflict rejection. Required: provider key ceremony, timestamps/replay window policy, centralized anomaly alerts, and provider certification.
3. **Unvalidated decision use.** A bank could mistake a synthetic-tested recommendation for validated lending approval across sectors. Current mitigation: decision-support terminology, separate official bank decision, committee routing for uncalibrated types, model versioning, and outcome capture. Required: bank model-risk approval, real labeled backtest, segment monitoring, fairness/proxy review, threshold and loss limits.

## STRIDE review

| Threat | Current control | Remaining production evidence |
|---|---|---|
| Spoofing | Bearer auth; HMAC callbacks | IAM lifecycle, mTLS/allow-list decision, rotation/revocation proof |
| Tampering | payload hash; immutable event ID binding; correction trail | managed immutable audit export and database access controls |
| Repudiation | request IDs; actor and consent audit | centralized time-synchronized logs and retention |
| Information disclosure | partner scoping; raw callback transactions forbidden | encryption at rest, DLP/log redaction, penetration test |
| Denial of service | bounded bodies; rate limit; bounded request workers | gateway limits, autoscaling/capacity test, queue/DLQ |
| Elevation of privilege | role-permission matrix | periodic access review, break-glass control, external test |

## Detection and response requirements

Alert on authentication failure bursts, cross-tenant probes, webhook signature failures, event-ID conflicts, unusual evidence volume, consent rejection, admin actions, and provider latency/error rates. A production incident runbook must define bank/Olin contacts, severity, containment, credential revocation, evidence preservation, notification decision, recovery, and post-incident review.

## Regulatory and contractual unknowns

Counsel and the bank must confirm the final role allocation, consent/privacy text, data retention, data-subject handling, bureau and provider permissions, adverse-action responsibilities, subcontractors, cross-border processing, audit rights, and incident-notification terms. This review does not replace legal advice or a bank vendor-risk assessment.

## Risk quantification

Annualized loss exposure cannot be credibly calculated yet because production case volume, data population, contract liability, fraud exposure, and incident cost assumptions have not been approved. Treat any numerical risk estimate before those inputs as invented.
