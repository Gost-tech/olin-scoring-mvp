# Phase 1 Case / Event / Snapshot Spine

Phase 1 adds a typed event registry, server-authoritative `ActorContext`, deterministic replay, and immutable `snapshot_v1`. It preserves the Phase 0 tables and functions and extends their authority only with snapshot read/create/invalidate operations.

The minimum event set is `CASE_CREATED`, the empty `INVESTIGATION_EVENT_RECORDED` Phase 0 compatibility event, and `CASE_SNAPSHOT_INVALIDATED`. Snapshot creation is represented by the immutable snapshot row itself instead of an event. Appending `CASE_SNAPSHOT_CREATED` before snapshot calculation would make the snapshot depend on an event that needs its result; appending it afterward would make the snapshot immediately stale.

Snapshot content is immutable. Currentness is derived from equality between `case_snapshot.event_head_sequence` and `investigation_case.case_version`, plus the absence of an append-only `case_snapshot_invalidation` record. Invalidation is limited to enumerated integrity failures; consent, evidence, provider, and expiry semantics remain deferred.

The Phase 0 authority contract receives a documented additive Phase 1 extension: `snapshot.create`, `snapshot.read`, and `snapshot.invalidate`; the `case_snapshot`, internal `case_snapshot_request` idempotency ledger, and `case_snapshot_invalidation` tables; and their constrained database functions. Existing denies, routes, principals, credentials, and forbidden surfaces are unchanged. Every converged snapshot request is permanently bound to its resulting snapshot in the append-only request ledger, including a second writer that converges on a row created under another key.

## Exact `snapshot_v1` schema

No keys beyond this closed shape are permitted by the builder:

```json
{
  "applicable_versions": {
    "canonicalization": "olin-canonical-json-1",
    "event_registry": "investigator-events-1.0"
  },
  "audit": {
    "case_created_actor": {
      "actor_type": "bank_service | human | system",
      "actor_reference": "string",
      "tenant_id": "uuid",
      "case_id": "uuid | null",
      "authentication_reference": "string",
      "authorization_source": "string",
      "correlation_id": "string",
      "created_at": "UTC RFC 3339, six fractional digits"
    },
    "latest_event_actor": "same closed ActorContext audit shape"
  },
  "case": {
    "case_id": "uuid",
    "case_version": "positive integer",
    "cohort_reference": "string | null",
    "created_at": "UTC RFC 3339, six fractional digits",
    "created_by": "authoritative actor reference",
    "legacy_case_reference": "string | null",
    "tenant_id": "uuid",
    "updated_at": "UTC RFC 3339, six fractional digits"
  },
  "event_stream": {
    "head_event_digest": "lowercase SHA-256",
    "head_event_id": "uuid",
    "head_sequence": "positive integer",
    "stream_digest": "lowercase SHA-256 over the ordered event-digest array"
  },
  "lifecycle": {"state": "OPEN"},
  "snapshot_schema_version": 1
}
```

Keys are lexicographically ordered, UUIDs are lowercase, timestamps are UTC with fixed microsecond precision, null is explicit, binary floats are rejected, finite decimals serialize as their exact base-10 string, and the UTF-8 JSON encoding has no insignificant whitespace. Snapshot identifiers and creation timestamps are envelope metadata and are deliberately excluded from canonical content, so concurrent builders at the same event head converge on identical bytes and digest.

The Phase 1 migration explicitly aborts if the Phase 0 case or event store contains rows. Authenticated actor provenance cannot be reconstructed honestly, so Phase 1 neither fabricates a production authentication record nor deploys a database that contains permanently unsnapshotable cases. Because Phase 0 forces RLS, this one global cutover check deliberately requires a controlled superuser or `BYPASSRLS` migration principal; runtime roles remain unprivileged and cannot acquire either attribute. Deployment must prove the pre-pilot Phase 0 store is empty; handling real legacy rows would require a separately reviewed cutover.

For database execution in this phase, ActorContext is intentionally limited to a `system` actor derived from the tenant-bound PostgreSQL login: actor reference, authentication reference, authorization source, case scope, and creation time are server-derived. The correlation/run reference is a bounded `postgres-command:` value derived by SHA-256 from the validated command idempotency key, so free-form caller data is never copied into ActorContext. Caller-set actor, user, admin, reviewer, workload, principal, authentication, authorization, correlation, case, or timestamp GUCs are ignored. Human authentication is not invented; it requires a later real resolver before any route exists.
