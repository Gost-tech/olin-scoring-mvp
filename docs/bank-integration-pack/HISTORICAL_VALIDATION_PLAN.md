# Historical pharmacy shadow validation plan

This plan must be approved by the bank's credit-risk and model-risk owners before results are interpreted.

## Frozen definitions

- Unit: one independently originated pharmacy credit case.
- Index date: date on which the bank had all information used by its original decision.
- Primary outcome: bank-approved 90+ DPD/default definition inside the agreed 12-month observation window.
- Secondary outcomes: 30+ DPD, 60+ DPD, restructuring, charge-off and paid-off.
- Engine: frozen code version, feature-contract version, capacity version and source-registry snapshot.
- Leakage control: Olin receives only information observable at the index date; later repayment fields are isolated until scoring is frozen.

## Required sample

The bank supplies every eligible case in the agreed date range, not a hand-selected success sample. Exclusions and missing-data reasons are counted. Results are reported overall and, where sample sizes allow, by pharmacy subtype, requested-amount band, geography, tenure and evidence route.

## Measures

- Coverage and missingness by field/source.
- Agreement with bank decision as workflow context, not model accuracy.
- Bad rate by Olin score/tier and proposed-amount band.
- Discrimination: ROC-AUC and precision-recall AUC with bootstrap intervals.
- Calibration: observed versus predicted risk only after a probability model exists; the current heuristic score must not be called probability.
- Capacity: 30+/90+ DPD by stressed DSCR and proposed/requested ratio.
- Fairness and stability using bank-approved, legally permissible groups and drift measures.
- Operational value: analyst time, turnaround time, manual touches and override reasons.

## Acceptance rule

The bank pre-registers thresholds, exclusions, minimum sample sizes and stop conditions. Olin remains committee-only if outcome labels are incomplete, leakage is found, source trust is not reproducible, confidence is too wide, or performance is unstable across material segments. Synthetic tests validate software only and never satisfy this plan.
