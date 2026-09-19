# Bounded first shadow evaluation (harness version 1)

Optional hosted transport: see [PHASE5B_HOSTED_CONNECTION.md](PHASE5B_HOSTED_CONNECTION.md)
for the explicitly disabled-by-default `shadow-hosted-1` extension, dedicated
worker-only credential custody, three-request cap and spending/transmission
approval requirements. The original local-adapter protocol below remains valid;
the extension does not alter frozen rubrics, prompt, schema or coverage.

This is a synthetic research evaluator, not a model-quality result, canonical
writer extension, bank pilot, or new provider. The Phase 5B authority amendment
is unchanged. No model installation, download or inference is authorized here.
The raw-length repair enforces the existing schema; prompt/schema versions stay
`shadow-prompt-1`, `shadow-context-1`, `shadow-proposal-1`.

## Frozen coverage manifest

`shadow-evaluation-1` remains seven development and three held-out rubrics. The
evaluator pins exact dataset, prompt and schema digests. It does not tune them.
Rubric/expected/forbidden/split fields remain evaluator metadata, never worker input.

| Rubric | Canonical setup and actual model observability |
|---|---|
| coverage-unknown (development) | Existing 118k bank-visible / 260k merchant target; account and channel UNKNOWN. MODEL_VISIBLE. |
| account-complete (development) | Same target plus existing operator's closed useful-coverage fixture. Account COMPLETE, channel UNKNOWN. MODEL_VISIBLE. |
| period-mismatch (development) | UNSUPPORTED_SETUP: closed operator has no mismatch variant; baseline periods match. Phase 4 supports period checks, but this harness does not claim to have supplied this scenario. |
| scope-mismatch (development) | UNSUPPORTED_SETUP: no personal-versus-business fixture supplied by the closed operator. |
| duplicate-source (development) | FILTERED_AT_INPUT_BOUNDARY: existing duplicate-response fixture adds no canonical evidence; response history is omitted from research projection. No independent support is manufactured. |
| permission-missing (development) | UNSUPPORTED_PROJECTION: authorization for NEW acquisition is absent from the projection. Existing evidence-analysis consent remains valid. It is not revoked to simulate this different question. |
| insufficient (development) | UNSUPPORTED_SETUP: the available target fixture contains admissible facts; no empty-case setup is supplied. |
| stop-limit (held-out) | UNSUPPORTED_PROJECTION: administrative action limits/history are not model-visible. |
| prompt-injection (held-out) | FILTERED_AT_INPUT_BOUNDARY: rubric free text is not admitted by the closed canonical fixture/projection. It is never inserted as an invented context field. NOT evidence of model resistance. |
| cost-debt-unknown (held-out) | Target has no cost/debt evidence; actual approved reconstruction preserves unknown totals. MODEL_VISIBLE. |

Actual coverage is THREE model-visible scenarios, not ten model evaluations.
All ten entries receive fresh authorized setup/projection records; the seven
nonrepresentable entries retain their exact gap and are not sent to inference.
The complete-account setup identifier is fixture metadata, not a performed human
action. This evaluator creates no human baseline, rating, action or bank outcome.

## Setup and commands

Use an already provisioned disposable PostgreSQL database and the existing
development-only tenant roles/fixtures. Do not use a production database. Apply
existing migrations with the existing controlled setup; this evaluator adds no
grants or migrations. Normal analyst processes never receive operator custody.

In a separate operator preparation process configure existing explicit connection
variables (do not load a legacy `.env`):

- `OLIN_SYNTHETIC_RUNTIME_DATABASE_URL`
- `OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL`
- `OLIN_INVESTIGATOR_DATABASE_URL`
- `OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL`
- `OLIN_INVESTIGATOR_ACTION_DATABASE_URL` (read history through existing service)

```sh
python -m scripts.evaluate_investigator_shadow prepare \
  --tenant <development-tenant-uuid> --namespace <new-evaluation-namespace-uuid> \
  --directory output/shadow-evaluation-run
```

Preparation uses the existing `SyntheticEvidenceOperator` canonical acceptance
route, then `InvestigatorWorkflowService.current_analysis` and the existing
projection. It never treats manifest JSON or its digest as authorization.
The directory must be owner-only 0700; records are created exclusively as 0600.
Preparation makes no inference call. Remove operator authority credentials from
the evaluation coordinator environment afterward; retain only its existing
runtime, canonical-reader and action-reader connections.

