# Phase 5B isolated synthetic shadow research — version 1

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
