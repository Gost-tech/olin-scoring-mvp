# Olin real-data connector runbook

Status checked: 20 August 2026. This document separates code readiness from
commercial or regulatory access. A green API key is not the same as a complete
merchant-consent flow.

## What now exists in Olin

| Source | Olin endpoint | What it proves | Current readiness |
| --- | --- | --- | --- |
| Google Places (New) | `POST /api/v1/evidence/google-places/lookups` | Public business/location observation and live display metadata | Server key configured; live lookup implemented |
| INEGI DENUE | `POST /api/v1/evidence/denue/lookups` | Public registry, activity, size band, address and geo match | Connector implemented; `INEGI_DENUE_TOKEN` still required |
| Olin Geointelligence | `POST /api/v1/evidence/geointelligence/analyses` | DENUE density, transparent competitor/complement classification, radial catchment, GeoJSON and versioned aggregate snapshots | Implemented for every SME type; live use requires `INEGI_DENUE_TOKEN` and bank-approved SCIAN profiles |
| Bank CSV | `POST /api/v1/evidence/bank-statements/analyses` | Pre-analysis of authorized statement rows | Implemented; deliberately **not verified** and not eligible alone for a production decision |
| Syncfy | Existing backend connector in `olin/syncfy.py` | Provider-sourced account and transaction data | Sandbox API key works; merchant Widget V3 and callback flow are not enabled in Olin |
| Círculo de Crédito | Manual partner result in the case form | Credit-file/bureau evidence | No account, affiliation, sandbox application or production credentials yet |

Provider readiness is available to an authenticated partner at
`GET /api/v1/providers`. The versioned contract is in `docs/openapi-v1.json`.

## Correct merchant flow

1. A partner or authorized Olin analyst opens `/nuevo` and records purpose,
   identity data and the exact approved consent text.
2. Google Places searches the declared business. Olin displays live metadata
   but persists only the Place ID and observation time allowed by Google policy.
3. Using Google's coordinates, DENUE searches for a public establishment and
   compares name, address and physical distance. An ambiguous result stays for
   analyst review.
4. The merchant connects a bank through the Syncfy Widget. Bank credentials
   must be entered into Syncfy's consent interface, never into an Olin form.
5. Círculo is queried only by the contractually authorized user and only after
   express authorization. Until that integration exists, `checked=false` is
   valid and routes the case to human review; Olin must not invent a bureau
   score.
6. The selected evidence route is enforced:
   - inventory-led requires verified supplier evidence;
   - TPV-led requires verified settlement evidence;
   - bank-flow-led requires verified bank-provider evidence;
   - hybrid requires two verified sources.
7. Olin produces a recommendation and reasons. In the pilot, the partner makes
   and records the decision. Shadow cases can never disburse.

## Círculo de Crédito: exact next action

Círculo's API Hub says a developer can create a free account, register an
application and use sandbox APIs. Productive access is a separate step and asks
for an affiliation/otorgante number, legal name, commercial executive and
successful security-test evidence. Productive requests must be signed and
responses verified using the provider's public-key process.

Before using real credit data, confirm in writing whether the lending partner
will be the Círculo user and send the result to Olin, or whether Olin will become
the affiliated user. Do not treat a developer sandbox account as authority to
query real people.

- API Hub: https://developer.circulodecredito.com.mx/
- Integration guide: https://developer.circulodecredito.com.mx/guia_de_inicio
- Contact form: https://developer.circulodecredito.com.mx/contacto

Questions for Círculo:

1. For a B2B decisioning provider whose lender partner makes the final credit
   decision, which entity must be the `Usuario/Otorgante`?
2. Which product returns the score/bands and delinquency fields required by
   Olin's policy?
3. Can the partner pass the response or a normalized result to Olin under its
   contract and the merchant's express authorization?
4. What consent wording, proof, retention period and audit evidence are
   required for WhatsApp and in-person capture?
5. What are sandbox-to-production requirements, minimum volume, setup cost and
   per-query price?

## Syncfy: exact next action

The configured sandbox key can list test institutions and the backend can
derive cash-flow metrics from an existing Syncfy credential. This is not yet a
safe merchant flow. Syncfy states that its Widget handles institution
selection, credentials, consent, MFA and connection status. Olin needs current
Widget V3 access plus an approved callback/webhook configuration.

Ask Syncfy support to enable or confirm:

- Widget V3 package and current integration documentation;
- sandbox and production origins for the Olin merchant page;
- scoped session-token creation and expiry;
- refresh webhook signing and retry behavior;
- supported Mexican business-bank and POS-settlement institutions;
- data retention/deletion requirements and production pricing.

No Olin page should collect online-banking usernames or passwords.

## Google and DENUE limitations

Google can provide operating status, category, address, coordinates, website,
opening hours, rating and a limited relevance-ranked review sample. It does not
provide a reliable business opening date. Olin therefore does not infer tenure
from review age. Google Places content has storage restrictions; Olin persists
the Place ID rather than copying the live provider payload.

DENUE provides public registry fields for more than five million Mexican
establishments, including activity, size band, address and coordinates. It can
support existence and sector consistency. It does not prove sales, ownership,
profitability or repayment capacity and therefore does not directly approve a
loan.

- Google Place Details: https://developers.google.com/maps/documentation/places/web-service/place-details
- Google Places policies: https://developers.google.com/maps/documentation/places/web-service/policies
- INEGI DENUE API and token registration: https://www.inegi.org.mx/servicios/api_denue.html

## Multi-sector policy

Olin accepts multiple business types, but only the historically configured
`abarrotes` segment is eligible for the current automated route. Every other
sector is deliberately routed to human review until segment-specific repayment
outcomes justify calibration. DENUE's activity label helps detect a wrong giro;
it must not silently replace the merchant's declaration.
