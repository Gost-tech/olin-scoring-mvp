# Olin for Elektra — product and implementation plan

## Product decision

Do not pitch Olin to Elektra as a new lender, a replacement credit score or a complete loan-origination platform.

The recommended initial product hypothesis is:

> **Olin is an evidence and affordability decision-support adapter for existing Banco Azteca customers purchasing business-use equipment through Elektra's “Mi Negocio” catalogue. It helps the existing credit process review cases where documented income or business context is incomplete; Banco Azteca remains the sole decision maker.**

This hypothesis must be confirmed in discovery. It is based only on public information: Elektra offers a “Mi Negocio” equipment catalogue, Préstamo Elektra is Banco Azteca Credimax, and Grupo Elektra publicly prioritizes improving digital credit origination and credit use across formal and informal businesses.

## Why Elektra could need it

The relevant problem is not “Elektra cannot score people.” Banco Azteca already has a very large customer, repayment, channel and collections footprint.

The possible gap is narrower:

- A customer is known to Banco Azteca but the requested purchase has a productive/business purpose.
- Existing consumer-credit data may not describe the incremental repayment capacity created by that equipment.
- The case may require manual review or additional evidence.
- Olin can normalize the permitted business evidence, explain what is missing and produce an affordability view for the existing decision process.

If Elektra cannot identify this cohort, its current baseline and an accountable credit owner, stop the project. A generic score has no credible value proposition.

## First use case

### User

Banco Azteca credit strategy/operations analyst reviewing an existing customer who wants to use approved credit for an Elektra “Mi Negocio” product.

### Trigger

An Elektra or Banco Azteca system sends an authorized shadow-assessment request for a defined cohort. Olin is never invoked directly from public checkout in the first phase.

### Minimum inputs

- Pseudonymous Elektra/Banco Azteca customer reference.
- Application and existing credit-line reference.
- Cart/SKU, price, category and declared business purpose.
- Bank-approved derived repayment/history features.
- Bank-approved derived income/cash-flow features, if available.
- Existing decision and reason code for retrospective evaluation.

No bank username/password, raw open-banking credential, payment initiation instruction or unnecessary identity document enters Olin.

### Output

- `assessment_id`, model/policy version and trace ID.
- `route`: insufficient evidence, manual review, or evidence-supported review.
- Affordability/capacity calculation under Elektra-defined assumptions.
- Missing-evidence list and machine-readable reason codes.
- Evidence provenance summary.
- Explicit `decision_support_only=true` and `official_decision_required=true`.

Olin must not return `approved`, create a credit line or alter checkout.

## Success metric

Primary metric: **incremental reviewable coverage for the agreed incomplete-evidence cohort without bypassing Banco Azteca policy.**

Proposed pilot targets to negotiate, not current claims:

- At least 99.5% technically valid records processed without manual data repair.
- 100% traceable inputs, policy version, reasons and bank outcome.
- At least 30% reduction in analyst handling time for the selected cohort.
- Zero official decisions or money movements initiated by Olin.
- Zero cross-customer exposure, consent/authority bypass or critical/high unresolved security finding.
- A jointly agreed coverage or decision-quality threshold defined after the historical baseline.

Do not set an approval-rate or loss-rate target until Elektra supplies a representative labeled cohort and defines the observation window.

## Discovery inputs required from Elektra

These are integration requirements, not sales questions:

1. Which exact decision or operational queue is currently slow, rejected or unscorable?
2. Is the target Credimax usage, credit-line increase, a business-purpose loan, or another product?
3. Which legal entity owns the decision and which system is the system of record?
4. What existing customer, cart, credit, repayment and business-purpose fields are available?
5. What is the baseline volume, handling time, approval/decline/pending mix and mature outcome definition?
6. Which fields may leave Elektra's boundary, or must Olin run inside it?
7. What identity, API gateway, event bus, cloud, SIEM and deployment standards are mandatory?
8. Who owns product, credit policy, model risk, security, privacy, integration and operations?

If those answers are unavailable, the only valid next step is a discovery workshop—not software deployment.

## Target architecture

Use a small, PostgreSQL-native modular monolith:

```text
Elektra/Banco Azteca source system
        |
        | approved API/event + workload identity
        v
API contract / idempotency / schema validation
        |
        v
Application workflow service
   | evidence normalization
   | Elektra policy adapter
   | affordability assessment
   | reason-code generation
        |
        +--> PostgreSQL: request, evidence references, assessment, audit events
        |
        +--> Elektra decision callback/export (official decision remains external)
        |
        +--> metrics, traces, alerts and SIEM
```

