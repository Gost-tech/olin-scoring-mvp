# Phase 5B isolated synthetic shadow research — version 1

Current evidence update: one separately founder-authorized hosted application
request at d9806918c68761c30ba9ec7d5324445dd2be4905 completed with a structurally
valid abstention. Guarded disclosure/blinding/currentness and development credential
custody passed. Cumulative calls seven; no remaining inference authorization.
MODEL SEMANTIC LIMITATION — RECORDED: the abstention denied the supplied merchant
assertion and blurred applicability with acquisition permission. This does not
invalidate permitted abstention or establish usefulness. The execution session's
private evidence is output/hosted-app-live1; no new request in release closure.
Older six-call/not-live statements below describe their original implementation
sessions, not the current status. Prompt/schema/applicability are unchanged.

## Guarded connected V1 amendment — shadow-application-hosted-1

The optional connected launcher now supports `--shadow-mode fake` or explicitly
approved `--shadow-mode openai`; default `none` remains human-only. This supersedes
the original local-only application transport restriction below, not its reasoning,
evidence or money denials. Authority1.7 adds only the six existing authenticated
research routes (create/resume/generate/disclose/rate/history) and six coordinator
settings. Database grants, principals and ordinary `ai.invoke` / `provider.call`
denials are unchanged. Migration0007's isolated research role remains the writer.

The application talks only to its token-authenticated loopback runner and pins
provider/model identity. Only the separate runner can invoke the existing hosted
adapter. It has a closed environment and no database/action/evidence credentials.
`OLIN_SHADOW_CREDENTIAL_FILE` carries an absolute path only to the runner, never
the analyst child, config JSON or process arguments. Its lazy loader uses the
existing owner-only regular-file/no-symlink check when generation is requested.
Readiness does not open that file or invoke inference. No ambient key lookup.
These process environments are not proof of OS/filesystem/network isolation.

Frozen pre-selection contexts, durable human binding, fresh disclosure, bounded
local validation and applicability remain unchanged. Runner failure leaves the
human/report/feedback services running; research fails explicitly without fallback.
STARTED/AMBIGUOUS recovery never reinfers automatically. A new runner process is
not a renewed spending approval; the existing per-process cap is not a global
billing ledger. Launch neither authorizes inference nor starts it automatically.
All six historical requests remain exhausted. This integration is tested only
with labelled fake results and mocked HTTPS, not a real provider credential.

Generation remains shadow-prompt-4 / shadow-openai-structured-3 /
shadow-openai-schema-2 with existing applicability. No semantic quality or live
compatibility improvement is established by this wiring.

The optional evaluator-only hosted extension is separately specified in
[PHASE5B_HOSTED_CONNECTION.md](PHASE5B_HOSTED_CONNECTION.md), amendment
`shadow-hosted-1`. It does not change the application/default denial below or
authorize execution. The following local-only description remains the original
accepted application transport contract.

Founder-authorized amendment to blueprint sections 10/12/17: only the isolated
research runner may invoke one operator-approved local inference endpoint for
synthetic minimized context. The ordinary `investigator-authority-1.4` contract,
including `ai.invoke=deny`, remains unchanged. No Phase 3/4 callback invokes AI.
No model tools, action writes, canonical authority, acquisition, money or credit
authority are granted. This is not an autonomous agent.

The analyst application obtains fresh Phase 3/4 reconstruction, projects only
closed metadata and pseudonymous reference aliases, and records a fixed round
before human selection. No human action, rationale, later evidence or evaluation
answer is sent to the runner. Research storage is separate from evidence and
reasoning outputs. Migration 0007 is additive because the closed Phase 5A history
is not a model-output store; migrations 0001–0006 remain unchanged.

Disclosure requires the same analyst, an immutable human selection made after
round creation on its snapshot/authority, and fresh Phase 3/4 currentness. Research
events do not change the evidence snapshot. Changed evidence/authority excludes
the round; history does not reactivate it. Transactions end before inference.

