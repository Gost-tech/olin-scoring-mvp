# Project state — Olin × Elektra

**Updated:** 2026-09-01

## North star

Deliver one credible evidence/affordability decision-support adapter for Elektra/Banco Azteca technical evaluation. The bank remains the official decision maker.

## Current status

- Product hypothesis: defined, pending Elektra discovery confirmation.
- Existing prototype: useful domain experiments, blocked for enterprise deployment.
- Clean evaluation service: not yet implemented.
- Predictive model: not trained or validated for Elektra.
- Real-data authorization: not yet evidenced in the repository.
- Week-one target: sandbox technical evaluation, not production.

## Frozen decisions

- API-first modular monolith; no microservice rewrite.
- PostgreSQL + migrations; no runtime schema mutation or SQL translation shim.
- Elektra identity integration; no Olin employee password store.
- Decision support only; no approval/decline or money movement.
- Synthetic data until formal data/security gates pass.
- Interpretable baseline before any boosted-tree challenger.

## Top blockers

1. Current working tree is not a reproducible release.
2. Exact Elektra journey and system of record require internal confirmation.
3. Elektra architecture, identity and deployment standards are unknown.
4. Outcome label, observation window and representative cohort are undefined.
5. Named credit, model-risk, security, integration and operations owners are required.

## Required reads before changing Elektra scope

- `docs/elektra-next-week/report-source.md`
- `docs/elektra-next-week/execution-backlog.md`
- `docs/ELEKTRA_TECHNICAL_AUDIT_2026-09-01.md`
- `docs/ELEKTRA_PRODUCT_IMPLEMENTATION_PLAN.md`

## Memory rule

Record material product/architecture decisions here before implementing them. Never store credentials, personal data or secrets in project memory.
