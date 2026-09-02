# Controlled historical batch intake

Olin accepts a maximum of ten historical shadow cases through an operator-run import inside the approved environment. It does not expose a public file-upload endpoint.

## Transfer sequence

1. The bank creates the approved JSON bundle using the Olin case schema.
2. The bank records the file SHA-256 in the transfer manifest.
3. The file enters the approved encrypted transfer location.
4. An operator runs the importer without `--commit`. This validates the checksum, schema, classification, authorization artifact, evidence fields and all ten cases without writing them.
5. Invalid files remain outside the application database. The validator never echoes source rows.
6. After the validation report is approved, the operator repeats the command with `--commit` and a named partner ingestion actor.
7. Olin returns only the batch/cohort identifiers, pseudonymous partner case references and generated application IDs.

## Command

```bash
python -m scripts.import_bank_batch approved-batch.json \
  --expected-sha256 <manifest-sha256>

python -m scripts.import_bank_batch approved-batch.json \
  --expected-sha256 <manifest-sha256> \
  --actor bank_ingestion \
  --commit
```

The commit command fails unless the real-data production preflight passes.

## Bundle envelope

```json
{
  "schema_version": "olin-bank-shadow-batch-1.0",
  "batch_id": "bank-batch-001",
  "cohort_id": "shadow-uat-001",
  "institution_reference": "BANK-DATA-TRANSFER-88",
  "data_classification": "pseudonymized_historical",
  "data_authorization": {
    "basis_label": "bank_documented_instruction",
    "approval_reference": "BANK-PRIVACY-204",
    "approved_by": "bank_privacy_owner",
    "approved_at": "2026-09-01T12:00:00-06:00",
    "scope_sha256": "<sha256-of-approved-scope>"
  },
  "cases": []
}
```

`data_authorization` is an audit artifact. Its presence does not mean Olin has determined that the bank's legal basis is sufficient.

## Rejected content

- More than ten cases.
- Prospective applicants; they use the hosted consent/intake flow.
- Raw transactions or transaction arrays.
- Passwords, credentials, access/refresh tokens, private keys or secrets.
- A classification that differs from the deployed environment.
- Duplicate partner case references.
- Missing or malformed approval references and scope digest.
- A file whose SHA-256 differs from the approved transfer manifest.
