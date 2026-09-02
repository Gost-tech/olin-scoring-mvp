# Olin technical audit for an Elektra conversation — 2026-09-01

## Verdict

**BLOCK for Elektra deployment. REQUEST CHANGES for technical evaluation.**

Olin contains useful experiments, domain logic and safety tests, but it is not currently an enterprise-deliverable product. The bank feedback that it appears “vibe-coded” is supported by the repository structure, change-control state, custom infrastructure primitives and incomplete production journey. Passing local behavior tests does not cure those problems.

This review is a code/product engineering assessment, not an independent penetration test, model validation or legal opinion.

## Evidence summary

| Finding | Evidence | Consequence |
|---|---|---|
| The reviewed version is not reproducible | Working tree contains 65 modified and 105 untracked paths. Only 30 `olin/*` paths and 5 root tests are tracked, while the workspace contains 51 Python modules and 32 root tests. | Elektra cannot clone the locally tested product or audit a stable release. CI does not validate untracked files. |
| Backend is a prototype monolith | `olin/server.py` is 4,094 lines and embeds HTML/CSS/JavaScript in a Python string. `do_POST` is approximately 768 lines. | Routing, presentation, authentication and business workflows are coupled; changes have high regression risk. |
| Persistence is unsafe to evolve | `olin/store.py` is 1,462 lines, initializes schema at runtime and translates SQLite SQL into PostgreSQL with string replacement. There is no Alembic migration history. | Database changes are difficult to review, roll back and prove across environments. PostgreSQL semantics are not guaranteed by SQLite compatibility tests. |
| Authentication is home-grown | Named users, static JSON credentials and proprietary HMAC session tokens are implemented locally. | It does not meet a normal enterprise integration expectation for OIDC/SSO, MFA, corporate user lifecycle, centralized revocation and identity-provider audit. |
| Production UI and production API disagree | The principal intake UI posts directly to `/api/applications`; production rejects that path and requires a verified intake consent receipt. | A bank operator cannot complete the approved process through the product interface. |
| Operations are incomplete | The control room is explicitly read-only and cannot acknowledge, assign, escalate or resolve an exception. | There is no executable operating process or SLA evidence. |
| Product scope is mixed | Shadow decision support coexists with legacy STP, disbursement, collections, waitlist, marketing and multiple provider experiments. | Elektra cannot identify the supported product boundary or its attack surface. |
| Engineering quality gates are incomplete | CI runs behavior tests but no formatter/linter, static typing, coverage threshold, migration validation, SAST, dependency policy or container scan. | “155 tests passed” is not a maintainability or security assurance. |
| Automated quality signals are weak | A heuristic scan of 51 Python modules produced grade C, 824 smells and 14 SOLID warnings; `server.py` and `store.py` scored F due to size and complexity. | The exact counts are heuristic, but they correctly identify the two highest-risk concentration points. |
| External connectors are experimental | Syncfy includes direct credential APIs, polling and swallowed network exceptions; real hosted-provider certification is absent. | The connector is unsuitable for an Elektra integration without vendor approval, error contracts and production certification. |
| Model evidence is insufficient | The current engine is a rules scorecard tested mostly on synthetic cases. | It cannot be presented as an Elektra credit model or as evidence of predictive lift. |

## Highest-risk code findings

### P0 — release integrity

There is no reviewable release containing the code, tests, infrastructure and documentation claimed in the local demo. Before any technical meeting, create a clean branch from `main`, decide exactly which files belong to the product, commit them through review and produce a tagged build from CI. Do not send the current working directory as a deliverable.

### P0 — undefined Elektra product boundary

The repository attempts to be an origination app, alternative-data system, scoring engine, analyst desk, consent manager, provider connector, operations console, waitlist and lending simulator. Elektra needs one integration capability with a named owner, input contract, output contract and measurable business outcome.

### P0 — unsafe architecture concentration

`server.py` and `store.py` are change hotspots and single points of technical ownership. The target should remain a modular monolith, but HTTP routing, domain services, persistence, integrations and presentation must be separated. This is a controlled extraction, not a microservices rewrite.

### P0 — database lifecycle

Replace runtime schema mutation and the SQLite-to-PostgreSQL translation shim with PostgreSQL-native models, reviewed migrations, connection pooling, transaction boundaries and migration rollback testing. SQLite may remain only for isolated unit tests if parity is explicit.

### P0 — enterprise identity

Replace local employee authentication with Elektra-approved OIDC/OAuth2. Service-to-service calls should use Elektra-approved workload identity or mTLS. Olin must not become another employee identity store.

### P1 — workflow integrity

Implement one authoritative state machine with idempotent transitions, ownership, timestamps, reason codes and an append-only event history. The frontend and API must use the same application service; no legacy direct path should bypass authorization.

### P1 — engineering governance

Add a `pyproject.toml`, formatter/linter, type checking, coverage threshold, conventional migrations, API compatibility tests, secret/dependency/container scanning, CODEOWNERS, architecture decisions and a release checklist. Every claimed test must run from a clean clone.

## Keep, quarantine and replace

### Keep after review

- Explainable scoring concepts and reason-code vocabulary.
- Evidence provenance and idempotent callback tests.
- Separation between Olin recommendation and official bank decision.
- Live-money kill switch and synthetic portfolio tests.
- OpenAPI examples that survive the narrowed Elektra contract.

### Quarantine outside the Elektra service

- STP, disbursement, collections and graduation modules.
- Waitlist and public marketing application code.
- Belvo/Syncfy direct-credential prototypes.
- Demo seeders, videos and synthetic UI experiments.
- Generic multi-bank features not required by the first Elektra use case.

### Replace before enterprise UAT

- Custom HTTP server with a maintained application framework.
- Embedded HTML analyst interface with an API-only integration or a separately built internal UAT client.
- Custom employee sessions with approved OIDC/SSO.
- Runtime schema initialization with versioned PostgreSQL migrations.
- Read-only exception projection with a real operational task workflow.
- Environment-variable JSON user directory with centralized identity and secrets.

## Technical evaluation exit criteria

Olin should return to Elektra technical review only when:

1. A clean clone builds and passes every gate without local-only files.
2. One Elektra use case and one system owner are named.
3. The API contract contains no generic loan-origination features outside that use case.
4. PostgreSQL migrations upgrade and roll back in CI.
5. OIDC/service identity and tenant boundaries are demonstrated.
6. One synthetic Elektra event travels end to end with trace ID, idempotency and audit reconstruction.
7. SAST, dependency, secret and container scans have no unresolved critical/high findings.
8. Operations can assign, acknowledge, resolve and report an exception.
9. Architecture, data flow, threat model, SLOs and rollback are approved by named reviewers.
10. The product makes no predictive or business-lift claim without Elektra data.

