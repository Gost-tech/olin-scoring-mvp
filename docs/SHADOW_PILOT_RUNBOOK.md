# Olin Shadow Pilot Runbook

This runbook is for the first 10 authorized multi-sector small-business cases.
Olin is a decision-support tool in this pilot. The partner keeps the official
credit decision and no money is disbursed.

## Before the first case

1. Obtain written approval from the partner for the shadow workflow and the
   exact evidence it may share.
2. Have Mexican counsel approve the consent text, privacy notice, retention
   period, and access policy.
3. Create one named user per person in `.env`:

   ```text
   OLIN_MODE=production
   OLIN_USERS={"partner_operator":{"token":"long-random-token","role":"partner"},"credit_analyst":{"token":"another-long-random-token","role":"analyst"}}
   ```

4. Use a new, encrypted production database. Never copy the synthetic demo
   database into production.
5. Decide the cohort identifier, for example `shadow_2026_08`.
6. Agree with the partner on what counts as verified evidence for each route:
   - inventory-led: bank, supplier receipts and distributor confirmation;
   - TPV-led: settlement history, transaction consistency and bank flow;
   - bank-flow-led: deposits, outflows, invoices or another partner-approved
     record of recurring activity.

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
4. Enter merchant identity, business type, funding purpose, project
   description and INE-review status.
5. Select the agreed evidence route for the case.
6. Enter the Círculo result obtained under that consent.
7. Enter the available evidence:
   - select the true source;
   - add a retrievable evidence reference;
   - mark verified only after the agreed check is complete.
8. Add Maps, IMSS, tenure, TPV, supplier or invoice evidence only when
   observed and permitted by the pilot agreement.
9. Submit the case.
10. Read the Olin route, tier, DSCR, score, missing evidence, and reasons.
11. Confirm that a non-calibrated sector has not received an automatic route.
12. The partner records its independent approved, declined, or pending
    decision and its reason.
13. Export the cohort CSV from the queue.

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
