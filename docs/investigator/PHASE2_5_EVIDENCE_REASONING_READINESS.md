# Phase 2.5 evidence reasoning readiness

## Boundary

This phase adds no claims, contradiction analysis, evidence weights, scoring,
provider acquisition, AI, geo, lending, or money behavior. Canonical artifact
bodies stay with the Evidence Passport owner. Investigator stores immutable IDs,
digests, lifecycle references, and server-derived semantic-lineage metadata only.

The required flow is:

`canonical PostgreSQL authority projection -> immutable evidence reference -> snapshot v2 -> require_snapshot_current_for_reasoning -> ReasoningReadySnapshot`

Future analytical code must accept only `ReasoningReadySnapshot`. A raw
`CaseSnapshot`, snapshot payload, structural-currentness result, or historical
row is audit material and is not an analytical authorization.

`InvestigatorEvidenceBoundary` implements this contract for the in-memory
executable specification. `PostgresReasoningSnapshotGate` implements the same
method and returns the same opaque type for durable state. The durable call must
run in an explicitly open, read-only `READ COMMITTED` transaction, rechecks runtime
credential custody on the exact connection it queries, verifies the stored
canonical digest and contract versions,
and reconstructs every accepted reference from live canonical authority before
issuance. Caller `as_of` is only checked for bounded clock skew; evidence
currentness and `checked_at` use the authoritative spine/database clock so a
caller cannot backdate through an expiry edge. The token is for synchronous use
within that reasoning operation; it
is not a cacheable authorization.

The durable gate takes a transaction-scoped shared lock for the tenant/case
before its fresh statement snapshot. Migration `0004` makes event-head and
snapshot-invalidation writes take the matching exclusive lock. The shared lock
must remain held while the returned capability is synchronously consumed.
Production analytical entry points must use
`consume_snapshot_current_for_reasoning(...)`, which opens one bounded read-only
transaction, validates readiness, invokes the consumer, and then ends the
capability. The capability records the issuing backend and transaction ID;
cross-transaction, post-commit, post-rollback, repeated, and serialized use fails
closed. Statement and idle-in-transaction time are bounded to five seconds and
lock acquisition to one second. Raw snapshots and serialized payloads are not
analytical inputs.

## Semantic independence

The canonical evidence owner supplies an opaque `semantic_lineage_id`, a
`lineage_relation`, upstream issuer identity, and optional deterministic parent
or economic-event IDs. Investigator never infers equality from filenames,
channels, source labels, or fuzzy document similarity.

`INDEPENDENCE_UNKNOWN` is the default and is neutral. It neither adds independent
support nor constitutes adverse or fraud evidence. `INDEPENDENT_VERIFIED`
requires a versioned server-side attestation. Copies and corrections cannot be
independently verified; unknown lineage also stays independence-unknown.
Corrections retain their parent's lineage, and every
derived parent must resolve inside the same case and lineage. Reusing a stable
independence attestation ID, including under a new attestation version—or the
same known economic event and upstream issuer—
cannot create another independently verified support unit. Exact replay remains
idempotent and cannot create another support unit.

## Canonical PostgreSQL projection contract

**Canonical projection state is the authoritative eligibility state for
Investigator reasoning.** External Passport, consent, source, and lifecycle
systems remain upstream. Their changes become analytically effective only when
the Evidence Authority commits a corresponding projection revision.

`PostgresCanonicalEvidenceReadPort` queries the versioned, read-only projection:

`evidence_authority.investigator_evidence_v1`

Migration `0004` creates an append-only metadata projection ledger and the
latest-record view. Each tenant/case revision is monotonic and carries a
deterministic chained state digest, projection version, change kind, and commit
timestamp. The sole writer function takes the same exclusive advisory-lock domain
that reasoning holds shared. Thus revision N is either consumed completely before
N+1 commits, or N+1 commits first and readiness validates N+1. A rollback advances
neither revision nor digest.

