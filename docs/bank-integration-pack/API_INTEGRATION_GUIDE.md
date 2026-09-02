# API integration guide

## Authentication and traceability

Exchange the named bootstrap credential at `POST /api/v1/auth/sessions`, then use `Authorization: Bearer <short-lived-session>` over TLS. The signed `olin1` session expires after 5-60 minutes and remains only in browser/process memory. When `OLIN_REQUIRE_SHORT_LIVED_SESSIONS=1`, long-lived credentials are rejected by normal API routes.

Send a unique `X-Request-ID` on every request and retain the returned value for support.

Bank evidence callbacks use `X-Olin-Signature: sha256=<hex HMAC>` over the exact request bytes. Each provider receives its own secret. Rotation accepts `[current, retiring]` keys for a bounded overlap.

Historical files use the operator-run procedure in `BANK_BATCH_INTAKE.md`; Olin intentionally has no public general-purpose upload endpoint.

## Happy path

1. `POST /api/v1/intakes` with the bank case reference and cohort.
2. `POST /api/v1/intakes/{id}/consents` with approved text and policy version.
3. `POST /api/v1/intakes/{id}/link-sessions`; deliver the returned one-time token only to the provider-link client.
4. Provider exchanges the one-time token.
5. Provider posts consent-bound derived metrics to `/api/v1/webhooks/bank-evidence`.
6. Bank posts scoring fields to `/api/v1/intakes/{id}/score`.
7. Bank reads the recommendation and business evidence policy, makes its official decision, and records the outcome.

The callback must not include raw transaction rows. Replaying an identical `event_id` returns `200 duplicate=true`. Reusing it with any changed binding or payload returns `409 IDEMPOTENCY_CONFLICT` and writes nothing.

## Data minimization

Transmit only fields needed for the approved purpose. Evidence requires a source, verification status, retrievable reference, and observation time. A checked bureau flag without provenance is not verified evidence. Synthetic sources are rejected in production mode.

## Bank acceptance criteria

- cross-partner case reads return 404;
- withdrawn or absent consent blocks evidence ingestion;
- link tokens are hashed, expire, and can be consumed once;
- raw transactions do not appear in the database or API response;
- all responses carry `X-Request-ID`;
- the result never represents Olin's recommendation as an official approval;
- unsupported or uncalibrated business types route to bank committee.

Canonical machine contract: `../openapi-v1.json`.
