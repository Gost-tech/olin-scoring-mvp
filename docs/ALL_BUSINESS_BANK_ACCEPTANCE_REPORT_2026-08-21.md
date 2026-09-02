# Olin all-business bank acceptance report

## Verdict

**PASS for synthetic bank UAT. NO-GO for real-data production.**

The production code path was exercised with synthetic evidence for all 20 supported business types. Every case completed input validation, trusted source resolution, archetype-specific operating-profile validation, cash-flow reconciliation, stressed capacity, committee routing, independent bank decision, immutable repayment outcome and persisted retrieval.

All 20 cases routed to `COMMITTEE`. No type is auto-approved unless a bank/model-risk owner explicitly adds it to `OLIN_VALIDATED_AUTO_APPROVE_TYPES` after approved historical validation.

## Types tested

`abarrotes`, `jugueria`, `taqueria`, `restaurant`, `retail`, `services`, `health_beauty`, `professional`, `transport`, `light_manufacturing`, `wholesale`, `ecommerce`, `construction`, `agriculture`, `hospitality`, `education`, `healthcare`, `pharmacy`, `logistics`, and `other`.

## Negative tests

- Unregistered bank-feature source: proposed amount suppressed; manual review required.
- 50% account coverage: proposed amount suppressed; manual review required.
- Negative normalized/stressed cash flow: proposed amount zero.
- Missing Feature Contract v2: no proposed amount and committee routing.
- Feature window shorter than 90 days: request rejected.
- Real-data mode with configuration strings but no runtime Postgres adapter: startup/case path blocked.
- Replayed outcome after trust-attestation rotation: original immutable trust snapshot returned.
- Empty/synthetic outcome portfolio: historical validation readiness remains false.

## Adversarial findings corrected

- Real-data configuration could previously fall through to SQLite.
- Legacy capacity could appear as a proposed amount when Feature Contract v2 was absent.
- A synthetic invalid RFC caused every all-business case to decline while the first acceptance assertion still passed.
- Abarrotes could auto-approve without bank/model-risk validation.
- Outcome feeds could be recorded without a trusted source.
- Pharmacy license sufficiency did not initially require trusted provenance.
- Trust attestations could omit expiry.
- All business types initially shared generic evidence without structured archetype metrics.

## Verification

- Full project test suite: 94/94 passed.
- All-business acceptance: 20/20 business types passed.
- Focused bank/security/infrastructure tests: 17/17 passed.
- Python compilation, JSON validation and `git diff --check`: passed.
- OpenAPI breaking-change detector: zero breaking or potentially breaking changes.
- API linter: zero errors; legacy design debt remains (D/69.48 scorecard, principally pagination, response consistency and developer-experience warnings).

## Remaining launch gates

1. The Terraform module has not been applied inside an approved AWS account.
2. The Olin runtime still lacks its PostgreSQL adapter; real-data mode is intentionally blocked.
3. A backup restore has not been executed and evidenced.
4. Bank/provider contracts and attestation identifiers remain examples.
5. No real historical cases or repayment outcomes were provided; no type is statistically validated.
6. Bank security, privacy, model-risk and analyst UAT approvals have not been issued.

Synthetic success proves control behavior, not credit performance.
