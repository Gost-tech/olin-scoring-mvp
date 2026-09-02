# Bank real-data UAT deployment

## Verdict

The Olin codebase can be built as a fail-closed real-data shadow service. It is not authorized merely because the repository contains Terraform or because a bank is willing to provide data. The deployed environment must pass the runtime preflight and the institution's external gates.

## Supported operating model

- One bank-controlled shadow environment.
- Institution remains the official decision owner.
- No offer, disbursement, servicing, collection or payment initiation by Olin.
- Historical or prospective data classification declared before startup.
- PostgreSQL only for real data; SQLite remains synthetic/test only.

## Deployment path

1. Bank/cloud owner supplies the AWS account, VPC, private subnets, application security group, TLS certificate, DNS name and approved ingress ranges.
2. CI builds and scans the container and publishes an immutable image digest.
3. Operations creates the Secrets Manager runtime object outside source control.
4. Terraform provisions RDS, ECS Fargate, HTTPS ALB, WAF, logs, alarms and rollback controls.
5. The migration role initializes the schema.
6. A restore exercise is completed in an isolated environment.
7. `python -m scripts.production_preflight` returns `ok: true`.
8. `/readyz` returns HTTP 200.
9. A synthetic signed bank callback is ingested and reconstructed from the audit history.
10. The bank issues a written GO for the first authorized real case.

## Required runtime values

The secret names are configuration contracts, not evidence by themselves:

- `OLIN_DATABASE_URL` using managed PostgreSQL and TLS.
- `OLIN_USERS` with unique 32+ character credentials and partner, analyst and admin separation.
- `OLIN_BANK_WEBHOOK_SECRETS` with institution-scoped current/retiring secrets.
- `OLIN_CONSENT_OTP_SECRET` for prospective applicant flows.
- `OLIN_KMS_KEY_ID` and database encryption attestation.
- `OLIN_BACKUP_RESTORE_EVIDENCE` referencing a completed restore ticket.
- `OLIN_REAL_DATA_SCOPE_REF` and `OLIN_DATA_PROCESSING_APPROVAL_REF`.
- `OLIN_INCIDENT_OWNER` and `OLIN_INCIDENT_CONTACT`.
- Explicit data classification and retention period.

## Fail-closed behavior

Startup is rejected when real-data mode points to SQLite, PostgreSQL TLS is not attested, managed storage cannot be reached, credentials are weak or duplicated, roles are incomplete, the webhook is unsigned, scope/processing references are absent, retention or incident ownership is missing, the source registry is not ready, or live lending is enabled.

Prospective data additionally requires a non-synthetic OTP delivery adapter and a strong OTP protection secret. This technical gate does not establish that a consent text or delivery method is legally sufficient.

## Evidence to return to the bank

- Approved Terraform plan and apply record.
- Immutable image digest and vulnerability report.
- Non-secret preflight JSON.
- `/readyz` response and ALB target-health evidence.
- Database encryption, backup and restore evidence.
- Named-user/role matrix without tokens.
- WAF, alert and incident runbook evidence.
- Synthetic signed-callback receipt, request ID and audit reconstruction.

No real dataset should be emailed, placed in chat or copied to a personal workstation.