```sh
python -m scripts.evaluate_investigator_shadow dry-run \
  --tenant <development-tenant-uuid> --directory output/shadow-evaluation-run
```

This explicitly uses the labelled deterministic fake; it cannot select a real
configuration. Every eligible input is re-derived through the PostgreSQL wrapper
and compared with the prepared binding/digest immediately before inference.
All database transactions finish before the credential-free subprocess starts.
The worker receives only minimized context and explicit configuration, not
connections, rubrics, identities, selection, history or outcome metadata.
The parent checks currentness again before marking the result eligible.

Real mode uses the SAME command with `real --config <private-approved-json>`.
It refuses before database access without complete configuration. It never
falls back to the fake. A real run needs a separately prepared run directory;
reusing a fake run with a changed configuration is rejected, not overwritten.

Required real configuration: `mode=ollama`, exact preinstalled `model`, explicit
`http://127.0.0.1:<approved-port>/api/chat`, `synthetic_only=true`, accountable
nonblank `approval_reference`, `max_requests` from 1 to 10,
`max_input_tokens=16384`, `max_output_tokens=1024`, `timeout_seconds=30`.
First-run proposal: at most ten eligible requests, sequential, one attempt per
case; currently only three cases are eligible. No retries or fallback. Operator
approval must cover the total budget across process/run restarts; a second run
is not implicit permission to spend again. There is no approved model installed
or approved resource budget in the implementation session.

## Artifacts, failure and recovery

Private manifest: candidate SHA, dataset/prompt/schema hashes and versions,
fixture-to-case mapping, authorized context, snapshot/authority bindings,
reference aliases/provenance, and observability. No complete assessment is saved.

Each eligible case gets an exclusive durable STARTED record BEFORE launching its
worker. A file lock excludes concurrent runs. Final records are append-only and
replayed historically; an interrupted STARTED becomes AMBIGUOUS without another
call. A different configuration/candidate/manifest cannot overwrite the run.
Do not delete receipts or use a new directory to hide a failed attempt.

`report.json`, `summary.json`, and `summary.md` separate pipeline coverage from
model attempts. They retain invalid output, abstention, timeout, transport failure,
stale context and explicit refusal statuses. A free-text refusal violating the
closed schema is INVALID_OUTPUT, with raw response available for attributed human
classification; this adapter does not invent a provider-specific refusal field.
An authorization rejection BEFORE inference is neither model success nor failure.

Raw synthetic adapter responses are base64-encoded in the private per-case record,
not canonical evidence or public logs. The existing bounded 32,001-byte capture
limit still applies; an oversized response is a bounded prefix, not a claimed
complete raw transcript. Valid proposals have reproducible serialization/digests;
usage/latency are recorded when available. Unknown cost stays null. Failed parsing
may leave usage unavailable. No hidden reasoning is requested or graded.

The 30-second socket timeout and 35-second subprocess wait are not proof that the
Ollama endpoint stopped computing. Ambiguous results explicitly retain that
uncertainty; never retry until a pleasing answer appears.

Schema/reference/admissibility results are deterministic checks, not economic
truth. Relevance, redundancy, usefulness, economic interpretation and defensibility
remain NOT_REVIEWED until separately attributed human review. Unperformed outcomes
remain UNKNOWN. Ten rubrics (only three currently observable) do not establish
credit performance, bank usefulness or model reliability. Production OS/network
isolation, hosting, data lifecycle and bank authentication remain unproven.

## Focused implementation review attribution

The existing independent reviewer `/root/phase5b_boundary_review` reviewed only
this evaluator addition and the runner's private response observer. One medium
artifact-recovery issue was found: publishing files before completing their bytes
could strand replay on partial JSON. It was corrected with private temporary-file
fsync, atomic exclusive hard-link publication, directory fsync, and independent
summary recovery. New regressions cover interrupted publication and missing
summaries without repeated attempts. The same reviewer's correction recheck
returned GO for candidate validation, with no remaining blocking finding, high
confidence from source inspection. The reviewer executed no tests or inference;
local tests and exact-SHA CI are separately attributed to implementer/CI. This
does not grant final Phase 5B acceptance or real-inference authorization.
