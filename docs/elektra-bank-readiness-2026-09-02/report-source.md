# Olin × Elektra: evidence intelligence research brief

Research cutoff: 2 September 2026. This is a product and technical research artifact, not a legal opinion or a claim that any signal predicts default.

## Executive conclusion

Banco Azteca does not need another opaque credit score. It already describes an internal consumer-credit risk process using origination, payment behavior, sociodemographic and bureau variables, with backtesting and independent risk oversight. Olin is more credible as an evidence-orchestration layer: it converts incomplete SME files into a versioned evidence passport, a transparent capacity analysis, alternative evidence requests, and an auditable recommendation package for the bank's own policy and human decision.

The strongest near-term product is therefore:

1. ingest partner-supplied cases and consent references;
2. verify identity and evidence provenance;
3. normalize cash-flow, POS, supplier, fiscal or receivables evidence;
4. calculate repayment capacity under bank-approved stress assumptions;
5. add public business and neighborhood evidence as corroboration or context;
6. return the evidence package, missing-evidence routes and reason codes;
7. receive the bank decision and later repayment outcomes for validation.

No social, mobility, satellite, rating or weather observation should auto-approve, auto-decline, change a loan amount, or move money in the first pilot.

## Why this matters for Elektra

Grupo Elektra's 2Q26 materials describe Banco Azteca as serving underserved segments through 2,544 contact points. They also report a 5.3% delinquency ratio at June 2026, compared with 4.1% a year earlier, and identify consumer credit as 70% of the gross portfolio. That combination makes inclusion valuable but raises the bar for evidence quality, policy control and monitoring.

The current Mi Negocio Azteca terms already expect a productive activity, a fixed business, more than one year of operation, ownership, inventory or tools, identity/address evidence and a visit. Olin should first help the bank assemble and evaluate those facts when the applicant's documentary path is incomplete. It should not promise that exotic data replaces KYC, bureau authorization, credit policy or regulated controls.

## The four evidence classes

| Class | Examples | Permitted pilot use | Prohibited use |
|---|---|---|---|
| Candidate capacity evidence | Bank inflows/outflows, POS settlements, supplier purchases, receivables, fiscal evidence, payment-rail regularity | Bank-approved shadow capacity review after provider verification and provenance | Automatic lending decision or money movement |
| Corroborating evidence | Business tenure, DENUE match, Google Place match, operating-hours evidence, address continuity | Identity, activity and permanence corroboration; analyst review | Sole reason to decline or increase exposure |
| Context or stress only | Local establishment density, cohort aggregates, licensed footfall, weather, inflation, night lights, seasonality | Portfolio context and bank-approved stress scenarios | Borrower-level character inference or direct score contribution |
| Research only | Social engagement, review sentiment, WhatsApp response time, psychometrics, device behavior | Offline outcome/fairness studies with explicit purpose and controls | Production credit policy before legal, model-risk and adverse-impact approval |

## What each external source can really prove

### INEGI DENUE

DENUE's official API exposes establishment identity, location, activity and size-band fields for millions of establishments. It is suitable for public-registry matching, radial market context and versioned aggregate snapshots. It does not prove cash flow, ownership, current operation at the exact moment of decision, or repayment capacity.

### Google Places

Places can support a fresh business-presence check, Place ID, address, category, rating and a small relevance-ranked review sample. Google states that a maximum of five reviews can be returned and restricts caching or storing Places content except for allowed exceptions such as Place IDs. Olin should retain a provider reference and derived, policy-approved facts—not a permanent mirror of reviews or photos—and must implement required attribution when displaying provider content.

Google Places is not a supported source of historical Popular Times. Any footfall feature needs a separate licensed dataset and must be validated for Mexico coverage, consent/lawful basis, sampling bias, minimum cohort size, retention and purpose before use.

### Licensed mobility / footfall

Foursquare documents a country-relative popularity attribute based on a six-month span of visits and lists Mexico among available Places-data countries. Its Movement SDK requires access and processes location-derived visit events. This establishes vendor feasibility, not suitability for credit. Procurement must confirm that the exact licensed product covers Mexican microbusinesses and contractually permits the proposed analytics. Olin should only store aggregated, thresholded metrics and never raw device histories.

