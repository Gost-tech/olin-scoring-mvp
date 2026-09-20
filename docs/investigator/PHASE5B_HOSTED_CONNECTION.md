# Phase 5B hosted connection — shadow-hosted-1

Original adapter acceptance record, before separately authorized execution:
implementation and mocked validation only; no transmission/spending approval or
real-model execution in that implementation session. This supplements the
accepted engineering baseline `90993ac594376e866e1a1bdc104caec4fa23b2ec` without
reopening its validator/evaluator acceptance.

## Narrow authority amendment

`shadow-hosted-1` extends the prior local-only research transport allowance ONLY
for the existing isolated evaluator worker, with explicit operator approval of
synthetic transmission and a finite USD budget. It permits one fixed destination:
`https://api.openai.com/v1/responses`, model `gpt-5.4-mini-2026-03-17`.
The ordinary Investigator application and its `ai.invoke=deny` contract remain
unchanged. Its HTTP shadow transport still permits only fake/Ollama identities;
hosted inference is not enabled in that application or browser. The evaluator
does not create a human comparison baseline or expose proposals before selection.
It writes private research artifacts, not evidence, action history or decisions.

No default real configuration, ambient provider-key lookup, tools, SDK, retry,
fallback, redirects, polling, background inference or additional dependencies.
Only the isolated worker reads the explicitly supplied dedicated credential file.
The coordinator passes its path, not its contents, via the worker's private stdin.
No credential goes into config JSON, run records, model inputs or browser config.
Worker environment remains sanitized and excludes all database/action/evidence
custody. File ownership/mode checks are not a production OS sandbox: the operator
must control local filesystem access and use a dedicated credential unavailable
to ordinary analyst processes. Do not start the evaluator from an analyst server.

Canonical setup, fresh pre/post-inference PostgreSQL checks, closed output schema,
atomic private artifacts and STARTED/AMBIGUOUS recovery are unchanged. No lock or
database transaction spans inference. Replays do not repeat billed attempts.
Only `coverage-unknown`, `account-complete`, `cost-debt-unknown` are observable;
the other seven rubrics retain their existing gap dispositions. Prompt, schema,
dataset digests and split are frozen. Rubrics and judgments never reach the model.

## Protocol and failure meanings

Historical protocol (superseded by the offline structured generation revision
below): Responses API JSON mode was used with the original full schema in the unchanged
instructions. This does not claim provider-enforced schema adherence: the existing
closed validator rejects invalid references, fields, content and bounds afterward.
The schema is NOT loosened to fit a provider-supported JSON Schema subset.
Requests use `store=false`, `stream=false`, `background=false`, standard service
tier, `reasoning.effort=none`, and `max_output_tokens=1024`. No reasoning summary
or hidden chain-of-thought is requested. Unexpected tools/reasoning items fail.
`store=false` is not a promise of zero provider retention; explicit synthetic-data
transmission approval must account for the provider's applicable data policy.

Provider refusal is REFUSAL; output exhaustion is INCOMPLETE; invalid/oversized
output is INVALID_OUTPUT. HTTP errors (including redirects), socket timeouts and
lost responses remain failed/ambiguous attempts, never fake successes or retries.
Timeout does not prove remote computation or billing stopped. Known token usage
is recorded on valid completion; unavailable usage/cost remains unknown. Raw
responses are bounded private research artifacts; an echoed full credential is
suppressed before artifact capture. No provider error text is printed to logs.

### Controlled compatibility correction (2026-09-19)

