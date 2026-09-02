# Hosted bank-linking acceptance

Date: 20 August 2026  
Mode: production-shadow, synthetic UAT data  
Result: **PASS**

## Tested lifecycle

`CREATED → CONSENTED → LINK_PENDING → EVIDENCE_READY → SCORING → SCORED`

The acceptance tests proved:

- A partner can create an intake before an `application_id` exists.
- A second partner receives `404` for the intake.
- Scoring before evidence returns `422`.
- Consent text is hashed and versioned.
- Link tokens are random, stored only as hashes and exchanged once.
- A reused link token returns `401`.
- A signed intake callback is accepted; replay produces one stored event.
- Intake evidence excludes raw transactions, CLABE and credentials.
- Only an evidence-ready intake can create a scored application.
- The same intake cannot be scored twice.
- The scored application carries the consent hash, not duplicate consent text.
- Consent withdrawal cancels the link and causes later callbacks to return
  `401`.

## Reproduction

```bash
python3 -m unittest -v test_hosted_linking
```

## External certification dependency

The provider-neutral Olin lifecycle is implemented. Production still requires
one adapter that exchanges the Olin bootstrap for the selected bank or Syncfy
Widget session using server-side commercial credentials. This dependency
cannot be completed with fake credentials and must be certified with the
provider, but it does not require redesigning Olin's case or consent model.
