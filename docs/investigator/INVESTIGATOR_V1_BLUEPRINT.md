# OLIN Investigator V1 Blueprint

Status: approved architecture, frozen for incremental implementation  
Approved base: `4cf39e80abe3252cc089d0e03a41f6d781a4841b`  
Boundary: production-quality research and Second-Look shadow work, never autonomous credit or money authority

## 1. Product boundary

V1 serves one bank, one defined SME cohort, and declined, incomplete, or
borderline Second-Look cases. It is read-only with respect to bank, LOS,
lending, pricing, disbursement, repayment, collection, and verified-evidence
authority. OLIN may persist its own investigation history, snapshots, research
artifacts, human reviews, and outcome observations.

V1 does not replace a LOS, make an authoritative score, approve or decline,
set price or terms, disburse, collect, run a production geo/fraud score, train a
large model, crawl the web autonomously, or provide a generalized agent
framework. The bank remains the sole decision and monetary authority.

```text
Authorized evidence acquisition
  -> quarantine / consent / issuer validation
  -> canonical Evidence Passport
  -> Case / Claim / Evidence relationships
  -> immutable CaseSnapshot
  -> deterministic reconciliation
  -> human investigation planning and next action
  -> new evidence -> new CaseSnapshot -> repeat or stop
  -> human-reviewed Analyst Brief + Audit Annex
  -> non-authoritative structure questions
  -> authorized bank decision -> outcomes -> learning
```

One PostgreSQL database and one modular monorepo are sufficient. Investigator
uses a separate entry point, database role, secret set, and deployment boundary.
A separate acquisition service is justified only when live external acquisition
is later authorized.

## 2. Canonical records

The minimum durable records are:

1. `InvestigationCase`: mutable, non-authoritative projection of identity,
   tenant, partner/cohort reference, and event-head version.
2. `InvestigationEvent`: append-only lifecycle and audit history.
3. `CaseSnapshot`: immutable canonical reasoning input at a specific event head.
4. `InvestigationArtifact`: immutable, versioned assessment/brief/annex artifact.
5. `ArtifactEvidenceLink`: proposition-level link to canonical Passport evidence.
6. `BankOutcomeEvent`: authenticated, bank-owned outcome with append-only corrections.

Only the first two records belong in Phase 0. Evidence remains authoritative in
the existing Evidence Passport and consent/source-trust infrastructure; V1 must
not duplicate or rewrite it.

Initially embed Entity references, Claims, Propositions, Inferences, Estimates,
Hypotheses, Contradictions, Unknowns, InvestigationActions, ActionResults,
CapacityScenarios, candidate FacilityScenarios, and HumanReview in versioned
artifacts. Promote an item to its own table only when independent lifecycle or
query needs are observed. OLIN creates no credit `DecisionRecord`; the bank's
authenticated outcome is authoritative.

## 3. One monetary truth

Each concept has one owner and location:

| Concept | Authority |
|---|---|
| Requested amount and stated use | original bank/intake evidence proposition |
| Descriptive capacity range | versioned assessment artifact |
| Candidate facility scenario | non-authoritative structure question |
| OLIN analytical position | human dossier; never an offer |
| Approved facility and official terms | bank outcome event |
| Disbursed amount | bank outcome event |
| Outstanding balance | latest valid bank performance event |

Legacy `approved_mxn`, `recommended_amount_mxn`, `proposed_amount_mxn`, legacy
decisions, and pricing outputs are context-only and unavailable to Investigator.

## 4. Evidence and epistemic discipline

An authentic document verifies only the narrow observation supported by its
issuer, subject, period, authorization, verification method, and freshness. It
does not automatically verify every extracted conclusion.

Every finding carries both an epistemic class and truth/verification status:

- verified observation
- external evidence
- merchant claim
- model inference
- generated estimate
- experimental observation
- research hypothesis
- recommendation

Supported, refuted, corroborated, unknown, unresolved, superseded, expired,
revoked, and disputed states remain distinct. Caller labels such as
`verified=true` never create trust. Material findings cite evidence identifiers,
source/issuer, subject, period, timestamps, consent/authority, verification,
freshness, confidence, and contradictions.

## 5. CaseSnapshot

A CaseSnapshot is an immutable reconstruction at an exact event sequence. It
contains case and bank identity, responsible analyst, requested capital/use,
sealed bank packet, original decision and reason codes, consent state, evidence
references, claims, propositions, estimates, contradictions, unknowns,
financial reconstruction, investigation history, candidate structures, current
human analytical position, timestamps, and all relevant schema/formula/policy/
prompt/source-registry versions and digests.

Create a new snapshot after material evidence, consent, correction, action, or
finding events and before reconstruction or dossier delivery. Withdrawal,
expiry/revocation, attestation changes, identity failure, material correction,
or integrity failure marks old snapshots stale; it never mutates them. Stale or
invalid snapshots cannot authorize an action or dossier.

## 6. Contradictions and unknowns