### Satellite and night-time lights

VIIRS night-light products operate at roughly 500-metre scale. They can describe area-level change but are too coarse to verify the performance of one storefront. Sentinel imagery may support area or land-use research, but clouds, refresh timing, resolution and attribution make it unsuitable as first-pilot borrower evidence. Satellite features belong in an offline contextual experiment with spatial aggregation and backtesting.

### Weather and temperature

Open-Meteo's historical API uses reanalysis and model data at approximately 9–25 km resolution depending on dataset. It can support sector-specific stress scenarios—for example agriculture, transport or hospitality—but is not a measurement of one merchant's execution or willingness to repay. Missing weather evidence must remain neutral.

### Social presence

Public-profile scraping is not a bank-grade integration strategy. Business social data should enter only through official APIs and, where required, merchant authorization. A name match alone is ambiguous; account ownership, platform terms, purpose limitation, retention and bias must be resolved. For the first pilot, Olin may show “provider not configured / research only,” but it should not score follower count, posting frequency, sentiment or response time.

## Business comparison design

Olin can compare a merchant to a defensible local peer cohort without ranking the applicant:

- match the business to a public or partner identifier;
- select peers by SCIAN/category, geographic radius and, when available, size band;
- enforce a minimum cohort and suppress small cells;
- return aggregate density, cohort size, distance distribution, size-band coverage and later cohort change;
- disclose radial—not walking-time or drive-time—catchments;
- keep the output as market context only;
- never convert missing public attributes into negative evidence.

The code now exposes this as a privacy-minimized public peer benchmark and labels it `market_context_only`.

## Pilot implementation recommendation

### Phase A — historical replay

Use a bank-selected, de-identified historical cohort with a signed data dictionary and outcomes. Run Olin without affecting decisions. Confirm schema mapping, evidence provenance, missing-data behavior, reproducibility and audit export.

### Phase B — 10-case shadow workflow

Run 10 consented current cases in parallel with Banco Azteca's normal process. Olin does not communicate a lending decision to applicants and does not move money. Measure analyst minutes, missing-document routes, evidence completeness, bank/Olin recommendation agreement, overrides, reason quality and operational exceptions.

### Phase C — larger validation cohort

Only after mature repayment outcomes, test whether any candidate feature improves discrimination or calibration over the bank baseline. Validate stability, representativeness, fairness and policy impact. Keep contextual and research-only variables outside production policy unless Banco Azteca's credit risk, model risk, legal/privacy and security owners approve a documented use.

## Integration boundary

Banco Azteca owns applicant channels, KYC, bureau authorization/query, official credit policy, final decisions, disbursement, collections and complaints. Olin receives the minimum necessary case/evidence references, produces a versioned evidence and capacity package, and records the bank outcome for evaluation. Every provider call needs a timeout, retry policy, provenance reference, retention rule and degraded-mode path.

## Sources

- [Grupo Elektra, 2Q26 management report](https://www.grupoelektra.com.mx/api/pdfEkt/4259)
- [Grupo Elektra, 2Q26 risk methodologies](https://www.grupoelektra.com.mx/api/pdfEkt/4264)
- [Banco Azteca, Mi Negocio Azteca terms](https://www.bancoazteca.com.mx/content/dam/azteca/docs/producto/prestamos/prestamos-personales/240905/tyc-mi-negocio-azteca.pdf)
- [INEGI, DENUE API](https://www.inegi.org.mx/servicios/api_denue.html)
- [Google, Places API policies and attribution](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Google, Places resource reference](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)
- [Foursquare, Places Pro and Premium schemas](https://docs.foursquare.com/data-products/docs/places-pro-and-premium)
- [Foursquare, Places flat-file availability](https://docs.foursquare.com/data-products/docs/places-flat-file-overview)
- [Foursquare, Movement SDK overview](https://docs.foursquare.com/developer/docs/movement-sdk-overview)
- [NASA Earthdata, VIIRS Black Marble 500 m product overview](https://gis.earthdata.nasa.gov/portal/home/item.html?id=12b97384e1aa435eb2c0853df257b2fe)
- [Open-Meteo, Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

