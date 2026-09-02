# Olin bank integration acceptance report

Date: 20 August 2026  
Environment: clean local production-shadow instance  
Data: synthetic bank UAT case  
Result: **PASS**

## Executive result

Olin completed the full bank-orchestrated shadow journey. The test created a
case, produced a `COMMITTEE` recommendation with score `80.8`, accepted signed
derived bank metrics, enforced partner separation and correction duties,
recorded the bank's independent decision, and blocked disbursement.

All credentials and the database were temporary and destroyed after the test.
The report contains no secret, raw transaction, CLABE or real customer data.

## Acceptance matrix

| Bank test | Expected | Actual | Result |
|---|---:|---:|---:|
| Production readiness | 200 | 200 | PASS |
| Missing authentication | 401 | 401 | PASS |
| Partner creates shadow case | 201 | 201 | PASS |
| Second partner reads case | 404 | 404 | PASS |
| Partner reads consent evidence | 200 | 200 | PASS |
| Invalid bank signature | 401 | 401 | PASS |
| Valid signed metrics | 201 | 201 | PASS |
| Replayed callback | 200 idempotent | 200 idempotent | PASS |
| Derived evidence retrieval | 200 | 200 | PASS |
| Partner opens correction | 201 | 201 | PASS |
| Partner resolves own correction | 403 | 403 | PASS |
| Analyst resolves correction | 201 | 201 | PASS |
| Bank records official outcome | 200 | 200 | PASS |
| Shadow disbursement attempt | 403 | 403 | PASS |
| Stored bank events after replay | 1 | 1 | PASS |
| Database disbursed flag | 0 | 0 | PASS |

## Audit evidence

The immutable audit sequence contained:

1. `case_scored`
2. `consent_recorded`
3. `bank_evidence_ingested`
4. `correction_requested`
5. `correction_resolved`
6. `partner_decision_recorded`

## Reproduction

```bash
python3 -m scripts.bank_acceptance_test
```

The executable acceptance test generates new temporary credentials, database
and identifiers on every run. It exits non-zero if any expected control fails.

## CTO conclusion

The current architecture is ready for a bank-controlled sandbox and a small
shadow cohort using bank-orchestrated derived metrics. It is not approval for
real-money lending, public origination or Olin-hosted account linking. The bank
must still approve the consent wording, callback mapping, infrastructure and
operational ownership in its own environment.