Recommended implementation baseline, subject to Elektra standards:

- Python 3.12 with FastAPI/Pydantic for the API and domain application layer.
- PostgreSQL with SQLAlchemy and Alembic migrations.
- Elektra-approved OIDC/OAuth2 or mTLS/workload identity; no Olin employee password store.
- OpenTelemetry-compatible traces, structured logs and bank-supplied correlation IDs.
- AWS managed runtime only if Elektra approves it; otherwise package the service for its platform.
- No microservices, Kafka, Kubernetes or custom ML platform unless Elektra's target environment requires them.

## Delivery plan

### Phase 0 — product fit and system discovery

**Outcome:** one signed problem statement and integration context.

Deliverables:

- Current Elektra journey and system-of-record map.
- Named target cohort and exclusion rules.
- Baseline metrics and outcome label.
- Data classification and allowed-field inventory.
- One-page product requirements document.
- Architecture constraints and responsible owners.

Exit gate: Elektra product and credit owners confirm why the adapter is needed and how value will be measured. Without that confirmation, stop.

### Phase 1 — release reset and contract

**Outcome:** clean, reviewable repository and API contract.

Deliverables:

- Clean branch/tag containing only the Elektra service and its tests.
- Quarantine list for legacy/demo modules.
- Elektra request/response schemas and reason-code catalogue.
- Architecture decision records, threat model and data-flow diagram.
- CI gates for formatting, linting, typing, tests, coverage, migrations and security scans.

Exit gate: a fresh clone produces the same signed artifact and software bill of materials in CI.

### Phase 2 — thin vertical slice

**Outcome:** one synthetic Elektra-shaped case processed end to end.

Deliverables:

- Maintained API framework and PostgreSQL-native persistence.
- OIDC/workload identity integration stub approved by Elektra architecture.
- Idempotent assessment endpoint and immutable audit events.
- Policy configuration owned by Elektra, not hard-coded Olin thresholds.
- Structured reason codes, metrics and distributed trace.
- Exception assignment and resolution workflow.

Exit gate: Elektra sends one synthetic request from its sandbox, receives a deterministic shadow response and reconstructs the transaction from its SIEM/audit records.

### Phase 3 — historical validation

**Outcome:** demonstrate whether the product adds information or saves work.

Deliverables:

- Representative, pseudonymized and labeled historical cohort selected by Elektra.
- Data-quality report, exclusions and leakage review.
- Baseline-versus-Olin coverage, handling-time simulation and reason analysis.
- Segment/proxy/fairness review appropriate to the decision use.
- Recommendation to continue, modify or stop.

Exit gate: credit/model risk accepts the evidence for a shadow test. Ten hand-selected examples are not sufficient for this gate; sample size must be determined from the target cohort and outcome frequency.

### Phase 4 — controlled shadow integration

**Outcome:** run beside the existing process without affecting customers or credit.

Deliverables:

- Production-like integration, SLO dashboards, paging and runbooks.
- Named daily exception owner and kill-switch exercise.
- Official Elektra decision and override returned for every eligible assessment.
- Joint operational report and rollback evidence.

Exit gate: product, credit risk, model risk, security, privacy, architecture and operations provide written evidence-based approval for the next stage.

### Phase 5 — decision on productization

Only after the shadow results:

- Stop if the cohort is too small, Olin adds no coverage or handling time does not improve.
- Iterate if evidence quality or workflow—not policy value—is the main constraint.
- Productize only if Elektra demonstrates measurable value and approves the operating/control model.

No autonomous credit decision or money movement is included in this plan.

## Team and ownership

### Elektra/Banco Azteca

- Product owner for the selected journey.
- Credit-policy owner.
- Model-risk validator.
- Integration architect/engineer.
- Security and privacy reviewers.
- Operations owner.

### Olin

- Product/engagement lead.
- Senior backend/architecture lead.
- Backend engineer.
- QA/DevSecOps engineer.
- Mexican counsel/compliance support for documents and data flow.

This cannot be credibly delivered to Elektra as an unreviewed founder-only codebase. The first hiring/contracting priority is a senior engineer who can own the clean service, code review and Elektra integration with Brice.

## Explicit non-goals

- Replacing Banco Azteca's core decision engine.
- Building a new Elektra checkout.
- Collecting bank credentials or duplicating KYC.
- Moving money, disbursing or collecting.
- Training an ML model before a representative labeled dataset and model-risk plan exist.
- Supporting every SME, bank, evidence source and lending product in the first release.

