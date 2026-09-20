# Phase 7 — bounded synthetic annotations and declared cohorts

Status: implementation candidate, not development acceptance or bank approval.

## Reuse and gaps

| Existing | Reuse / missing piece |
|---|---|
| Phase5A selections/transitions | Actor, rationale, evidence refs, actual effort/cost remain there; no duplicated costs |
| Phase5B shadow ratings/history | Research-only judgment remains separate; never imported as report truth |
| Phase6 frozen report manifest | Historical report identity; new domain-separated signed receipt, no report body persistence |
| Tenant/case identity | Composite references and existing authenticated analyst; tenant ID is authenticated organization reference, NOT a bank name |
| Missing report feedback/external observations | Append-only annotation streams with attributed content and correction lineage |
| Missing declared denominator | Operator-only versioned synthetic cohort, maximum ten members; prior members cannot disappear |

## Narrow authority amendment

`investigator-measurement-1` is an isolated optional application boundary.
Authority1.6 adds exactly GET/POST case feedback and GET cohorts, plus the isolated
feedback connection setting; Phase0–6 runtime/action database grants and all
existing deny capabilities remain unchanged.
Migration0008 adds NOLOGIN feedback/cohort-operator roles and three constrained
commands (read, append annotation, freeze cohort). Tenant service logins follow
`olin_feedback_t_<tenant hex>` / `olin_cohort_t_<tenant hex>`, each a member ONLY
of its matching non-owner role. Forced RLS and transaction-local tenant context
apply; direct table writes, canonical evidence, research, scoring and money access
are not granted. Existing runtime/action custody is unchanged. The operator
credential is setup-only and never supplied to the analyst process.

Optional `OLIN_INVESTIGATOR_FEEDBACK_DATABASE_URL` enables the feedback service.
The existing session secret derives a domain-separated report-receipt HMAC key.
Only the authenticated application issues receipts after Phase6 current capture;
client manifests/digests are not issuance proof. Receipts bind actor, tenant/case,
complete historical manifest and action IDs actually captured. No reporting write
is introduced. Annotation persistence stores provenance metadata, not reports,
raw evidence or reasoning results. The service login is a trusted authenticated
application boundary (like existing actor attribution), not a credential issued
to analysts. The database does not independently authenticate the browser user.

History reads and writes recheck current database tenant custody and case access;
they do not rerun old reasoning. Evidence revocation prevents NEW report capture
but does not itself revoke permission to read authorized historical annotations.
Revoked session/user or database membership denies history. A stored annotation's
authenticated historical binding can issue a correction-only historical receipt
to another currently authorized tenant analyst. It is not a regenerated report.
Receipt-key rotation invalidates unstored receipts; committed annotation history
remains. No new signing/sign-off workflow is implied.

## Attribution and recovery

FEEDBACK is ANALYST_JUDGMENT; EXTERNAL_OUTCOME is ANALYST_REPORTED_EXTERNAL.
No authenticated bank-owned category exists. Organization is `tenant:<UUID>`;
claimed organization/source names never establish trust. Occurrence is supplied
with timezone or UNKNOWN; recording time is database-server time. Earlier dates
never establish a sealed pre-exposure baseline: NOT ESTABLISHED.

Every annotation has a closed bounded payload, kind/version, actor, report/action
binding, reason and source attribution. Corrections retain binding/kind, require
the latest expected version and predecessor/reason; the original remains.
Tenant lock and unique command keys serialize writes; same-content replay returns
the original record, changed-content replay fails, and transaction rollback
creates no record. No receipt-only lifecycle or external side effect is involved.

## Cohort and counts

Operator freezes a declared synthetic universe/source, eligibility version,
member case IDs/eligibility reasons, amendment reason and server time. Every new
version retains every prior member, including explicit exclusions. Declared and
eligible counts are separate. Stopped cases are never filtered. Each kind retains
all effective observations (including negative/uncertain judgments), with pending,
unknown, unavailable, observed, not-applicable and window-incomplete status.
No entries means NOT_YET_OBSERVED, not negative. Counts distinguish cases with
annotations from actual observed outcomes. No rates, approval lift, predicted
performance, repayment calculation or cross-currency cost sums are computed.
Use original action transition identifiers for effort/cost; unknown stays null.

## UI and limits

Open/capture a report, enter a labelled annotation, inspect history, correct a
selected effective record with reason, and view the declared cohort. Rendering
uses textContent. Browser memory only; all responses no-store. Research availability
is irrelevant. Annotations remain outside Phase6 authoritative report content.
Synthetic actors/responses are fixtures, not actual human ratings or bank events.
No full report store, inference, providers, bank integration or money authority.
Append-only development history does not override future real-data retention,
rectification, deletion or legal obligations; those require separate approval.

## Disposable demonstration

Use existing PostgreSQL16 and the locked Python environment with psycopg. Prepare
an empty UTF-8 database named `phase7_investigator_test`, then run:

```sh
OLIN_INVESTIGATOR_TEST_ADMIN_DSN='host=127.0.0.1 port=55443 dbname=phase7_investigator_test' \
OLIN_INVESTIGATOR_TEST_DISPOSABLE=YES PYTHONPATH=. \
python scripts/run_investigator_feedback_demo.py --port 8767
```

This development-only operator uses existing canonical fixtures and migrations
through0008, freezes three explicit members and starts a separate least-privilege
analyst child without setup/evidence-writer/model credentials. Do not share the
database with tests or another service. It prints only synthetic case/cohort IDs
and the loopback URL. Stop with Ctrl-C to tear down its disposable fixture schemas.
Log in as `SYNTHETIC-analyst` / `synthetic-feedback-demo-only` (public fixture values,
not provider credentials). Use the printed useful/uncertain/unobserved case IDs.
Capture each report before initial feedback; record explicitly synthetic judgments,
external source descriptions, corrections and inspect the cohort. Leave the third
member unobserved. No shell commands are needed during that analyst journey.
