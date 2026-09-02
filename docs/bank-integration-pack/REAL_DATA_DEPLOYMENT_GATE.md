# Real-data deployment gate

`OLIN_REAL_DATA_ENABLED` is off by default. Local SQLite is permitted only for synthetic/test data.

Before real bank evidence is enabled, operations must provide:

- `OLIN_DATABASE_URL` for managed PostgreSQL over TLS.
- `OLIN_KMS_KEY_ID` for envelope encryption of sensitive payloads.
- `OLIN_DATABASE_ENCRYPTION_AT_REST=attested` backed by provider evidence.
- `OLIN_BACKUP_RESTORE_EVIDENCE` referencing a successful restore exercise.
- Tenant/RLS tests, least-privilege service accounts, secret rotation, monitoring, paging and retention/deletion jobs.

The service fails readiness and case creation when real-data mode is enabled without these controls. `docs/postgres-shadow-schema.sql` is the target schema boundary; it is not proof that managed infrastructure exists.
