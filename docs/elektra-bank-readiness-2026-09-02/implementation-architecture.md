# Olin × Elektra implementation architecture

## Product boundary

Olin is an evidence-orchestration and capacity-recommendation service for controlled bank evaluation. Banco Azteca remains system of record for identity, bureau, credit policy, official decision, money movement, collections and complaints.

```text
Applicant / branch / bank channel
            |
            v
Banco Azteca controls: KYC + consent + bureau + case reference
            |
            v
Olin intake gateway
  -> tenant/auth boundary
  -> schema + idempotency validation
  -> consent/evidence-reference checks
            |
            v
Evidence Passport
  -> bank cash-flow / POS / supplier / fiscal / receivables
  -> public registry + place corroboration
  -> contextual geo/weather adapters
  -> source, time, version, quality and permitted-use envelope
            |
            v
Capacity engine + bank policy adapter
  -> stressed capacity scenarios
  -> missing-evidence alternatives
  -> recommendation + reason codes
  -> never an official decision
            |
            v
Banco Azteca analyst / policy engine
  -> approve / decline / refer / override
            |
            v
Outcome return
  -> decision + reason + repayment window + delinquency
  -> validation, monitoring and audit
```

## API sequence

1. `POST /api/v1/intakes` — bank creates a partner-scoped intake with its case reference.
2. Consent references are attached or a bank-approved Olin consent challenge is completed.
3. Provider evidence is linked through one-time sessions or signed webhooks.
4. `POST /api/v1/intakes/{id}/score` — Olin freezes the evidence snapshot and creates a recommendation package.
5. Banco Azteca records its decision and reason.
6. Performance events and repayment outcomes return over the agreed observation window.

## External layer roadmap

| Layer | Adapter state | Production dependency | Bank-facing use |
|---|---|---|---|
| Bank cash-flow features | Implemented contract and signed webhook path | Bank mapping, secrets, test certificates and sample payloads | Capacity evidence |
| POS / payment settlements | Contract surface exists | Acquirer/PSP agreement and mapping | Capacity evidence |
| Supplier / invoice evidence | Evidence Passport route exists | Partner feed or controlled verification SOP | Capacity evidence |
| INEGI DENUE | Connector and snapshot logic implemented | INEGI token and rate-limit monitoring | Corroboration / context |
| Google Places | Connector implemented | API key, contractual review, attribution UI | Corroboration only |
| Weather | Open-Meteo adapter implemented | Commercial-use plan/SLA decision | Stress context only |
| Public peer comparison | Implemented aggregate benchmark | Minimum cohort and sector-owner review | Market context only |
| Licensed footfall | Interface/catalog only | Vendor procurement and Mexico coverage test | Context experiment only |
| VIIRS/Sentinel | Interface/catalog only | Tile pipeline, spatial aggregation, baselines | Offline research only |
| Social business presence | Deliberately not scraped | Official API, merchant authorization, legal/model-risk approval | Offline research only |

## Seven-day technical-evaluation plan

Day 1: freeze scope, data dictionary, decision boundary, owners and synthetic fixtures.

Day 2: map Banco Azteca case/evidence payloads to the versioned intake and evidence contracts.

Day 3: configure isolated environment, named credentials, secrets, TLS, encrypted storage and audit export.

Day 4: run integration tests, idempotency/replay cases, provider outage tests and consent withdrawal.

Day 5: historical sample replay; reconcile every case and reason code with the bank data owner.

Day 6: analyst UAT with synthetic and approved historical cases; measure time, evidence gaps and usability.

Day 7: joint go/no-go for a 10-case shadow pilot. No live decision automation and no money movement.

## Acceptance gates

- Partner data dictionary and sample payload accepted.
- Authenticated tenant isolation and named-user audit verified.
- Consent/bureau purpose and reference mapping approved.
- Evidence provenance, retention and deletion behavior demonstrated.
- Recommendation replay is deterministic for the frozen version.
- Provider outage and partial-evidence behavior do not create favorable defaults.
- Bank policy owner approves reason codes and stop conditions.
- Security, privacy/legal, credit risk, model risk and analyst UAT owners sign the evaluation gate.