Detect claim-vs-evidence, evidence-vs-evidence, temporal, identity, ownership,
accounting, economic, duplicate, and source inconsistencies. Record severity,
decision materiality, plausible explanations, smallest resolving action,
status, and audit trail.

Example: claimed revenue of MXN 260k and bank-visible inflows of MXN 118k create
an unresolved contradiction and the unknown `unobserved revenue channels`.
They do not create the conclusion `bad credit` or `false revenue`.

## 7. Economic reconstruction

V1 produces descriptive ranges, never false precision or policy decisions. It
may reconcile bank, POS, delivery, marketplace, invoice, and cash evidence while
subtracting internal transfers, refunds, debt proceeds, and duplicates. It must
prevent overlapping-channel double count.

Where evidence supports them, calculate sustainable revenue, gross margin,
normalized and stressed operating cash flow, obligations, working-capital
cycle, concentration, free cash flow, and use-of-funds economics. Arithmetic,
normalization rules, deduplication, amortization, concentration identities, and
stress transforms are deterministic and fully traced. Estimates of missing
cash sales, sustainability, incomplete margins, or use-of-funds effects remain
explicit inferences/ranges. Unknown inputs remain null/open, never zero.

Legacy scorecard, repayment, fraud, calibration, geo, and `capacity_v2` outputs
are quarantined. A future pure descriptive calculator may be wrapped only after
its assumptions and obligations are reconciled and authority-shaped outputs are
removed.

## 8. Investigation actions and information value

V1 has four action families only:

- targeted merchant question
- authorized provider retrieval
- counterparty or asset verification
- controlled observation

An action records target uncertainty, hypothesis, source, decision relevance,
expected uncertainty reduction, independence, trust, manipulability,
completion probability, cost, merchant/analyst friction, latency, permissions,
freshness, specialist dependency, structures opened/closed, and stop criteria.

V1 does not claim calibrated expected information gain. Human reviewers record
LOW/MEDIUM/HIGH judgments before action for relevance, uncertainty reduction,
independence, trust, manipulation risk, cost, friction, and latency. After the
result, record realized usefulness and evidence/contradiction/structure effects.
Only deterministic admissibility gates may block actions; initial ordering and
selection remain human-controlled.

## 9. Investigation loop and authority

The compact lifecycle is `RECEIVED -> TRIAGED -> INVESTIGATING -> REVIEW_READY
-> DELIVERED -> CLOSED`, with `OUTCOME_PENDING` and `OUTCOME_MATURE` tracking.
New evidence or invalidation can return `REVIEW_READY` to `INVESTIGATING`.
Consent, privacy, security, evidence-integrity, fraud, legal, and partner holds
are orthogonal. Durable events are authoritative; mutable case status is only a
projection.

No LLM output may transition state, release a hold, authorize an action, accept
or verify evidence, sign a dossier, make a bank decision, or move money.

Stop when evidence is sufficient for a human recommendation; uncertainty is no
longer decision-material; the next action has low value; cost exceeds expected
credit value; permission is unavailable; security/fraud requires escalation;
no viable structure remains; or reasonable investigation remains insufficient.

## 10. Founder amendment: Shadow AI Investigator

After the human-action workflow exists, V1 must add a research-only Shadow
Investigator. It receives only a valid immutable CaseSnapshot and has no tools,
network, acquisition, contact, verification, authorization, state mutation,
scoring, credit, pricing, dossier-editing, or money authority.

It may propose decision-sensitive unknowns, contradictions, hypotheses,
targeted questions, at most three actions, information-value rationales, and
resolving evidence. The analyst selects an action before any AI proposal is
revealed. Store the AI proposal separately and never alter the dossier before
human selection.

After results, compare `human_action_selected`, `ai_shadow_actions_proposed`,
`human_ai_agreement`, human/AI predicted usefulness, realized information gain,
contradiction resolution, new independent evidence, actual cost, latency,
structure change, bank disposition change, and mature outcomes. This is
research instrumentation, not production credit authority. Phase 0 implements
none of this runtime behavior.

## 11. Founder amendment: two-layer bank output

Both outputs are reproducibly derived from the same CaseSnapshot and contain
its identifier, digest, event cutoff, and artifact version.

The primary **Analyst Brief** contains: original bank decision/reasons; what
OLIN newly established; unresolved contradictions/unknowns; reconstructed
economics; candidate structure questions; and the human next action.

The **Audit Annex** contains the complete dossier, evidence lineage,
reproducibility manifest, versions, limitations, contradictions, consent/trust
state, transformations, and human sign-offs. Neither output is a score, offer,
approval, or bank decision.

## 12. LLM and specialist boundaries

Initial V1 has no runtime LLM or autonomous agent. A later LLM may draft
source-linked candidates for extraction, claims, contradictions, hypotheses,
questions, rationales, summaries, and dossier prose from a redacted snapshot.
It cannot own consent, authentication, source/evidence verification, monetary
calculation, permissions, state transitions, hard policy, audit/versioning,
credit decisions, legal authority, deletion, or money movement.

