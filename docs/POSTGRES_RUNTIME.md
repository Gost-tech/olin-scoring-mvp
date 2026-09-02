# Production persistence and money gate

Real-data mode uses the managed PostgreSQL URL, never a local SQLite file. The
runtime connection boundary is `olin.store.connect_database`; it is used by
`ScoringLog` and the HTTP read paths so a production process cannot silently
read one database and write another. The schema is initialized from the
application's versioned schema and must be deployed to the AWS RDS PostgreSQL
16 instance declared in `infra/aws`.

Required production settings:

```text
OLIN_MODE=production
OLIN_REAL_DATA_ENABLED=1
OLIN_DATABASE_URL=postgresql://...
OLIN_KMS_KEY_ID=...
OLIN_DATABASE_ENCRYPTION_AT_REST=attested
OLIN_BACKUP_RESTORE_EVIDENCE=...
```

The readiness endpoint remains NO-GO until the driver is installed, the RDS
connection succeeds, encryption and restore evidence are attested, and the
schema migration has completed. No credentials belong in this repository.

## Real-money lending is a separate gate

The STP/SPEI connector is production-capable but disbursement remains disabled
by default. Enabling it requires production PostgreSQL readiness, STP
production credentials and mTLS files, a webhook secret, a cleared kill switch,
and two distinct recorded approvers:

```text
OLIN_LIVE_LENDING_ENABLED=1
OLIN_LIVE_LENDING_KILL_SWITCH=0
OLIN_LIVE_LENDING_APPROVAL_REF=...
OLIN_LIVE_LENDING_APPROVED_BY=...
OLIN_LIVE_LENDING_SECOND_APPROVER=...
STP_SANDBOX=0
```

These settings are operational approvals, not development defaults. Until they
are supplied and verified against a controlled provider test, every disburse
request returns a fail-closed response and no money moves.
