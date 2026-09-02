# Olin production integration map

This is the minimum connection map for an institution-led product. Vendor names
are evaluation candidates, not current partners.

| Capability | Product candidate | Olin status | Required before |
|---|---|---|---|
| Partner case intake | Olin API + partner webhook/CSV adapter | Working API; CSV import not built | Parallel pilot |
| Identity and business verification | Incode/MetaMap or partner KYC | Fields only; no live verification | Any real applicant |
| Credit bureau | Círculo de Crédito | Model and consent record exist; no live contract | Real recommendation |
| Bank cash flow | Syncfy or Finerio Connect | Adapter/mock logic only | Bank-flow route |
| POS settlements | Partner acquirer/Monex Host-to-Host or API | Schema and synthetic scenario only | TPV route |
| Supplier purchases | Distributor API, invoice feed or verified upload | Schema and synthetic scenario only | Inventory route |
| Business location | Google Places API | Not live in deployed pilot | Optional supporting evidence |
| Evidence documents | Encrypted object storage + checksum + retention policy | Missing | Real case files |
| Electronic signature | Mifiel/DocuSign, selected with counsel | Missing | Contracts or mandates |
| Enterprise identity | Auth0/WorkOS/managed IdP with MFA and audit log | Static named tokens | External production users |
| System of record | Managed Postgres, backups and encryption keys | SQLite | Production persistence |
| Monitoring | Sentry/Datadog or equivalent, alert routing and runbooks | File/email alerts only | Production SLA |
| Outcome feed | Partner decision and repayment webhooks | Decision endpoint works; repayment partner feed not live | Backtest/live learning |
| Disbursement and servicing | Partner lender/LMS/payment rail | Legacy STP simulation exists; globally disabled | Separate live-lending approval |

## Recommended architecture boundary

Olin should own:

- case normalization;
- source provenance and evidence quality;
- policy execution;
- explainable recommendation;
- analyst rationale;
- partner and repayment outcome labels;
- versioned exports and monitoring.

The partner should initially own:

- customer relationship and legally approved disclosures;
- KYC/AML acceptance;
- formal underwriting decision;
- pricing and contract;
- funding;
- money movement;
- servicing, collections and complaints;
- regulatory reporting.

## Integration order

1. Enterprise auth and managed Postgres.
2. One partner case/outcome adapter.
3. Círculo with versioned consent.
4. The partner's highest-coverage operating source: POS, bank flow or supplier
   history. Do not integrate all three before measuring coverage.
5. Encrypted evidence storage and audit export.
6. A second operating source only if the first pilot shows a material coverage
   or decision gap.

No payment rail should be enabled during a shadow pilot.
