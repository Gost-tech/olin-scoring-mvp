# Phase 4: deterministic economic reconstruction

## Boundary

Phase 4 is an immutable, synchronous, in-memory transformation over the exact
`ClaimsAssessment` created by Phase 3 inside the approved PostgreSQL currentness
transaction. A public `ClaimsAssessment`, its Python type, or its serialized form
does not establish acceptance. The fixed wrapper binds the assessment identity and
canonical digest to the live readiness capability, checks Phase 3 versions and all
tenant, case, snapshot, authority, and evidence-state fields, rechecks server
currentness immediately before reconstruction, retains the final checks after the
eager result is built, and records the server-checked time and canonical projection
version in the result binding.

The kernel performs no acquisition, verification, persistence, network or provider
call, model invocation, scoring, credit decision, pricing, facility construction,
or money movement. Its output is historical analytical data and grants no ongoing
authority.

## V1 value and status model

V1 distinguishes `OBSERVED_VALUE`, `CLAIMED_VALUE`, `DERIVED_VALUE`,
`CONSTRAINED_RANGE`, `ESTIMATED_RANGE`, `UNKNOWN_VALUE`, and `SCENARIO_VALUE`.
A derived value is deterministic arithmetic over accepted inputs and records its
formula, rule version, proposition digests, provenance, period, unit, and
assumptions. V1 defines a constrained-range shape but emits no range without
evidence-supported bounds. The estimated-range and scenario categories are
explicitly reserved so they cannot be confused with observations or deterministic
derivations; no V1 rule emits either category.

Each dimension is `SUPPORTED`, `PARTIALLY_SUPPORTED`, `INSUFFICIENT_INPUT`, or
`CONTRADICTED`, with a reason. These are reconstruction
statuses, not credit ratings or default probabilities.
Claimed values alone remain `INSUFFICIENT_INPUT`; they are preserved but do not
become evidentiary support. Unknown quantities and dimension statuses bind their
input proposition digests, deduplicated provenance, and contradiction rule IDs.

The coverage diagnostics are bank-account, revenue-channel, cost, debt, and period
coverage. Each is `COMPLETE`, `PARTIAL`, or `UNKNOWN`. Only a Phase 2
proposition-specific verified fact under schema version 1, exact coverage
proposition type, and unit `STATUS` can establish one of these states. Claims do
not establish coverage. Missing, invalid, or conflicting coverage metadata yields
`UNKNOWN`. Coverage retains its subject, period, proposition digests, and
provenance. A derivation may use it only for the same subject and exact period.

Absence of a finding or input never means healthy economics, complete coverage,
zero costs, zero debt, or zero risk. Unsupported totals remain explicit unknowns.

## Closed V1 proposition vocabulary

Direct values retain their original proposition meaning:

- `bank_visible_inflows` becomes observable bank inflows, never total revenue.
- `monthly_revenue` remains verified total monthly revenue or claimed total monthly
  revenue according to its Phase 3 class.
- `monthly_operating_costs`, `monthly_operating_cash_inflows`,
  `monthly_operating_cash_outflows`, `monthly_debt_service`, and `working_capital`
  retain those exact meanings.
- `bank_account_coverage`, `revenue_channel_coverage`, `cost_coverage`,
  `debt_coverage`, and `period_coverage` are coverage metadata, not economic values.

Other proposition types and other proposition schema versions remain accepted
Phase 3 metadata but do not acquire a new economic interpretation in V1. Monetary
values must be finite, bounded decimals denominated in the explicitly supported
V1 currencies MXN or USD. Arithmetic uses a versioned 28-significant-digit decimal
context and rejects non-finite or out-of-domain results. Negative working capital is permitted;
negative revenue, inflows, costs, outflows, and debt service are not reinterpreted
as economic values.

## Derivations and normalization

The first target derives only the arithmetic reconciliation gap:

`claimed monthly revenue - observable bank inflows`

It does so only for the exact compatible Phase 3 material-disagreement finding.
The result explicitly states that the difference does not prove missing revenue,
false revenue, or sustainable revenue. Phase 3 unknowns and contradictions pass
through unchanged.

V1 does not emit operating margin because its accepted propositions do not prove
compatible gross/net, tax, accounting, and cost-category bases. Even complete
coverage metadata cannot establish those economic semantics. Net operating cash
movement requires compatible verified operating inflow and outflow propositions,
complete period coverage for the same subject and exact period, and no relevant
contradiction. Arithmetic preserves the accepted input scope; it does not promote
`UNSPECIFIED` components to `BUSINESS_TOTAL`. Missing inputs produce unknowns.
Multiple compatible subject/period groups are reconstructed independently; an
unrelated or historical group cannot suppress an otherwise complete group.
V1 unresolved quantities are dimension-level diagnostics: when only some period
groups reconstruct, the unknown binds all considered proposition digests and
provenance but does not identify a single unresolved period.

V1 never treats one debt-service proposition as the total obligation schedule and
does not aggregate debt instruments. Total debt service therefore remains explicit
unknown even when an individual obligation and coverage metadata are present.
Likewise, an operating-cost observation whose accepted dimensional scope is
`UNSPECIFIED` remains observable but cannot by itself close total cost structure.

V1 supports only three explicit verified-cost normalizations:

- daily to monthly: multiply by 30, using a stated 30-day standard month;
- weekly to monthly: multiply by 52 and divide by 12;
- annual to monthly: divide by 12.

The proposition types are respectively `daily_operating_costs`,
`weekly_operating_costs`, and `annual_operating_costs`. The unit is preserved; no
currency conversion occurs. V1 accepts only exact one-day, seven-day, and 365-day
source periods respectively, and emits the normalized monthly equivalent over an
explicit 30-day target period beginning at the source-period start. Phase 4 does
not normalize incompatible periods, gross versus net, tax treatment, or business
versus personal flows.

## Target case

The 260,000 MXN merchant revenue assertion remains a claim. The 118,000 MXN
bank-visible inflow proposition remains an observation. Their 142,000 MXN
difference is a deterministic reconciliation gap. Total sustainable revenue,
additional channels, and account coverage remain unresolved. No midpoint,
supported revenue range, fraud conclusion, credit score, PD, decision, loan amount,
or facility recommendation is produced.

No Phase 4 result persistence is authorized by this contract.
