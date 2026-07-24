# Olin 30-Loan Pilot Runbook

## Pilot rule

Launch only with abarrotes, one analyst decision per application, and no more
than 30 disbursed loans until repayment outcomes are reviewed. An engine
auto-approve is a recommendation; the analyst must still approve it and write
a reason. Engine declines cannot be overridden during the pilot.

## Before the first live application

- Use `OLIN_MODE=production` and a clean `olin_production.db`.
- Confirm the analyst token and webhook secret are stored outside source code.
- Confirm STP is production-configured and perform a low-value controlled test.
- Verify backup creation and restoration on another copy of the database.
- Assign named owners for underwriting, disbursement, collection, incidents,
  privacy requests, and daily reconciliation.
- Approve a written credit policy covering eligibility, exceptions, ticket
  limits, declines, affordability, and committee quorum.
- Obtain qualified Mexican legal/compliance review before handling live credit
  and identity data.

## Per-application checklist

1. Confirm identity, INE, RFC/phone, business address, and destination CLABE.
2. Record a numeric Círculo score or confirmed no-file result.
3. Verify bank evidence and save its source reference and observation date.
4. Verify FMCG evidence and save its source reference and observation date.
5. Review DSCR inputs, internal score, tier, confidence interval, fraud flags,
   and requested-versus-approved amount.
6. Record the committee/analyst decision and a specific rationale.
7. Independently confirm beneficiary name and CLABE before disbursement.
8. Record the STP folio and confirm the loan is active only after STP accepts it.

## Daily operations

- Reconcile each incoming STP event against the payment ledger and bank/STP
  settlement report; never edit a payment row to force a match.
- Review unmatched, duplicate, partial, and overpaid transfers.
- Run `python3 -m jobs.daily --db olin_production.db` and resolve every reported
  issue the same day.
- Contact overdue borrowers using an approved script and record every action.
- Back up the database and verify the latest backup exists.
- Review access logs and rotate any credential suspected of exposure.

## Outcome data required for every disbursed loan

- Application ID and immutable scoring timestamp
- Model version, tier, score, DSCR, Círculo band, approved amount, fixed cost
- Raw verified evidence with source, verification state, reference, and date
- Analyst decision, rationale, analyst identity, and decision timestamp
- STP folio and disbursement timestamp
- Every payment event ID, installment, amount, timestamp, and raw event
- Final status: paid on time, paid late, defaulted, or defaulted/recovered
- Days to full repayment and any collection actions

Do not train on demo records, applications that were never disbursed, active
loans, or outcomes that have not reached a final state. Preserve late and
recovered outcomes instead of collapsing everything into a single repaid flag.

## Stop conditions

Pause new disbursements immediately if any of these occurs:

- A demo/mock application reaches production or a production payment reaches
  the sandbox
- A transfer is sent without a valid analyst decision and rationale
- STP and the Olin ledger disagree on amount, beneficiary, or status
- Webhook authentication fails repeatedly or duplicate events cannot be
  explained
- The daily job or backups fail
- Two defaults occur before 10 loans mature, or observed losses exceed the
  pilot risk limit approved by the credit owner

The last threshold is deliberately conservative and should be replaced by a
formally approved pilot risk appetite before launch.