One attempt per round bounds ambiguity: started is not finished. Interrupted or
ambiguous attempts expire into an explicit failure, never silently rerun. A new
round is a separate attempt and never overwrites the first. No exactly-once
external billing claim is made. Unknown effort, cost and unperformed outcomes
remain null/UNKNOWN. Agreement means only action-type overlap, not correctness.

V1 permits one round per analyst/case, recovered through the metadata-only resume
route after browser interruption. It deliberately does not offer a second attempt
on the same case after exposure; a future independently authorized protocol would
be needed to distinguish repeat exposure. STARTED without FINISHED becomes
AMBIGUOUS after 65 server-clock seconds. It never automatically reruns inference.
Failures and abstentions remain in the event denominator. A timeout does not mean
that a provider performed no work. Ratings are append-only accountable human
interpretations; corrections append another rating. No ranking metric is emitted.

## Development-only setup and journey

Apply migration 0007 after the accepted 0001–0006 using the disposable migration
owner. Provision a separate `olin_research_t_<tenant UUID without hyphens>` login,
NOINHERIT/NOSUPERUSER/NOBYPASSRLS, granted ONLY `olin_investigator_research`.
The analyst runtime retains its existing runtime, canonical-reader and action
connections; add the research DSN as `OLIN_INVESTIGATOR_RESEARCH_DATABASE_URL`.
Do not inject any of those database credentials into the runner.

Start the runner in a separate sanitized process, not from the analyst's inherited
environment. Example using existing Python and a separately supplied dedicated
local transport token (not a model-provider credential):

```sh
env -i PATH="$PATH" PYTHONPATH="$PWD" \
  OLIN_SHADOW_RUNNER_CONFIG='{"mode":"fake"}' \
  OLIN_SHADOW_RUNNER_TOKEN='<dedicated-development-transport-token>' \
  python3 -m olin.investigator_shadow_runner --port 8087
```

For the existing separate analyst application configure
`OLIN_INVESTIGATOR_SHADOW_RUNNER_URL=http://127.0.0.1:8087`, its dedicated
`OLIN_INVESTIGATOR_SHADOW_RUNNER_TOKEN`, and
`OLIN_INVESTIGATOR_SHADOW_SYNTHETIC_CASES` as a JSON allowlist of operator-prepared
synthetic case UUIDs. The normal evidence setup/acceptance path remains Phase 5A's
separate synthetic operator. Research does not seed evidence.

Open that case, freeze the round, select a human action and rationale in the
existing workflow, generate the isolated attempt, and reveal. Inspect the explicit
fake provider/model label and untrusted suggestions; record usefulness with a
reason. Execute only the human-selected Phase 5A action via its existing controls.
The research history view links that performed action's durable transitions and
fresh supported coverage without showing stale proposals or credit conclusions.
The original choice never changes. Later choices after disclosure are labelled
post-exposure. No browser storage is added. Every response is no-store.

## Real adapter configuration (NOT authorization to run)

The runner's config must explicitly name mode `ollama`, a loopback
`http://127.0.0.1:<approved-port>/api/chat` endpoint, an already installed model,
`synthetic_only=true`, an accountable `approval_reference`, `max_requests` (1–20),
`max_input_tokens` (1–32768), `max_output_tokens` (1–2048), and `timeout_seconds`
(1–30). Input bytes including prompt/schema are conservatively bounded as tokens.
Budget is per approved runner process; restarting requires owner accounting and
must not be used to evade the approved resource budget. There are no transport
retries or fallback models. Coordinator configuration must also pin
`OLIN_INVESTIGATOR_SHADOW_PROVIDER=ollama` and `OLIN_INVESTIGATOR_SHADOW_MODEL` to
that exact model. Mismatches are invalid output. No remote/cloud provider or
provider credential is supported by this adapter. This implementation performs
no model installation or download. No real configuration/budget has been approved
in this task, so real-model evaluation remains NOT EXECUTED.

