# Olin Shadow Pilot Runbook

This runbook is for the first 10 authorized abarrotes cases. Olin is a
decision-support tool in this pilot. The partner keeps the official credit
decision and no money is disbursed.

## Before the first case

1. Obtain written approval from the partner for the shadow workflow and the
   exact evidence it may share.
2. Have Mexican counsel approve the consent text, privacy notice, retention
   period, and access policy.
3. Create one named API key per user in `.env`:

   ```text
   OLIN_MODE=production
   OLIN_API_KEYS={"brice":"long-random-token","partner_analyst":"another-long-random-token"}
   ```

4. Use a new, encrypted production database. Never copy the synthetic demo
   database into production.
5. Decide the cohort identifier, for example `shadow_2026_08`.
6. Agree with the partner on what counts as verified bank evidence and
   verified distributor evidence.

## Start the workspace

```bash
python3 -m olin.server --no-seed --no-open
```

Open:

- `http://127.0.0.1:8080/` for the case queue;
- `http://127.0.0.1:8080/nuevo` for a new shadow case.

The browser asks for the named user's token on the first authenticated
request. The HTML shell itself contains no case data; the queue, exports, and
all case actions remain unavailable until the API accepts that token.

## Process one case

1. Confirm that the merchant is part of the authorized cohort.
2. Record the partner case reference.
3. Paste the exact approved consent text and select the channel used.
4. Enter merchant identity and INE-review status.
5. Enter the Círculo result obtained under that consent.
6. Enter bank and FMCG evidence:
   - select the true source;
   - add a retrievable evidence reference;
   - mark verified only after the agreed check is complete.
7. Add optional Maps, IMSS, tenure, and TPV evidence only when observed.
8. Submit the case.
9. Read the Olin route, tier, DSCR, score, missing evidence, and reasons.
10. The partner records its independent approved, declined, or pending
    decision and its reason.
11. Export the cohort CSV from the queue.

## Never do during this pilot

- Do not give the public a loan-application link.
- Do not describe an Olin route as the partner's approval.
- Do not mark agent-stated numbers as verified evidence.
- Do not upload synthetic cases to the production database.
- Do not disburse or collect money from this workspace.
- Do not claim predictive accuracy from 10 cases.

## Stop conditions

Pause the pilot immediately if any of these occurs:

- a case is visible without authentication;
- a shadow case reaches a money-movement connector;
- consent or evidence provenance is missing;
- a case cannot be reconstructed from stored inputs;
- the partner decision is overwritten or lost;
- real and synthetic data are mixed.

## Pilot completion

The cohort is complete when all 10 rows have:

- consent timestamp and channel;
- cohort ID and partner reference;
- source and verification status for every supplied evidence block;
- Olin engine version, route, tier, score, and reasons;
- partner decision and rationale;
- an audit trail for scoring, consent, and partner decision.

The output is a joint workflow report, not a default-rate study. The next
decision is whether to run a larger validation sample, change the workflow,
or stop. Live lending requires a separate legal, risk, capital, security, and
operating approval.