Specialist review is explicit and need-based: credit validity to Credit
Scientist; geo economics to Geo Intelligence; manipulation to Fraud Red Team;
security/tool access to Security Reviewer; system structure to Chief Architect;
and high-stakes assumptions to Adversarial Skeptic. Specialist conclusions are
advisory and never production authority.

## 13. Bank Second-Look and dossier flow

The minimum bank input preserves institution/tenant, cohort, partner case,
original disposition/reason codes/timestamp/policy, requested facility, evidence
references/times, prior missing-evidence attempts, consent/retention authority,
analyst, idempotency key, and packet digest.

```text
sealed bank packet + original reasons
  -> tenant-bound case and evidence normalization
  -> contradictions/unknowns
  -> human-proposed and human-authorized action
  -> new evidence and reconstruction
  -> Analyst Brief + Audit Annex
  -> bank analyst response
  -> authenticated outcome and performance events
```

The outcome feed covers the entire eligible denominator and preserves original
decision before exposure, packet adoption, final bank decision, official terms,
disbursement, schedule/exposure, performance/DPD/censoring, cure, restructure,
charge-off, recovery, cost, provider reliability, issuer, version, and
corrections.

## 14. Storage and migration strategy

Use PostgreSQL relational tables plus explicit relationship tables when needed;
do not adopt a graph database merely because evidence relationships form a
graph. Add versioned migrations. Use UUID Investigator identities and retain
legacy text references only as references. Enforce non-owner/no-BYPASSRLS roles,
FORCE RLS, dual tenant binding, composite tenant foreign keys, transaction-local
context, pool reset, encryption, minimization, retention, and database-verified payload
digests. Full-envelope or chained tamper evidence is deferred with the wider event
envelope design. Phase 0 actor/workload fields are contextual audit metadata, not
authenticated identity; a future service must bind them to authenticated claims.
Digests must not encode raw PII in immutable logs.

Migration disposition:

| Existing area | Disposition |
|---|---|
| Evidence Passport, source trust, consent, intake/bank ingestion | preserve and later wrap through narrow read ports |
| `store.py` / `scoring_log` | do not extend; build additive Investigator repository |
| `server.py` | do not add Investigator routes; use a separate entry point later |
| scorecard, repayment, `capacity_v2`, calibration, signals | quarantine from Investigator |
| geo and fraud modules | research-only; unavailable to initial runtime |
| outcomes/performance | later wrap as authenticated bank-owned events |
| STP, collection, portfolio, graduation and legacy money routes | physically inaccessible to Investigator |

There is no big-bang rewrite and no dual write of canonical authority.

## 15. Approved build sequence

0. Executable authority contract, forbidden-surface inventory, case/event
   migration, database role/RLS, and negative harness.
1. Case/event repository and deterministic replay with no evidence or scoring
   logic.
2. Immutable CaseSnapshot and read-only Passport/consent adapters.
3. Versioned assessment and deterministic descriptive reconstruction.
4. Human action workflow and predicted/realized information-value capture.
5. Same-snapshot Analyst Brief and Audit Annex.
6. Authenticated full-cohort outcome stream and controlled shadow pilot.
7. Research-only Shadow Investigator and blinded human-vs-AI comparison.

Every phase needs unit, integration, tenant-boundary, provenance, replay,
idempotency, failure/rollback, and authority-regression tests appropriate to its
surface. A phase rolls back by disabling its separate entry point and reverting
only additive schema/code; legacy lending behavior is never part of rollback.

## 16. Pilot and kill conditions

Pilot with one bank, a frozen cohort of at most ten representative historical or
parallel-shadow cases, a complete eligible denominator, original decisions
sealed before OLIN exposure, and no production effect. This validates workflow,
provenance, reproducibility, burden, cost, and outcome capture—not PD/LGD/EAD or
bank outperformance.

Stop immediately for any credit/money effect, cross-tenant access, caller-created
trust, failed withdrawal, unreproducible output, monetary divergence, unknown
treated adversely, collapsed contradiction, missing denominator/censoring,
unauthenticated/mutable outcomes, live-decision contamination, scenario mistaken
for offer, unavailable outcomes, lifecycle/audit failure, or cost/effort exceeding
decision value. Reject the product thesis if repeated controlled cases mostly
repeat bank information and do not produce decision-relevant independent
evidence or a measurable workflow/economic improvement.

## 17. Explicitly deferred

Deferred are CaseSnapshot in Phase 0, runtime AI, autonomous agents, live
acquisition broker, merchant uploads, crawler, graph database, calibrated action
ranking/EIG, generalized facility search, automated recommendations, capacity
policy, predictive model training, production geo/behavioral/psychometric/fraud
scores, cross-bank deployment, direct-SME lending, LOS writes, pricing,
disbursement, repayment, collections, and graduation.
