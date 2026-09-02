# Bank-grade target architecture

## Trust and responsibility boundary

```text
Merchant / bank channel
        |
        v
Bank API gateway + WAF + TLS/mTLS + rate limits
        |
        v
Olin partner API (Bearer identity, tenant scope, request ID)
        |
        +--> Consent + intake state machine
        +--> Provider adapters --> normalized derived evidence + provenance
        +--> Sector policy --> required evidence and review route
        +--> Versioned score + repayment capacity + safety gates
        +--> Recommendation API --> bank credit workflow
        |
        +--> append-only audit/outcomes/corrections

Managed Postgres     Object store/quarantine     Queue/DLQ
KMS/secrets manager  Central logs/metrics/alerts Backup/restore
```

The current implementation is a modular Python service with SQLite suitable for local UAT. Before real-data multi-instance operation, the persistence and operational plane must move to managed infrastructure. SQLite is not the production target.

## What the bank sees

- partner-scoped intake and consent state;
- evidence status, source, reference, and observation time;
- business segment, missing primary evidence, and routing policy;
- score, explicitly non-statistical sensitivity range, capacity metrics, reason codes, and engine version;
- Olin recommendation and recommended amount;
- correction trail and recommendation-versus-bank-outcome comparison.

## Internal layers the bank should govern but not operate

1. **Adapter layer:** converts provider payloads into a stable evidence contract and rejects raw transaction storage in the callback path.
2. **Provenance layer:** binds evidence to consent, provider, connection, timestamp, and immutable payload hash.
3. **Sector layer:** selects the evidence strategy for the business cash-flow pattern; it does not pretend one model fits every sector.
4. **Capacity layer:** evaluates repayment capacity separately from business quality.
5. **Safety layer:** hard filters, data coverage, fraud flags, portfolio caps, and committee routing.
6. **Governance layer:** score version, consent history, corrections, partner outcomes, and audit events.
7. **Learning layer:** monitored labeled outcomes used for later calibration; it cannot be activated from synthetic results.

## Evaluating different small businesses

Olin groups businesses by how cash becomes repayment evidence:

| Segment | Examples | Primary evidence | Risks requiring explicit review |
|---|---|---|---|
| Inventory retail | abarrotes, retail, wholesale | supplier purchases + bank flow | turnover, supplier concentration, invisible cash |
| Food/hospitality | restaurant, taquería, hotel | POS + bank flow | seasonality, spoilage/occupancy, platform concentration |
| Recurring services | beauty, education, healthcare | bank flow + POS | customer concentration, owner dependency |
| Project businesses | professional, construction | bank flow + identity/contract review | milestone delay, cost overrun |
| Asset/route | transport, logistics | bank flow + identity/asset review | downtime, fuel, contract concentration |
| Production/agriculture | manufacturing, agriculture | bank flow + supplier evidence | input cost, yield, seasonality |
| Digital commerce | ecommerce | platform/POS settlements + bank flow | returns, platform and advertising dependency |

All SME categories may enter the controlled shadow workflow when the bank's
cohort rule permits them. Every category, including `abarrotes`, remains
human-review decision support: the bank makes the official decision and no
shadow case may trigger money movement. Segment-specific automation is blocked
until real labeled performance and bank model-risk approval support it. The
legacy `pilot_auto_eligible` label means only that an abarrotes case may reach
the scorecard's recommendation route after its evidence gates; it never means
automatic bank approval.

## Production deployment requirements

- managed API gateway, TLS, optional bank mTLS, network allow-listing;
- managed Postgres with tenant isolation, encryption, PITR, and tested restoration;
- secrets manager/KMS with provider-scoped current and retiring webhook keys;
- durable queue and dead-letter path for asynchronous provider events;
- centralized logs, metrics, traces, paging, SIEM export, and immutable audit retention;
- SAST, dependency scanning, container scanning, external penetration test;
- documented RTO/RPO, incident roles, data retention/deletion, and vendor exit plan.

Do not add microservices before the operational need exists. A well-isolated modular service plus managed data and security controls is the lower-risk pilot architecture.
