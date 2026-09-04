# Investigator V1 Phase 0 Forbidden Surface

The application-policy inventory and enforcement source is
`config/investigator-authority-v1.json`. This reviewed inventory explains why
each surface is unavailable to the Investigator deployment. Default is deny;
an omitted capability is not permitted.

## Python and service surface

| Surface | Forbidden authority |
|---|---|
| `olin.server` and `olin.api.cases` | combined legacy scoring, decision, outcome, export, provider, and money routes |
| `olin.store.ScoringLog` | writes decisions, outcomes, disbursement claims, payments, and mixed-authority records |
| `olin.stp.disburse` | SPEI money movement and private-key use |
| `olin.collection` payment/default functions | collection, repayment, and outcome mutation |
| `olin.portfolio.check_portfolio` | portfolio credit gate |
| `olin.graduation.get_graduation_offer` | authoritative offer/limit progression |
| `olin.repayment` | affordability and repayment policy outputs |
| `olin.scorecard.score_application` | approve/committee/decline, amount, and price outputs |
| `olin.capacity_v2.calculate_capacity` | proposed amount, term, rate, and DSCR output |
| `olin.fraud` | unvalidated operational fraud authority |
| `olin.evidence_passport` mutators | verification registration/revocation authority |
| Belvo, Syncfy, Places, DENUE, geo, weather | provider/network acquisition not authorized in Phase 0 |

Static boundary tests reject direct and relative imports from these modules
under `olin/investigator/`. Future read-only adapters must be separately
reviewed and explicitly added to the positive allowlist.

## Routes

The Phase 0 Investigator has no HTTP routes. In particular it cannot register
legacy application/scoring, analyst decision, partner outcome, disbursement,
STP webhook, intake scoring, bank webhook/link exchange, or evidence-provider
routes. It must later use a dedicated entry point rather than `olin.server`.

## Database

The runtime role receives only `SELECT` on
`investigator.investigation_case` and `investigator.investigation_event`, plus
`EXECUTE` on the constrained create/append functions and three tenant-policy
helpers. The migration aborts if the runtime inherits non-Investigator schema
creation, relation access, or routine execution. It receives no direct
table mutation privilege and no privilege on the existing `public` tables,
including `scoring_log`, `payment_ledger`, performance, evidence, consent,
authorization, correction, ingestion, or intake tables. Evidence and consent
will later be exposed only through narrow tenant-bound read interfaces.

## Credentials and environment

The Investigator environment uses the contract's small positive allowlist.
Everything else—including STP, live-lending controls, collection webhook
signing, legacy shared users/API keys, bank evidence webhooks, provider tokens,
LLM/tool credentials, and unreviewed future variables—fails closed without
logging values. The legacy `.env` must never be copied wholesale.

## Jobs, queues, and network

No queue framework exists in the current repository. Investigator cannot run
the daily collection/default job or any scoring, disbursement, repayment,
graduation, provider, evidence-acquisition, or AI worker. Phase 0 requires no
outbound network capability beyond its tenant-bound PostgreSQL connection and
deployment observability. STP, bank LOS writes, provider endpoints, link/
webhook ingestion, LLM endpoints, and general Internet egress are forbidden.

## Trust and identity

Caller-supplied `verified`, `trusted`, `authoritative`, or `issuer_validated`
labels are untrusted input. A tenant is derived from an authenticated,
database-provisioned login binding and must match transaction-local context;
tenant identifiers in bodies, paths, queries, headers, or event payloads cannot
create authority. The runtime role cannot own schema objects, create roles,
bypass RLS, grant permissions, alter policies, or access credentials.
