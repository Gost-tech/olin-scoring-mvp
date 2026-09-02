# Olin bank integration pack

Status on 2026-09-01: **deployable candidate for a controlled real-data shadow UAT; not yet deployed or approved for production lending.** The software now includes managed-PostgreSQL enforcement, production preflight, short-lived sessions, controlled historical batch intake and an AWS reference runtime. Real-data use remains blocked until the deployed environment and the bank's external approvals pass.

Olin supplies evidence normalization and a versioned credit recommendation. The bank remains the official decision maker, system of record, lender, disburser, and collections owner. No Olin API endpoint moves money.

## Start here

1. Lock the single outcome in [PILOT_EXECUTION_PLAN.md](PILOT_EXECUTION_PLAN.md).
2. Complete and validate [pilot_manifest.example.json](pilot_manifest.example.json).
3. Read [GO_LIVE_GATE.md](GO_LIVE_GATE.md) before promising a launch date.
4. Review [ARCHITECTURE.md](ARCHITECTURE.md) with security, risk, data, and engineering.
5. Follow [API_INTEGRATION_GUIDE.md](API_INTEGRATION_GUIDE.md) in synthetic UAT.
6. For historical files, use [BANK_BATCH_INTAKE.md](BANK_BATCH_INTAKE.md).
7. Execute [UAT_AND_SHADOW_PLAN.md](UAT_AND_SHADOW_PLAN.md).
8. Assign every control in [SECURITY_CONTROL_MATRIX.csv](SECURITY_CONTROL_MATRIX.csv).
9. Use [sample_request_response.json](sample_request_response.json) as the terminology contract.

## Non-negotiable product boundary

`recommendation` is decision support, not an approval. The response explicitly returns `recommendation_scope: decision_support_only`, `requires_bank_decision: true`, and a separate `official_bank_decision` field. The bank must record its own outcome and retains veto authority.
