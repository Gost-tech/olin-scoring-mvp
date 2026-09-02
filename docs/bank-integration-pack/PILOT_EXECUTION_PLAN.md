# Olin pilot execution plan

## The one objective

Complete one bank-controlled, ten-case shadow pilot that proves workflow value,
secures an outcome-data contract, and ends with a documented paid-deployment
decision. Olin remains decision support; the bank owns every credit decision.

The ten cases validate integration, consent, auditability, analyst usability,
and operational safety. They do **not** validate default prediction. Credit
validation requires the larger labeled cohort and observation window specified
by bank model risk in the outcome contract.

## Product freeze

Until the joint pilot report is complete, do not add scoring signals, launch a
second product, enable money movement, or claim predictive accuracy. Fix only a
pilot blocker, a security defect, a contractual API defect, or an agreed UAT
failure.

## Execution sequence

| Gate | Work | Exit evidence | Owner |
|---|---|---|---|
| 0. Commercial | Name institution, procurement owner, price hypothesis, and paid-conversion decision | Signed shadow agreement and conversion path | Founder + bank procurement |
| 1. Scope | Lock ten-case ceiling, three evidence routes, selection rule, outcome label/window, targets, and stop conditions | Completed pilot manifest | Bank credit/model risk |
| 2. Synthetic UAT | Run valid, malformed, duplicate, cross-tenant, withdrawn-consent, stale-data, and outage cases | Signed UAT results; zero failed critical controls | Bank engineering + Olin |
| 3. Security/privacy | Review data flow, consent, retention, deletion, correction, access, incident, and kill switch | Written approvals with evidence references | Bank security/privacy |
| 4. Controlled shadow | Run at most ten authorized cases; bank decision remains independent | Ten complete audit trails and bank outcomes | Bank analyst + operations |
| 5. Joint report | Compare workflow time, missing evidence, overrides, agreement, and incidents | Signed report; no prediction claim | Credit risk + Olin |
| 6. Conversion | Decide paid implementation and larger outcome cohort | Signed next phase, owner, budget, and date—or explicit stop | Procurement + sponsor |

## Mandatory measurements

- consent, provenance, recommendation reconstruction, and bank-outcome coverage;
- bank baseline versus Olin-assisted analyst turnaround time;
- missing evidence and provider failures by evidence route;
- recommendation-versus-bank agreement and override reasons;
- security, privacy, tenant-isolation, and money-movement incidents;
- eventual repayment outcome under the bank-defined label and window.

Agreement is descriptive. It is not evidence that Olin predicts repayment.

## Who does what next

Olin/Codex can maintain the API contract, generate synthetic cases, execute
automated tests, repair defects, export audit evidence, and produce the joint
report template. Brice must obtain the bank name, named owners, signed
agreements, credentials, approvals, outcome-data commitment, procurement path,
and analyst time. The bank must define credit labels and policy; Olin must not
invent them.

## Daily operating rule

Operations reviews exceptions daily. The kill-switch owner stops intake on any
declared stop condition. A security, consent, tenant-isolation, audit-history,
or unauthorized-money-movement failure returns the pilot to synthetic UAT.

## Enforced readiness check

Copy `pilot_manifest.example.json`, replace every placeholder, attach evidence
references, then run:

```bash
python3 -m scripts.pilot_gate path/to/pilot_manifest.json
```

`READY_FOR_CONTROLLED_SHADOW` means every required declaration is present. It
does not independently authenticate signatures or replace bank approval. A
`NO_GO` result lists the exact missing decisions and evidence.