The runner has no registered model tools and is started without database/evidence,
action or provider credentials. Repository checks are not proof of OS/network
isolation: deployment custody, filesystem/network sandboxing, bank SSO, retention,
and real-data permissions remain separate prerequisites, not synthetic acceptance.

## Evaluation attribution

`tests/fixtures/shadow_evaluation_v1.json` freezes ten varied behavioral rubrics,
including three held-out cases. Rubrics, splits and forbidden conclusions remain
with the evaluator and are not sent in model payloads. Deterministic fake tests
exercise schema, abstention and plumbing only. They do not measure semantic model
quality, economic usefulness, calibrated information gain or repayment performance.
The prompt is versioned once; no real-model tuning was performed.

Real transport: Ollama local `POST /api/chat`, `stream=false`, structured output,
no tools, `think=false`. Documentation checked before implementation:
https://docs.ollama.com/api/chat and
https://docs.ollama.com/capabilities/structured-outputs . No default model.
Real mode requires explicit synthetic-only operator approval, model, endpoint,
finite resource/request/token/time budget. No model download or inference is
authorized merely by installing this candidate. Fake results are plumbing tests,
not evidence of model intelligence. REAL-MODEL EVALUATION PENDING.

## Case-scoped applicability amendment

`shadow-action-applicability-1` adds a versioned extension to `shadow-context-1`
without changing persistence, canonical authority, or `shadow-proposal-1` local
structural validation. Fresh projection, generation schema and post-currentness
disclosure/evaluator reporting use the same server-owned derivation. Historical
contexts can be classified offline, but that grants no renewed authorization.

| Existing action | Eligible unresolved target | Bounded effect |
| --- | --- | --- |
| REQUEST_ACCOUNT_CHANNEL_RECORD | BANK_ACCOUNT_COVERAGE with one supported observed bank subject/period and no complete same-scope attestation | Bank-account coverage only; not channel completeness, total or sustainable revenue |
| CLARIFY_MERCHANT_ASSERTION_SCOPE | REVENUE_CHANNEL_COVERAGE or additional_revenue_channels with one supported merchant revenue-claim subject/period | Attributed claim clarification only; not independent channel or amount verification |

Missing/ambiguous scope fails closed. Matching recorded period bounds do not
establish complete evidence-period coverage. Costs, debt and other uncovered
targets remain explicitly unsupported by these actions. Acquisition permission
is not established by research context; applicability never executes an action.

Original structurally VALID proposals are retained. Separate classifications are
APPLICABLE, NOT_APPLICABLE or REDUNDANT, with reason codes, server-owned scope and
capability descriptions. Every narrative remains REQUIRES_SEMANTIC_REVIEW.
`APPLICABLE_ACTION_TYPE_OVERLAP_V2` counts only applicable pairs for agreement;
agreement still does not establish truth or usefulness. Existing blinded selection
and fresh disclosure checks remain required. No keyword semantic judge is added.

Generation provenance advances to `shadow-prompt-4`,
`shadow-openai-structured-3`, and `shadow-openai-schema-2`. The catalogue remains
`investigator-action-catalogue-1.0`; its bounded descriptions are filtered into
the context alongside eligible pairs. Provider schema digests are context-specific
because action enums are narrowed. The full local acceptance schema is unchanged.
Prior prompts, receipts and outcomes remain historical, unmodified records.

Offline regression uses the six actual structured-batch proposals and exact saved
contexts. Five action/target pairs are applicable; the account-complete bank action
targeting revenue-channel coverage is NOT_APPLICABLE (unsupported target and
already-complete same-scope coverage). This is not semantic approval of the five.
The coverage-unknown and cost-debt-unknown contexts share the relevant economic
facts/unknowns; timestamps, aliases and bindings differ, and neither supplies an
investigation focus. Neither catalogue action directly investigates costs/debt.
Not choosing a hidden rubric focus is not demonstrated model failure.

This amendment performs no inference. Six historical requests remain exhausted.
Human ratings remain NOT_REVIEWED and unperformed outcomes UNKNOWN.