The view represents authoritative artifact, subject, consent, proposition,
source-attestation, integrity, lifecycle, and semantic-lineage metadata. It returns
only the closed metadata fields requested by the adapter—never an evidence body.
Its `canonical_reference` object contains the exact 43 authority-owned fields
of the persistence envelope; Investigator supplies only `reference_id`,
`accepted_at`, and `supersedes_reference_id`. SQL acceptance requires exact
object equality before persisting anything, so a copied digest cannot authorize
substituted provenance.
Missing fields, missing rows, unsupported versions, legacy incomplete records,
duplicate rows, or a non-PostgreSQL connection fail closed. The port also
requires an unprivileged, transaction-read-only
`olin_investigator_evidence_reader` identity with no Investigator runtime,
owner, or evidence-authority membership. Each port instance is bound to one
tenant and rejects requests for any other tenant. PostgreSQL RLS independently
binds reader logins named `olin_canonical_t_<tenant UUID without dashes>` to the
same transaction-local tenant context. Migration `0004` owns the hardened
no-login reader group and grants only schema usage, projection-view `SELECT`,
and execution of the exact read-only tenant identity accessors used by that RLS
policy. A reader-controlled GUC alone cannot change the tenant derived from its
login name. No backing-table or artifact-body privilege is granted to runtime,
reader, or Evidence Authority logins.

## Credential custody

The following are separate identities and secret objects:

- Investigator runtime tenant login: member only of
  `olin_investigator_runtime`; it cannot possess canonical-reader or
  evidence-authority credentials.
- Canonical read service: read-only execution on the owner projection; it cannot
  write Investigator, consent, trust, scoring, or money state.
- Evidence-authority tenant login: member only of
  `olin_investigator_evidence_authority`; it may invoke closed acceptance/state
  commands and has no Passport mutation, scoring, lending, or money authority.
- Migration owner: offline migration identity, never an application credential.

Runtime startup must validate its database identity with
`assert_runtime_database_custody`. Any active role other than the exact runtime
group, missing runtime membership, owner/evidence-authority membership, powerful
login attribute, shared DSN, authority secret, or ambiguous identity fails
startup. Authority DSN and password names are explicitly prohibited from the
Investigator environment contract; deployment injection belongs in a separate
authority process/service. Secret-manager/IAM separation, independent rotation, connection
auditing, and tenant-login provisioning are operational requirements; repository
code alone does not prove them.

The evidence-authority writer is checked separately with
`assert_evidence_authority_database_custody`, and its SQL acceptance command
independently rejects powerful login attributes or any membership other than the
evidence-authority role. All custody checks traverse the complete PostgreSQL role
membership closure, so a forbidden role nested under an allowed group also fails.
The canonical reader rechecks its identity, conflicting memberships, login
attributes, tenant binding, and read-only transaction state for every lookup.

## Accountable ownership

| Role | Approve | Execute | Audit | Emergency revoke/rotate |
|---|---|---|---|---|
| Evidence Authority Owner | Projection/writer changes | Authority revision publication | Revision and credential trail | Disable writer and rotate authority credential |
| Source/Revocation Governance Owner | Source eligibility and revocation | Authorize source-state projection | Source changes and affected cases | Revoke compromised source |
| Data Governance Owner | Consent, retention, pseudonymization | Authorize lifecycle projection | Consent/retention history | Withdraw authority and require revalidation |
| Platform/Security Owner | Deployment and access policy | Roles, RLS, timeouts, secret rotation | Effective privileges and incident trail | Disable access and rotate credentials |

Approval and execution must be separated where the same role has multiple staff.
Material revocation must meet the deployment incident SLA. Secret-manager
isolation and network separation are **DEPLOYMENT PROOF REQUIRED**; unit tests do
not establish those controls.

Migration `0004` records pre-existing Phase 2 references with semantic schema
version `0`. They remain immutable and auditable but cannot pass the reasoning
gate; only forward references backed by canonical semantic schema version `1`
are reasoning-eligible.

For durable parity, migration `0004` preserves the Phase 2 snapshot builder as
an internal legacy implementation and places semantic enrichment at the
immutable snapshot insert boundary. The public `create_snapshot_v2` wrapper
returns the post-enrichment digest and converges different idempotency keys at
the same locked event head on that stored enriched snapshot. New durable
snapshots therefore carry the
same `investigator-evidence-semantics-1` marker and per-reference semantic record
as the Python specification. Pre-migration snapshots are not rewritten and
remain ineligible until a later event head produces a new snapshot.
