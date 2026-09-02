# Olin code review — bank evaluation baseline

Date: 2026-09-02

## Outcome

Olin is suitable for a controlled technical evaluation with synthetic or bank-provided, consented cases. It is not yet suitable for autonomous production lending, production money movement, or unsupported score-performance claims.

## Verified in this review

- Backend unit suite: 162 tests passed.
- Focused evidence-governance and peer-comparison suite: 19 tests passed.
- Python compilation and OpenAPI JSON parsing passed.
- Astro production build passed.
- Website static QA: 338 controls passed.
- Four route/viewport visual checks passed.
- No live credential was evidenced by the repository scan; example provider credentials remain identifiable as placeholders.

## New controls implemented

- `olin/evidence_governance.py` classifies every signal into candidate capacity, corroboration, context/stress, or research-only.
- Only verified, referenced capacity evidence can be eligible for a bank-approved shadow policy.
- No alternative signal may approve, decline, or move money by itself.
- `olin/business_comparison.py` produces aggregate, privacy-minimized DENUE peer context with minimum cohort size and small-cell suppression.
- Geointelligence output now carries governance metadata and a peer-comparison block.

## Priority findings

### P0 — required before a bank-controlled environment

1. Establish a clean, reproducible release baseline. The working tree contains extensive modified and untracked work; tag an reviewed commit, generate a dependency lock/SBOM, and build from CI.
2. Enforce the bank/Olin boundary in every API path. Legacy routes must not bypass consent, evidence classification, human review, or the bank-owned final decision.
3. Decompose `olin/server.py` and `olin/store.py`. The current HTTP handler and storage class are too large for safe change review and clear ownership.
4. Replace development persistence assumptions with a reviewed PostgreSQL schema and migrations; prove backup and restore.
5. Define production provider contracts: authentication, field mapping, rate limits, retries, idempotency, outage behavior, and permitted storage.
6. Add an immutable actor/event history suitable for access review and incident reconstruction.

### P1 — required before a production recommendation workflow

1. Centralize authorization with named roles, short-lived sessions, tenant isolation, and periodic access review.
2. Add structured logs, metrics, traces, alert ownership, and a tested kill switch.
3. Add SAST, dependency, secret, container, and infrastructure scanning to CI.
4. Add contract tests against bank sandboxes and replay-safe fixtures for every provider.
5. Create a formal outcome-data pipeline for decisions, overrides, delinquency, and observation windows.
6. Add model/data monitoring only after a sufficiently large, mature labeled cohort exists.

## Architecture judgment

The immediate product is an evidence-orchestration and analyst-support layer. Banco Azteca remains system of record for identity, bureau, policy, official decision, disbursement, collections, and complaints. This boundary is both the fastest implementation route and the safest answer to the bank's concern that the prior product was vague and over-claimed.

## Review caveat

Automated code-quality scoring was used to prioritize refactoring, not as a bank certification. A partner security review, privacy/legal review, credit/model-risk approval, and analyst UAT remain external gates.

