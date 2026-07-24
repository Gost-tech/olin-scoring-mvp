# Olin Adversarial Review

**Scope:** scoring, onboarding, SQLite state, analyst API, STP disbursement,
collections, calibration, daily operations, and the public website.

**Verdict:** **BLOCK for unattended live lending. READY for demos and a
partner-led shadow pilot.**

## Live-lending blockers

### 1. Disbursement ambiguity still needs authoritative reconciliation

The server now reserves the application with `claim_disbursement()` before it
calls STP, then records success or rolls the claim back after a known failure.
That closes the normal double-click/retry path. The remaining dangerous case is
an ambiguous provider result: STP may have accepted a transfer while the local
process loses the response or fails before it can record the folio.

Required design before live lending: durable attempt records, a stable provider
idempotency key, explicit `pending/sent/confirmed/failed/unknown` states,
authoritative reconciliation against STP, and a manual hold for every unknown
outcome. Never convert an ambiguous state into an automatic retry.

### 2. Shared analyst authentication is not sufficient for production

One environment token authorizes every analyst action. It cannot identify who
approved, declined, exported data, or initiated a disbursement. There is no
session expiry, role separation, or second-person approval for money movement.

Required design: named users, strong authentication, analyst/admin roles,
immutable actor audit events, short-lived sessions, and dual control for
disbursement.

### 3. Sensitive identity and financial data is stored unencrypted

The SQLite audit record contains raw application, bank, identity, address,
CLABE, and decision information. File permissions and `.gitignore` are not a
complete data-protection control.

Required design: encrypted storage and backups, access control, retention and
deletion policy, field minimization, restore testing, and incident procedures.

### 4. Credit-bureau consent evidence is only partially implemented

The store now records a consent timestamp, channel and exact text, and
production blocks analyst approval when consent is absent. This is an important
minimum control, but it is not yet a complete authorization artifact.

Required design before live lending: consent-text version, customer and operator
identity, report/reference ID, permitted purpose, immutable message/signature
evidence, privacy-notice linkage, and a reviewed customer-facing capture flow.

### 5. Existing connector credentials must be rotated

The local `.env` contains configured non-placeholder Belvo, Google Places, and
Syncfy credentials. Their values were not copied into this report, but every
credential that has been shared with earlier assistants, terminals, or other
people should be treated as exposed and rotated before any production use.

## Serious operational gaps

- Production traffic has no built-in TLS. Keep the application on loopback
  until it is placed behind an authenticated HTTPS gateway.
- There is no STP settlement reconciliation job comparing Olin records against
  the provider's authoritative transfer list.
- The pilot-wide MXN 30,000 maximum is a scorecard convention, not an independent
  portfolio/disbursement policy limit for every path and repeat borrower.
- The daily job now sends standard SMTP e-mail when configured and otherwise
  appends a timestamped durable log. Alert acknowledgement, retry, and escalation
  ownership are still missing.
- SQLite is acceptable for a single-operator shadow pilot, but concurrent
  workers and production availability require an explicit database strategy.
- The embedded analyst UI and HTTP API live in one 1,500-line module, making
  security review and safe changes harder than necessary.
- The public-site demo URL is now isolated in `website/config.js`; it still must
  be set to an authenticated hosted demo before public deployment.

## Findings corrected during this review

- Duplicate application logging used `INSERT OR REPLACE`, which could erase
  disbursement and repayment history. Logging is now append-safe and rejects a
  duplicate application ID.
- Portfolio-check database failure previously failed open. Production now
  blocks when exposure/default checks are unavailable.
- Demo mode could be pointed at a production database and expose its API without
  production authentication. Startup now refuses mixed-environment databases.
- The daily job previously defaulted to the demo database even in production.
- Calibration labels still described an obsolete tier mapping.
- Public-site reveal animation initially hid content when JavaScript was absent;
  it now uses progressive enhancement.
- A pre-disbursement claim now blocks ordinary duplicate sends and rolls back a
  known provider failure.
- Círculo consent timestamp, channel and text are stored, with a production
  approval gate when consent is absent.
- Daily alerts now persist to SMTP or `logs/alerts.log` instead of existing only
  as terminal output.
- The public website now reads its protected demo target from a separate config
  file rather than hard-coding the local analyst URL in the page.

## How far Olin can go now

1. **Now:** polished product demonstration and internal analyst simulation.
2. **Now:** shadow-score 10–30 consented partner cases without affecting credit
   decisions or moving money.
3. **After consent/data contracts:** controlled recommendation pilot with a
   registered lending partner making the final decision.
4. **After the five blockers:** limited live disbursement with dual control and
   daily reconciliation.
5. **After mature outcomes:** calibration research. Thirty loans are useful for
   operations learning, not enough for a production machine-learning model.
