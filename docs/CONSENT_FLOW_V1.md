# Olin Consent Flow v1

**Engineering status:** implemented and tested for synthetic UAT  
**Real-person status:** **BLOCKED** until the institution, Mexican counsel and
privacy owner approve the exact texts, identity sources, delivery provider,
retention schedule and withdrawal procedure.

This is a product and engineering control document, not a Mexican legal
opinion. Olin remains decision support; the institution makes the credit
decision.

## What the system now enforces

Olin treats these as three different acts. Acceptance of one never implies the
others:

1. `credit_assessment`: privacy notice linkage and processing for assembling
   and evaluating the file.
2. `provider_access`: authorization for one named data provider. A bank-link
   session cannot be created without an active authorization for that exact
   provider.
3. `credit_bureau`: a separate authorization for the named credit-information
   society. A payload that claims a bureau check cannot be scored without it.

The production path is:

`trusted identity + authority binding -> immutable policy -> OTP challenge -> verified receipt -> provider access -> shadow score`

Direct text pasted by a partner is rejected by default in `pilot` and
`production`. `OLIN_ALLOW_LEGACY_CONSENT=1` exists only for controlled migration
and must remain off for a new pilot.

## API sequence

1. Create the bank-owned intake with `POST /api/v1/intakes`.
2. Register identity and authority bindings through an internal approved KYC
   adapter. A person cannot self-assert either control.
3. Read a policy from `GET /api/v1/consent-policies`.
4. Issue one challenge at
   `POST /api/v1/intakes/{intakeId}/consent-challenges`.
5. Send the returned `/consentir#challenge=...&token=...` path to the applicant.
   The fragment is not sent in HTTP request logs. The page submits the token in
   a JSON body and never receives the institution API credential.
6. The applicant reads the exact text, actively checks the unselected box and
   enters the separately delivered six-digit code. The public token-bound
   endpoint creates the receipt.
7. Retrieve the integrity-checked receipt at
   `GET /api/v1/intakes/{intakeId}/consents/{consentId}/receipt`.
8. Withdraw with the existing withdrawal endpoint. Olin cancels dependent link
   sessions, blocks future dependent work and opens a critical operations task.

The raw OTP, applicant-link token and destination are not stored. Olin stores HMAC/digests, the
provider delivery reference, the exact policy snapshot, identity and authority
reference hashes, UTC acceptance time, receipt JSON and receipt SHA-256. Codes
expire, lock after five failures and cannot be reused.

## Do we need a KYC company?

Not to run synthetic UAT. For real people, Olin needs an approved source that
can establish identity and, separately, authority to act for the business. It
may be the pilot bank's existing KYC process instead of a new vendor. A KYC
vendor alone does not prove legal-representative authority, does not replace the
privacy notice and does not create credit-bureau authorization.

The production dispatcher is deliberately unconfigured. An approved SMS,
WhatsApp or e-signature adapter must return an opaque delivery/transaction
reference before real consent can be created.

## Legal issue map for counsel

| Status | Issue | System position | Required owner |
|---|---|---|---|
| BLOCK | Exact authorization wording | Synthetic text cannot run in real mode | Institution + Mexican counsel |
| BLOCK | Credit-bureau form and signing mechanics | Separate purpose/provider is enforced; wording is absent | Institution + SIC counsel/contact |
| BLOCK | OTP/e-signature evidentiary sufficiency | Technical receipt exists; provider is unconfigured | Mexican counsel + security |
| BLOCK | Real identity/authority source | Only trusted adapter records are accepted | Compliance/KYC owner |
| COUNSEL | NOM-151 use and retention period | Receipt is hash-verifiable; no claim of NOM-151 compliance | Mexican counsel + records owner |
| COUNSEL | Withdrawal effects and mandatory retention | Processing stops and a task opens; deletion is not promised | Privacy + legal |
| CLARIFY | Controller/processor roles and transfers | Must be written for each bank/provider relationship | Partner privacy owner |
| OK | Purpose separation and tenant isolation | Enforced and covered by automated tests | Engineering |
| OK | OTP expiry, lockout, replay and outage behavior | Enforced and covered by automated tests | Engineering/security |

## Questions that must be answered before the ten-case pilot

- Who is the data controller for each purpose: the bank, Olin, or both under a
  specific arrangement?
- Is the applicant an individual business owner or a legal entity, and what
  evidence proves the signer can bind that entity?
- Which exact provider and data categories are authorized, for what observation
  period, and are refreshes allowed?
- What exact authorization artifact does the selected credit-information
  society and institution require?
- Which OTP/e-signature vendor is approved, and what delivery evidence and
  identity assurance does counsel accept?
- Which records must be retained after withdrawal, for how long, and who closes
  the operations task?
- Does counsel require a NOM-151 accredited conservation service for these
  receipts or only for a narrower class of commercial messages?

## Current official references reviewed

- Cámara de Diputados, [Ley Federal de Protección de Datos Personales en
  Posesión de los Particulares](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf),
  text showing latest reform 14 November 2025.
- Cámara de Diputados, [Ley para Regular las Sociedades de Información
  Crediticia](https://www.diputados.gob.mx/LeyesBiblio/ref/lrsic.htm), text
  showing latest reform 24 January 2024.
- Diario Oficial de la Federación, [NOM-151-SCFI-2016](https://dof.gob.mx/normasOficiales.php?codp=6499&view=si),
  conservation of data messages and document digitization.

The implementation intentionally does not reproduce or invent a credit-bureau
authorization form. The approved institution/SIC wording must be loaded as an
immutable policy snapshot with legal, privacy and partner approval references.
