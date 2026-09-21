# Phase 6 — deterministic Analyst Brief and Audit Annex

Development contract: authenticated synthetic cases only. No production/bank
approval, AI prose, new evidence authority, decisions or report persistence.
Phase 5B remains separate research; six historical calls are exhausted and no
additional inference is authorized or performed by this feature.

## Read-only route amendment

`GET /api/cases/{case_id}/report` accepts the existing analyst session, no query
or body bindings. Tenant comes from authentication and is checked against both
database custodians. It returns one captured brief/annex pair, printable escaped
HTML and structured JSON with identical provenance. Response is private/no-store.
Authority contract `investigator-authority-1.5` / profile `investigator_v1_phase6`
requires the exact seven Phase 5A routes plus exactly this one read-only route.
This adds only a read route to the existing authority allowlist, not database
grants, actions, signing, delivery or report storage. Existing development auth
is not approved bank SSO.

## Consistent capture

`investigator-report-input-1` is immutable serialized in-memory display data,
not an authorization token. The existing action login runs a READ ONLY
transaction and holds the existing shared case reasoning-currentness fence.
This prevents fenced evidence/case/selection writes during capture. Ordered,
append-only action history is read before and after the unchanged approved
`reconstruct_economics_current` wrapper. Transitions have their own action lock:
if either history read differs, the entire capture fails explicitly. Equal
history reads bracket the server-authorized reasoning time without ABA because
history cannot be rewritten/deleted. No lock spans rendering or browser use.

The snapshot envelope is immutable and its digest is checked against the
wrapper result. Both outputs bind tenant/case, snapshot/digest, event cutoff,
authority revision/digest, evidence-state digest, assessment/rules/schema,
action-history digest/per-action sequence cutoff, template/input versions and
server checked_at. Connections close before deterministic rendering. Bounds and
timeouts inherit the existing canonical snapshot and reasoning contracts. Captured
serialized input is limited to two MiB; oversize fails without truncation.

Template: `investigator-report-template-2` adds escaped arithmetic assumptions to
the concise Brief so strict30-day equivalents cannot appear to be calendar-month
observations. Prior template1 artifacts remain unchanged. A report-input digest binds the
complete captured record. Rendering the same record/template is deterministic;
a fresh capture has a new server time and need not have the same digest.

## Meaning and exclusions

Brief observations, claims, arithmetic, unknowns and precise disagreements stay
distinct. The annex retains reference-only evidence/source/consent/verification,
lineage/supersession, reconstruction formulas/assumptions and human history.
Tenant-scoped historical snapshot invalidations are captured under the same
fence with reference, reason, time and actor metadata only; they never reactivate
the invalidated snapshot or authorize a current report.
There are no raw document bodies, model responses, research ratings or new
signatures. Current evidence linked to an accepted action is reported as newly
supported only for its proposition/verification status; administrative status
never verifies a claim. Missing bank question/disposition/reasons and human
sign-offs are NOT PROVIDED: the currently supported synthetic source contract
does not record them. Structure questions are NOT ASSESSED. No generic event
payload is reinterpreted as bank authority.

The target remains 118,000 MXN observed bank inflows, 260,000 MXN claimed revenue
and 142,000 MXN arithmetic difference. Complete bank-account coverage is not
complete revenue-channel coverage. Sustainable revenue, missing costs/debt and
unperformed outcomes remain unknown. No amount is recalculated in JavaScript.

## Analyst journey and custody

Use the existing development-only synthetic setup and authenticated Investigator
app. Open a case, select **Capture / refresh report pair**, then **View Analyst
Brief** or **View Audit Annex**. Both views, **Print selected report**, and
**Download structured JSON** use that one pair. Refresh captures anew and clears
old report display first; failed refresh leaves an explicit unavailable state.
No browser storage or server report table is used. A downloaded artifact is
historical AS OF its timestamp, not continuing authorization. It cannot be
remotely recalled; analyst custody/retention and real-data permissions require
separate production approval. No public sharing or automatic delivery exists.

## Validation thesis

Useful output means a human can distinguish supported economics and actual
investigation outcomes without consulting raw tables or conflating research with
truth. Kill conditions: cross-tenant exposure, mixed cutoff/snapshot, stale
success, implicit verification, hidden mutations or invented economics.
Focused tests cover authentication/forged bindings, deterministic escaped output,
real PostgreSQL capture/history races/revocation and original/coverage/stop cases.
Browser demonstration and exact-candidate CI evidence are recorded separately;
tests do not establish bank usefulness or production readiness.
