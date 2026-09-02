# Evidence Passport v2 — verified-evidence routing

**Status:** engineering contract implemented and tested for synthetic UAT.  
**Decision use:** evidence routing for human partner review only.  
**Not established:** legal approval, bank policy approval, a production KYC
vendor, real-data authority, or predictive validation.

## KYC decision

Olin does **not** need to purchase a KYC vendor for synthetic UAT. The code uses
a replaceable verifier interface and a deterministic adapter that is disabled in
pilot and production modes.

Before any real case, use this order:

1. Ask the institution whether its existing KYC/KYB result can be delivered as
   an attested reference. Reuse the bank-approved flow when possible.
2. Ask whether Círculo's Identity Data product is already within the partner's
   affiliation and approved purpose.
3. Only procure a separate provider if neither route supplies the required
   identity result with acceptable security, consent, retention, and evidence.

Possible products for a controlled evaluation—not endorsements—include:

- [Círculo Identity Data API](https://developer.circulodecredito.com.mx/producto/identity-data-api-simulacion),
  which describes an identity-validation API and requires separate production
  onboarding.
- [Incode Mexico government verification](https://developer.incode.com/docs/system-of-record-mexico),
  which documents INE data/face verification.
- [Truora identity verification](https://www.truora.com/es/productos/validacion-identidad-digital-facial-documento),
  which describes Mexico document and facial-verification support.

Commercial claims must be verified through diligence and a pilot. No provider
is activated in `config/trusted-sources.example.json`; the example entries stay
`inactive` until contract, privacy, security, and partner acceptance evidence is
recorded.

## What KYC can and cannot prove

| Question | KYC result may support | Separate proof still required |
|---|---|---|
| Is this a real person presenting a valid ID? | Yes, within the provider's documented method and limitations | Partner acceptance and fraud exception handling |
| Does the person own a sole-proprietor business? | Only if the approved workflow verifies the person-to-business link | RFC/business evidence and partner policy |
| Can the person bind a legal entity? | Usually not from identity alone | Powers/appointment and corporate-authority review |
| Is the person a beneficial owner? | A KYB/UBO product may support this | It still does not prove signing authority |
| Did the person consent to this data use? | No | Versioned purpose-specific consent artifact |
| May a credit bureau be queried? | No | Separate institution/Círculo-approved authorization |
| Can the business repay? | No | Independent capacity evidence and bank credit policy |

## Implemented controls

- Assessments accept evidence IDs, not caller-provided “verified” labels.
- Each record is bound to one case tenant and active consent record.
- Sources must be active and authorized for the exact evidence type in the
  server-controlled trust registry.
- Records carry an attestation, source reference, independent origin,
  verification method, subject hash, observation time, expiry, and metadata
  hash.
- Evidence is rechecked for expiry, revocation, consent withdrawal, current
  source trust, and attestation changes every time it is assessed.
- Conflicting subject hashes fail closed.
- Cash triangulation requires three distinct evidence types from three distinct
  origins.
- Identity, consent, and the correct legal-form authority remain mandatory.
- Account ownership and beneficial ownership are supporting context, not legal
  authority.
- Collateral cannot replace repayment capacity.
- Every successful registration and revocation appends a case audit event.
- Provider replay is idempotent only when the stored record is identical;
  conflicting reuse of a source reference is rejected.

## Provider acceptance gate

Do not activate a KYC source until the institution and Olin record:

- exact Mexico coverage: INE, CURP, RFC, passports/residency documents as needed;
- document authenticity, liveness, face match, failure and manual-review rules;
- hosted capture so raw images, biometric templates, and credentials do not
  pass through Olin;
- signed webhooks, replay protection, stable transaction references and status
  correction/revocation;
- DPA roles, purposes, notices/consent, subprocessors, processing locations,
  cross-border transfers, retention and deletion evidence;
- encryption, access control, incident notice, business continuity and audit
  evidence;
- sandbox and production credentials separated;
- SLA, support, pricing, minimum volumes, exit/export and deletion terms;
- partner security, privacy, legal/compliance and UAT approval.

The current private-sector data law is the
[LFPDPPP, latest compilation reviewed](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf).
Credit-information authorization remains a separate question under the
[LRSIC](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf). A licensed
Mexican lawyer and the regulated institution must approve the exact roles,
texts, evidence, and provider flow.

## Test coverage

The focused suite covers successful routing plus fake labels, unsupported
sources, wrong subject binding, subject conflicts, false source independence,
revocation, expiry, consent withdrawal, changed attestations, unknown IDs,
duplicate IDs, cross-tenant access, KYC failure, legal-form conflicts,
idempotent provider replay, and prohibition of synthetic KYC in real modes.

Run:

```bash
python3 -m unittest test_evidence_passport test_kyc_adapter -v
```

The next engineering task after partner selection is one signed-webhook adapter
for the chosen bank or KYC provider. It must call `ingest_kyc_verification` or
`register_verified_evidence`; it must never expose a public “mark verified” API.
