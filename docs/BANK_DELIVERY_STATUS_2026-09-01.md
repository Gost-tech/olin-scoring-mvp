# Olin bank delivery status — 2026-09-01

## Executive verdict

Olin is a deployable candidate for a controlled, bank-owned real-data shadow UAT. It is not yet a deployed or institution-approved production service. The product returns explainable decision support; the institution remains the official credit decision maker and no Olin shadow endpoint moves money.

## Delivered in the product

| Area | Delivered evidence |
|---|---|
| Real-data safety | Real data is off by default; production startup fails closed if the technical and operational prerequisites are incomplete. |
| Storage | Managed PostgreSQL runtime support, TLS enforcement/attestation, encryption/KMS checks, backup and restore evidence gate. SQLite is synthetic/test only. |
| Deployment | AWS reference runtime for private RDS, ECS Fargate, HTTPS ALB, WAF, immutable image digest, encrypted logs, alerts, rollback and deletion protection. |
| Identity and access | Named partner/analyst/admin roles, tenant filtering, strong unique bootstrap credentials and HMAC-signed short-lived sessions. |
| Intake | Authenticated hosted intake plus a controlled, checksummed historical batch path capped at ten cases. Raw transactions and common secret fields are rejected by the batch importer. |
| Data authority | Direct consent and bank-documented historical processing authority are stored separately, versioned and audit-recorded. Consent withdrawal is supported. |
| Evidence | Trusted-source registry, signed bank callbacks, idempotency, evidence references, correction workflow and audit reconstruction. |
| Credit governance | Shadow-only recommendation, bank decision captured separately, manual/committee routing for uncalibrated business types and live-lending kill switch. |
| Outcomes | Bank decision, override reason, repayment state, delinquency observations and observation windows can be returned and retained. |
| Operations | Readiness endpoint, structured request logs without bodies/query strings, control-room workflows, alerts and incident ownership gate. |
| Contract | Versioned OpenAPI contract and bank integration/runbook package. |

## Verification completed on 2026-09-01

- 155 automated tests passed.
- V2 tier-matrix compatibility assertions passed.
- Full lifecycle compatibility flow passed in simulation.
- Bank-data connector pipeline assertions passed with mock data.
- 1,000 synthetic cases passed the safety checks with no real outcomes and no money movement.
- All 20 supported SME business types passed synthetic bank acceptance; adversarial missing/untrusted evidence routed safely.
- All five Terraform files parsed successfully.
- OpenAPI JSON validation, Python compilation and whitespace validation passed.

These checks establish software behavior. They do not establish predictive accuracy, a default rate, legal sufficiency, security certification or the bank's approval.

## Required from the bank/cloud owner before the first real case

1. AWS account and approved deployment role.
2. VPC, private application/database subnets, application security group, ACM certificate, DNS name and approved ingress ranges.
3. Secrets Manager object containing database URL, named users, session secret, webhook secrets and the non-secret evidence references required by preflight.
4. Exact data classification, field schema, authorized purpose, case scope, retention period and written processing-approval reference.
5. Named security/incident, privacy, credit-risk, model-risk and UAT owners.
6. Approved container vulnerability result, Terraform plan/apply record and penetration/security review required by the institution.
7. Successful database migration, production preflight, readiness check and isolated restore exercise.
8. Written GO for the first authorized case. Prospective applicant data also requires an approved non-synthetic OTP delivery adapter and legally reviewed consent journey.

## First real-data run

Use pseudonymized historical cases if the bank approves that classification. Transfer only through the bank-approved encrypted channel into the deployed bank environment—never email, chat or a personal workstation. Start with one dry-run batch, validate its checksum and schema, import no more than ten cases, have analysts record official decisions/overrides, and return outcome observations under the agreed timetable.

## Explicitly not delivered or claimed

- No AWS resources have been created from this workstation.
- No real bank data has been received, copied or processed here.
- No production restore or penetration test has been performed.
- No bank security, privacy, legal/compliance, model-risk, credit-risk or analyst-UAT sign-off has been issued.
- Ten cases will test workflow value, not predictive performance. Score calibration requires a larger labeled cohort with mature repayment outcomes.
- Live lending, disbursement, servicing and collections remain outside this shadow UAT.

## Bank handoff documents

- `BANK_REAL_DATA_UAT_DEPLOYMENT.md`
- `bank-integration-pack/README.md`
- `bank-integration-pack/BANK_BATCH_INTAKE.md`
- `bank-integration-pack/GO_LIVE_GATE.md`
- `bank-integration-pack/UAT_AND_SHADOW_PLAN.md`
- `openapi-v1.json`
- `../infra/aws/README.md`
