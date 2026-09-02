# Olin SME-wide 28-signal implementation

## Product boundary

Olin evaluates every `BusinessType` supported by the API. Abarrotes is one
segment, not the platform boundary. Sector applicability changes which signals
are relevant; a missing or non-applicable signal never becomes a positive
observation.

The 28-signal report is evidence context alongside the legacy scorecard. Its
indicator values are designed heuristics, not probabilities of default. The
bank retains the official decision, policy, pricing, and amount.

## What is usable now

- `GET /api/v1/signals/catalog` returns the versioned catalogue, metric schema,
  source strategy, applicability, and limitations for exactly 28 signals.
- Every newly scored case returns `alternative_signal_report` with all 28
  evaluations, six layer summaries, observed coverage, verified coverage,
  provenance, confidence, and missing-source explanations.
- `signal_evidence` on the authenticated case payload accepts bounded scalar
  metrics for any catalogue signal. Unknown signals, nested payloads,
  non-finite numbers, and verified observations without a source, evidence
  reference, and ISO-8601 observation time are rejected.
- Existing bank, supplier, POS, tenure, Google Places, and payroll inputs
  automatically populate the matching signals.
- `POST /api/v1/evidence/weather/analyses` returns attachable Open-Meteo
  evidence using a 30-day prior-year comparison.
- `POST /api/v1/evidence/geointelligence/analyses` performs a live DENUE
  radius analysis for every SME type and returns density, competitors,
  complementary businesses, radial catchment bands, concentration, minimized
  nearby establishments, and attachable geo-signal evidence.
- Geointelligence snapshots are isolated by authenticated partner and location.
  Later observations derive additions, missing establishments, business-stock
  change, and closure-rate evidence without retaining provider contact fields.

## Source reality

| Source | Usable state | Signals | Production prerequisite |
|---|---|---|---|
| Syncfy / bank callback | Backend adapter and signed derived-metric callback exist | Bank snapshot and trend; SPEI after transaction classification | Commercial credentials, hosted consent widget, provider certification |
| Bank CSV | In-memory analysis exists | Bank snapshot and trend | Controlled document authentication; a CSV hash alone is not verification |
| Google Places | Live lookup exists | Maps activity and current operating metadata | API key, policy-compliant live display; no historical Popular Times assumption |
| INEGI DENUE | Live match and geointelligence radius analysis exist | Registry, density, competitors, complements, neighbor ecosystem, and snapshot-derived closure signals | Token plus repeated observations over a bank-approved comparison window |
| Open-Meteo | Adapter implemented | Weather context | Bank-approved sector sensitivity; never a universal borrower penalty |
| INEGI Indicator API | Official API identified | Sector-relevant input inflation | Select and version a SCIAN-relevant series per sector |
| Distributor records | Normalized evidence contract ready | Purchase volume, cadence, supplier diversity | FEMSA/Bimbo/Lala agreement or controlled invoice verification |
| POS/acquirer records | Normalized evidence contract ready | POS volume and settlement behavior | Acquirer/PSP/bank settlement contract |
| Footfall | No supported Google historical-footfall source assumed | Foot-traffic delta | Authorized mobility, sensor, PSP, or merchant operating source |
| NASA/NOAA VIIRS | Dataset source identified; no pipeline | Night-light trend | Tile ingestion, geospatial aggregation, baseline versioning, QA |
| WhatsApp onboarding | Metric contract ready | Business account, response, timing, consistency, questionnaires | Explicit consent, accessibility review, retention policy, adverse-impact review |
| CoDi/DiMo/OXXO/Spin | Metric contract ready | Payment-rail frequency and regularity | Bank/PSP/wallet agreement; public aggregate statistics are insufficient |
| IMSS/payroll | Metric contract ready | Payroll trajectory | Consented employer/payroll evidence; public IMSS data is aggregate only |

## The 28 signals

The implementation contains the 27 rows enumerated in the June 2026 PDF plus
`pos_transaction_volume`, which was present in the original six-signal model
but omitted from the later table. Its PDF weight is `null` because the document
did not define a weight for it. Olin does not silently rebalance the remaining
weights.

## SME sector behavior

- Inventory and supplier signals are core for retail, wholesale, food,
  hospitality, manufacturing, agriculture, and applicable healthcare models.
- Location/footfall signals are conditional for physical businesses and are
  not forced onto digital or project-based firms.
- Weather is limited to exposed sectors such as agriculture, transport,
  logistics, construction, food, hospitality, and physical retail.
- Bank flow, business continuity, payment behavior, onboarding integrity, and
  seasonality are available across sectors when the required evidence exists.
- Unknown business models route through `other` and remain reviewable without
  inventing sector assumptions.

## Geointelligence boundary

The implemented catchment is a transparent radius between 50 metres and 5 km,
which is the supported DENUE radius-query range. It is not drive time, walking
time, mobile-device footfall, or satellite activity. Those require separate
authorized providers. Competitor classification uses an explicit SCIAN prefix
when supplied and otherwise a versioned sector keyword profile; the response
shows which rule was applied.

## Validation rules before predictive use

1. Define the bank's outcome label and observation window.
2. Confirm every signal's permitted purpose, source, and retention rule.
3. Measure missingness by sector and channel.
4. Test stability, leakage, calibration, and out-of-time performance.
5. Review proxy discrimination and accessibility effects, especially for
   psychometric, WhatsApp, location, and device-derived evidence.
6. Version every transformation and preserve the exact evidence reference.
7. Promote a signal into decision policy only through bank model governance.
