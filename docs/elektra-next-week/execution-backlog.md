# Seven-day execution backlog

## Release objective

Produce a reproducible Elektra sandbox technical-evaluation artifact for one synthetic evidence/affordability assessment. This backlog does not authorize real-data ingestion or official credit decisions.

## P0 — must finish

- [ ] `REL-001` Freeze scope and publish product/non-goal statement. Owner: Product. Day 1.
- [ ] `REL-002` Create clean Elektra service branch from tracked source. Owner: Tech lead. Day 1.
- [ ] `REL-003` Lock dependencies and prove clean-clone build. Owner: DevSecOps. Day 1.
- [ ] `API-001` Freeze versioned request/response/error schemas. Owner: Backend. Day 1.
- [ ] `ARC-001` Approve modular-monolith, data-flow and identity ADRs. Owner: Tech lead. Day 1.
- [ ] `DB-001` Add PostgreSQL schema and Alembic migration. Owner: Backend. Day 2.
- [ ] `DB-002` Test upgrade/rollback/upgrade against PostgreSQL. Owner: Backend. Day 2.
- [ ] `WF-001` Implement assessment state machine and invariant tests. Owner: Backend. Day 2.
- [ ] `WF-002` Enforce idempotency and append-only audit history. Owner: Backend. Day 2.
- [ ] `POL-001` Implement versioned bank-policy adapter. Owner: Credit + Backend. Day 3.
- [ ] `POL-002` Prohibit approval/decline output in code and contract tests. Owner: QA. Day 3.
- [ ] `EVD-001` Implement provenance, freshness and missing-evidence alternatives. Owner: Backend. Day 3.
- [ ] `IAM-001` Implement sandbox JWT verification and production identity boundary. Owner: Security. Day 4.
- [ ] `IAM-002` Test role, customer and tenant isolation. Owner: Security + QA. Day 4.
- [ ] `OBS-001` Add JSON logs, metrics, traces and correlation IDs. Owner: DevSecOps. Day 4.
- [ ] `SEC-001` Complete threat model and security test cases. Owner: Security. Day 4.
- [ ] `CI-001` Add lint, format, types, tests and coverage gate. Owner: DevSecOps. Day 5.
- [ ] `CI-002` Add secret, dependency, SAST and image scans. Owner: DevSecOps. Day 5.
- [ ] `BLD-001` Generate OCI image, SBOM and checksum in CI. Owner: DevSecOps. Day 5.
- [ ] `E2E-001` Run golden synthetic request end to end. Owner: QA. Day 5.
- [ ] `OPS-001` Prove timeout, replay, duplicate and malformed-event handling. Owner: Ops + QA. Day 6.
- [ ] `OPS-002` Prove alert, assignment, acknowledgement, resolution and kill switch. Owner: Ops. Day 6.
- [ ] `OPS-003` Run backup/restore exercise in evaluation environment. Owner: DevSecOps. Day 6.
- [ ] `DEMO-001` Package 15-minute technical review and evidence index. Owner: Product. Day 7.
- [ ] `DATA-001` Agree historical-data schema, label owner and observation window. Owner: Elektra Credit. Day 7.

## P1 — finish if P0 is green

- [ ] Add OpenAPI breaking-change detection.
- [ ] Add a minimal operator queue for failed assessments.
- [ ] Capture evaluation load and latency baseline.
- [ ] Add signed build provenance if the selected CI supports it.
- [ ] Produce Spanish API/operator glossary.

## Hard stop conditions

- Real personal or credit data is offered before the data/security approvals exist.
- Product scope expands to KYC, approval, disbursement, collections or public checkout.
- The build depends on untracked local files or manual database creation.
- A critical/high security finding is waived without named Elektra approval.
- Anyone asks the team to claim predictive lift before representative outcome validation.

## Daily proof packet

Each day ends with: commit SHA, CI link or local reproducibility evidence, tests/scans, decisions, new risks, next owner and a five-minute demo. A task is not done because code exists locally.