Transport payload version `shadow-openai-messages-1` puts the unchanged
`PROMPT + canonical(OUTPUT_SCHEMA)` into ONE developer input message and the
unchanged minimized context into ONE user input message. No duplicate top-level
instructions, answer hints, prompt/schema changes or inference-setting changes.
The canonical HTTP body is explicitly UTF-8 bytes; its SHA-256 and transport
version are recorded separately from the unchanged research input digest.
The [official JSON-mode guide](https://developers.openai.com/api/docs/guides/structured-outputs)
requires a JSON instruction in a conversation message and demonstrates input
messages. This layout avoids relying on a separate `instructions` field satisfying
the JSON-mode input check. The historical HTTP 400 retained insufficient provider
diagnostics to establish its cause; layout remains a compatibility hypothesis,
not a retrospective confirmed diagnosis.

Private worker diagnostics retain bounded HTTP status, allowlisted error code/type
and known request parameter, plus a format-validated `x-request-id`. Free-form
provider messages are suppressed entirely, including credential/input echoes;
unknown parameters/headers are suppressed, not copied to reports. This trades
message detail for safe diagnostics. A structured HTTP rejection does not establish
zero billing. Existing stop/replay behavior is unchanged for every HTTP failure.

### Offline structured generation revision (2026-09-19)

The final historical response omitted `references` from all three proposals.
JSON mode enforced JSON syntax, not required fields, and prompt two's citation
placement wording did not explicitly require the array. All eighteen narrative
fields passed; the response correctly remains INVALID_OUTPUT. Nothing in this
revision repairs or accepts that response. All three authorized requests are
exhausted. This implementation grants NO further inference authorization.

Current hosted payload version: `shadow-openai-structured-2`.
`text.format` is exactly `{type: "json_schema", name: "shadow_proposal",
strict: true, schema: provider_schema()}`. `provider_schema()` in
`olin/investigator_shadow_openai.py` makes a fresh deep copy of the unchanged
application `OUTPUT_SCHEMA` and performs only these adaptations:

- `schema_version.const` becomes equivalent `type: string, enum: [value]`.
- Nullable `action_type.enum` additionally specifies `type: [string, null]`.
- `references.uniqueItems` is omitted from the provider representation because
  it is not a documented supported keyword. Duplicate rejection remains mandatory
  in the unchanged local validator. This is not evidence of live provider support.

Keyword audit against the official
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
and [pinned model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini):
`type` (object/array/string/null), `properties`, `required`,
`additionalProperties: false`, `items`, `enum`, and `maxItems` are retained.
All object properties are required; root and proposal objects remain closed.
`minLength`/`maxLength` are retained for this non-fine-tuned model; the guide's
additional exclusion of those keywords applies to fine-tuned models. No
undocumented `uniqueItems`, conditional/composition keywords or `$ref` are sent.
The mapping test inverts the three adaptations and requires exact equality with
the original schema; it does not silently drop unknown future constraints.

The trusted developer message contains `shadow-prompt-3`; the unchanged minimized
context remains the user message. The schema is sent once in `text.format`, not
duplicated in prose. The entire UTF-8 HTTP body is bounded by the existing 16,384
input upper-bound units, including schema and catalogue framing. Model, endpoint,
reasoning effort, output/time limits and all failure/replay behavior are unchanged.
No JSON-mode fallback, retries, tools or response normalization are introduced.
Refusals and incomplete responses remain unsuccessful; every completed proposal
still passes the original membership, duplicates, content, bounds and abstention
checks. Structured syntax is not economic truth or evidence authority.

Transport schema version `shadow-openai-schema-1`, digest
`447128f8997c11b7856bf62fda59fff30aab097a0a5d2f625420e15390c5eeba`.
Worker diagnostics preserve it, payload version/digest, catalogue version and
guidance digest on both success and failure. Existing manifest/run prompt bindings
also bind the trusted catalogue guidance. Live compatibility of this exact new
payload remains untested: no request is authorized by this change.

The founder separately authorized one manual coverage-unknown compatibility
follow-up linked to the initial stopped run, as request TWO of the original THREE,
not a new budget. Preserve the original run unchanged. Reserve $0.304608 for its
unknown-cost first attempt and another $0.304608 for the follow-up ($0.609216
aggregate), within the original $1.00 ceiling. Use fresh canonical preparation,
a separately attributed private continuation record and `max_requests=1`; no
request for another case, restart of the stopped run, or automatic retry is allowed.
Approval and linked artifact hashes belong in the private execution record. This
documentation records authorization, not successful inference or product validation.

## Original proposed budget (approval recorded separately)

Official documentation checked 2026-09-19:

- [Model, pinned snapshot and standard pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini):
  $0.75 per million input tokens, $4.50 per million output tokens;
  cached input $0.075/M is not assumed. Context window 400,000 tokens.
- [Responses output cap](https://developers.openai.com/api/reference/cli/resources/responses/methods/create):
  max_output_tokens includes visible output AND reasoning tokens.
- [JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs):
  valid JSON is not schema compliance or economic correctness.

At 16,384 input-token units and 1,024 output tokens, three requests estimate
`3 × (16384 × 0.75 + 1024 × 4.50) / 1,000,000 = $0.050688`.
Input admission uses UTF-8 bytes of context + prompt/schema, not a tokenizer or
proof of provider framing overhead. Therefore the enforced spending reservation
uses the ENTIRE 400,000-token context window per request instead:
`3 × (400000 × 0.75 + 1024 × 4.50) / 1,000,000 = $0.913824`.
This deliberately conservative standard-price inference bound includes output
reasoning, assumes no cache discount, no tool charges, and excludes taxes/FX.
Proposed total approved inference budget: **USD 1.00**, at most three sequential
requests, one per eligible case, no retries. A smaller request count reserves
proportionally; configurations above USD 1.00 or below reservation are rejected.
Price/model changes require a reviewed change, never an automatic substitution.
Reconfirm published rates before authorizing execution. Model access is untested.

The evaluator's durable receipts count ambiguous attempts against the request
cap. The runner also has a process-local cap. A new directory/process is NOT new
spending permission: the accountable operator must prohibit additional runs under
the same approval. This is not a cross-host billing ledger or exactly-once billing
guarantee. Dashboard alerts are supplementary, not the spending control.

## Secure setup AFTER separate explicit approval

Do not paste keys in chat, shell arguments/history, repository files, `.env`, or
browser config. Do not reuse/search legacy credentials. Have the accountable
operator securely provision a dedicated project credential into an absolute,
owner-only regular file outside the repository (0600, private parent directory),
using an approved local secret-manager/editor workflow. Only the isolated worker
opens that explicit path; symlink credential files and group/world access fail.
Keep the application process unable to read the file. No credential is needed for
mocked tests or configuration validation.

After transmission and spending are explicitly approved, create a private 0600
configuration file outside the repository with the following NON-SECRET fields.
The two references must identify actual accountable approvals, not placeholders:

```json
{
  "mode": "openai",
  "endpoint": "https://api.openai.com/v1/responses",
  "model": "gpt-5.4-mini-2026-03-17",
  "authority_amendment": "shadow-hosted-1",
  "synthetic_only": true,
  "synthetic_transmission_approved": true,
  "approval_reference": "REPLACE-WITH-ACTUAL-SPENDING-APPROVAL",
  "transmission_approval_reference": "REPLACE-WITH-ACTUAL-TRANSMISSION-APPROVAL",
  "max_requests": 3,
  "max_input_tokens": 16384,
  "max_output_tokens": 1024,
  "timeout_seconds": 30,
  "total_budget_usd": "1.00"
}
```

Prepare a NEW real-run directory through the existing approved synthetic operator
instructions in PHASE5B_EVALUATION.md. Do not reuse a completed fake-run directory
or historical manifests whose disposable database no longer exists. Remove
canonical-writer credentials from the coordinator environment after preparation.
Keep only the existing authorized read/currentness connections. Then, and only
after explicit execution approval:

```sh
python3 -m scripts.evaluate_investigator_shadow real \
  --tenant <authorized-development-tenant-uuid> \
  --directory output/shadow-openai-approved-run \
  --config /absolute/private/approved-openai.json \
  --credential-file /absolute/private/dedicated-openai-key
```

The credential path is not authorization. Neither is a key, balance, prepared
manifest or digest. No model output establishes truth, usefulness, credit
performance or authority. Human evaluation remains NOT_REVIEWED; unperformed
investigation outcomes remain UNKNOWN. Final product validation remains pending.

## Focused independent review attribution

`/root/hosted_adapter_review` performed one source-only independent review of
this adapter/evaluator extension, not a repeat of settled Phase 5B acceptance.
Judgment: GO for engineering candidate, high confidence within trusted local
operator custody, subject to implementation/CI gates. One low-severity malformed
content classification observation was corrected with explicit list/object checks
and a regression; the same reviewer's source-only recheck closed it. No outstanding
findings were reported. The reviewer executed no tests or inference. Test/CI
evidence belongs to the implementation session and CI, not to that reviewer.
API compatibility, provider access, OS isolation and model usefulness are unproven.
