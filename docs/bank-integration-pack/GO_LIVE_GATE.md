# Go-live gate

## Current verdict

| Stage | Verdict | Permitted data/action |
|---|---|---|
| Local demonstration | GO | synthetic data only |
| Bank synthetic UAT | GO | bank-created fake cases and sandbox credentials |
| Shadow pilot | CONDITIONAL GO | only after bank security/privacy approval; bank makes every decision |
| Real-data production | NO-GO | blocked until all gates below have evidence |
| Autonomous lending/disbursement | NO-GO | not the current product scope |

## Gates requiring external or deployment evidence

- [ ] Bank and data-provider commercial agreements, sandbox credentials, and certification are complete.
- [ ] Bank-approved consent text, privacy notice, DPA, purposes, retention, deletion, and data-subject workflow are signed off.
- [ ] A deployed HTTPS sandbox passes bank network, authentication, tenant-isolation, replay, and rate-limit tests.
- [ ] SQLite has been replaced by managed Postgres for real data; encryption, backups, restore, and failover are evidenced.
- [ ] Secrets live in KMS/secrets manager; rotation and emergency revocation are demonstrated.
- [ ] Central monitoring, SIEM export, paging, incident runbooks, RTO/RPO, and on-call ownership are operating.
- [ ] SAST/dependency/container scans and an independent penetration test have no unresolved critical/high findings.
- [ ] Historical labeled outcomes are backtested by segment; thresholds, fairness, drift, override, and loss limits are approved by bank risk.
- [ ] Bank credit policy names the official decision owner and records reason codes, adverse-action handling, and manual escalation.
- [ ] Operational SLA, support path, vendor inventory, subcontractor approval, and exit/data-return plan are accepted.

Legal permission to offer a product does not automatically satisfy a bank's vendor, privacy, model-risk, and production-control gates. Owners must attach evidence, approver, and date to each item; a verbal “ready” is not sufficient.
