# Olin pharmacy shadow contract v2

Status: bank shadow decision support only. Olin does not issue the bank's credit decision.

## Bank sends

- Case identity: bank case reference, cohort, merchant, requested amount, purpose.
- Pharmacy classification: subtype and SCIAN `464111` or `464112`.
- Regulatory facts: whether controlled medicines are sold, applicable license status and the bank/provider evidence reference.
- Inventory facts: supplier count, top-supplier share, inventory days, expiry write-offs, gross margin and stockout rate.
- `bank_features_v2`: a six-month, MXN cash-flow feature contract.
- Facility terms: term, monthly rate, existing debt service, policy ceiling, target DSCR and stress assumptions.
- Consent, bureau, identity and geo evidence through their existing consent-bound routes.

The bank feature contract must classify operating inflows/outflows separately from internal transfers, debt proceeds and refunds. It must state account coverage, account-holder match, transaction-classification coverage, account count, period, calculation version, source and retrievable evidence reference.

## Olin enriches and reconciles

1. Confirms pharmacy subtype/SCIAN and builds the vertical evidence matrix.
2. Resolves provider trust from the server registry; the payload cannot make itself trusted.
3. Excludes internal transfers and debt proceeds from operating inflows.
4. Checks account and classification coverage before capacity is calculated.
5. Applies bank-configured term/rate, current obligations and base/stress cash flow.
6. Returns required/missing evidence, pharmacy-specific risks, source trust and an auditable amount rationale.

## Bank receives

- `requested_amount_mxn`: merchant request.
- `amount_evaluated_mxn`: amount inside the configured policy ceiling.
- `proposed_amount_mxn`: stress-supported principal, or `null` if evidence/trust is insufficient.
- Base and stressed normalized cash flow, payment, DSCR and assumptions.
- Pharmacy risks: regulatory gap, supplier concentration, expiries and stockouts.
- Evidence coverage and provider trust results.
- `COMMITTEE` routing until pharmacy repayment outcomes support bank-approved calibration.
- No statistical confidence interval. The legacy range is explicitly a non-statistical sensitivity range.

## Later outcome

The bank posts immutable performance events containing period end, DPD, balances and payments. Olin derives the DPD bucket server-side and retains the source attestation. These labels support cohort monitoring and eventual model validation; they do not retroactively rewrite the original recommendation.

See `test_pharmacy_vertical.py` for the executable fake-data acceptance journey.
