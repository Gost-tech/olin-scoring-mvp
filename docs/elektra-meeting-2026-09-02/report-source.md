# How Olin can help Elektra and Banco Azteca extend productive credit

**Audience:** Elektra / Banco Azteca product, credit-risk, operations and technology leaders  
**Date:** 2 September 2026  
**Purpose:** Meeting answer and controlled-pilot design  
**Operating assumption:** Banco Azteca remains lender, policy owner and official decision maker; Olin is an evidence and affordability decision-support layer.

## Direct answer

Olin can help Elektra give more responsible loans by converting cases rejected or delayed for **missing conventional documentation** into an auditable “second look.” It does this by assembling permitted evidence of business activity, continuity and repayment capacity from several independent routes, then telling Banco Azteca one of four things:

1. **Evidence-supported review:** enough verified evidence exists for the bank to evaluate the case.
2. **Next-best evidence:** one or more specific alternatives could complete the case.
3. **Safer structure:** the requested amount is not supported, but a lower amount or different bank-defined term may be supportable.
4. **Not yet supportable:** reliable repayment capacity is not demonstrated; the customer enters an evidence-building path rather than receiving an unsafe recommendation.

The meeting line is:

> **“Olin convierte un ‘no por falta de papeles’ en una ruta verificable: qué evidencia alternativa ya existe, qué falta, cuánto pago puede soportar el negocio y por qué. Banco Azteca conserva la decisión.”**

Olin should not claim that every layer is used for every customer or that more data automatically means more approvals. The layers have different evidentiary strength and must be selected by business type, permitted purpose and bank policy.

## Why this problem is credible for Elektra

Banco Azteca already has a substantial credit platform. Its June 2026 risk disclosure describes an internal multivariate consumer-credit model using origination characteristics, payment behavior, sociodemographic data and credit-information-society data, together with backtesting and an independent risk function. Olin therefore should not be positioned as a replacement credit score.

The opportunity is the intersection of Elektra's productive-equipment catalogue and incomplete-document microbusinesses:

- Elektra's **Mi Negocio** catalogue includes tools and equipment for gastronomy, beauty, medical services, carpentry, point of sale, workshops and other productive activities.
- Banco Azteca's public **Mi Negocio Azteca** terms target individuals with a productive activity or business and ask for a fixed location, more than one year of operation, ownership, relevant inventory/tools, identity, address and a business visit.
- Mexico's 2024 Economic Census results reported by the national financial-inclusion portal indicate that only 10% of micro units obtained financing in 2023, while equipment/expansion represented 33% of financed uses.
- Banco Azteca states that it serves segments traditionally underserved by conventional banks, but its June 2026 disclosure also shows the importance of prudence: consumer credit represented 70% of gross loans and the reported delinquency index was 5.3%, up from 4.1% a year earlier.

These facts create a plausible business case for better evidence coverage without weakening risk controls. They do not prove that Olin will improve approvals or losses; that requires Banco Azteca data.

## Product: Pasaporte Productivo Olin

The product is not “28 signals and an AI score.” It is a **progressive evidence and capacity workflow** embedded behind Elektra/Banco Azteca channels.

```text
Customer requests productive equipment or business credit
                         |
                         v
Banco Azteca identity, consent, bureau and existing relationship
                         |
                         v
Olin selects the relevant evidence route for that business
                         |
          +--------------+--------------+
          |              |              |
       bank flow        TPV           supplier / fiscal /
       and debt       settlements     receivables / cash triangulation
          +--------------+--------------+
                         |
                         v
Business existence + continuity + provenance checks
                         |
                         v
Stressed repayment-capacity calculation
                         |
                         v
Evidence-supported review / missing alternative / safer amount / not yet
                         |
                         v
Banco Azteca official policy and human/automated decision
                         |
                         v
Decision, override and repayment outcome returned for validation
```

## How the six existing Olin layers should be used

### Layer 1 — Financial and transactional

**Role:** Primary capacity evidence.

Use Banco Azteca account flows, permitted transaction summaries, verified bank feeds, POS settlement history, supplier purchase volume/cadence and business inflows/outflows. This layer estimates operating cash generation and existing debt burden.

**Meeting value:** Banco Azteca can use data it already holds across accounts, payments and credit relationships, while Olin normalizes it into a case-level evidence contract.

**Boundary:** A CSV uploaded by the applicant is not automatically verified. Purchase volume proves activity but not sales or margin.

### Layer 2 — Geospatial intelligence

**Role:** Supporting existence and local-context evidence.

Use INEGI DENUE matching, sector consistency, transparent radius-based business density and repeated observations. It can help replace manual searching and prioritize visits.

**Meeting value:** It supports the fixed-location and business-existence questions already visible in the Mi Negocio Azteca journey.

**Boundary:** Location density, Google ratings or neighboring businesses do not prove income or repayment capacity. No historical Google footfall is assumed.

### Layer 3 — Business permanence and survival

**Role:** Core eligibility/continuity evidence when the policy asks whether a business is established.

Use dated supplier records, bank activity, leases/utilities, settlement history and controlled site-visit attestations. Repeated sources are stronger than a single current web listing.

**Meeting value:** Digitizes the evidence behind “fixed location,” “more than one year,” “inventory/tools” and the business visit, without pretending a map listing proves ownership.

### Layer 4 — Behavioral and psychometric

**Role:** Experimental research only in the first Elektra pilot.

Olin contains questionnaire, response-time and onboarding-consistency concepts. They should **not influence credit eligibility, pricing or amount** in the first pilot. Response timing can reflect connectivity, disability, work schedule or channel access rather than willingness to repay.

**Meeting value:** Demonstrates Olin's governance discipline: we will remove weak or proxy-prone signals until Banco Azteca data and independent review establish relevance and fairness.

### Layer 5 — Payment rails

**Role:** Primary or corroborating transaction evidence.

Use Banco Azteca/PSP-authorized SPEI, CoDi/DiMo, TPV, marketplace or other settlement summaries to measure transaction regularity, reversals, seasonality and concentration.

**Meeting value:** Helps thin-file businesses that transact digitally but lack formal statements.

**Boundary:** Public aggregate payment statistics are not merchant-level evidence. Olin needs a bank/PSP contract or bank-derived features.

### Layer 6 — External and macro context

**Role:** Stress testing and contextual explanation—not borrower punishment.

Use sector-specific inflation, seasonality, weather exposure and verified local economic series to stress expected cash flow.

**Meeting value:** Helps structure amounts and terms around the business cycle—for example, testing whether the payment remains supportable during a seasonal decline.

**Boundary:** Weather or neighborhood variables must never become universal negative borrower signals. They are applied only where the bank establishes a causal, lawful and validated connection.

## The essential control layers around the six signals

The six signal layers do not make a bankable product by themselves. Elektra needs these surrounding layers:

1. **Identity, authority and consent:** reuse Banco Azteca's approved KYC/KYB result and credit-bureau authorization. Olin should receive attested references, not raw credentials or unnecessary biometrics.
2. **Evidence Passport:** every observation carries source, subject binding, verification method, consent reference, observation time, expiry, provenance and revocation status.
3. **Capacity engine:** converts verified business flows into normalized and stressed cash flow, debt-service coverage and a supportable amount under bank-defined terms.
4. **Policy adapter:** Banco Azteca owns exclusions, minimum evidence, amount limits, manual-review rules and stop conditions.
5. **Human decision and reason codes:** Olin explains; Banco Azteca approves, declines or requests more information.
6. **Outcome loop:** Banco Azteca returns official decision, override, 30/60/90+ DPD, restructuring, charge-off and observation window so each route can be validated.

## Alternative evidence routes

The customer does not need every document. The bank selects one appropriate capacity route plus mandatory identity/authority/consent and supporting existence evidence.

### Bank-flow route

For customers with Banco Azteca or authorized account activity. Use operating inflows/outflows, deposit regularity, account coverage, debt service and stress capacity.

### TPV/platform route

For merchants with card, marketplace or platform settlements. Use net settlements, reversals, concentration, continuity and seasonality.

### Fiscal route

For businesses with authorized CFDI/fiscal evidence. Reconcile invoices with collection evidence because invoicing alone does not prove cash receipt.

### Supplier route

For shops, pharmacies, restaurants, wholesalers and inventory-led businesses. Use verified supplier cadence, volume and continuity; combine with sales or cash evidence because purchases do not prove margin.

### Receivables route

For services, construction, transport, wholesale and B2B firms. Use buyer-confirmed invoices, aging and historical collection behavior.

### Cash-business route

For truly cash-intensive businesses. Require at least three independent origins, such as controlled cash-sales observations, supplier confirmations, site visit and inventory count. Keep the route manual, conservative and bank-defined.

### Evidence-building route

When there is no reliable capacity evidence, do not manufacture a positive score. Offer a transparent path: separate business and personal flows using Banco Azteca Débito Negocio, record settlements or supplier invoices for a bank-defined period, then reassess. Any starter credit product or limit remains a Banco Azteca policy decision and requires controlled outcome testing.

## Three concrete examples for the meeting

### Example A — Abarrotes requesting a refrigerator

- Known Banco Azteca customer with acceptable payment history.
- No formal income statement.
- Verified supplier purchases show stable weekly restocking.
- TPV/bank deposits show sales regularity.
- DENUE/site evidence confirms the fixed business and continuity.
- Capacity stress supports MXN 18,000 rather than the requested MXN 25,000.

**Olin output:** evidence-supported manual review, smaller supportable amount, reasons and provenance. **Banco Azteca decides.**

### Example B — Beauty professional operating mainly in cash

- Identity and ownership are verified by Banco Azteca.
- Fixed location and tools are confirmed through a controlled visit.
- Lease/utility history and supplier invoices support continuity.
- Three-source cash triangulation is complete, but capacity remains approximate.

**Olin output:** committee-only route with conservative policy limits and explicit uncertainty—not automatic approval.

### Example C — Applicant with no documents and no observable business activity

- Identity alone is available.
- No verified flow, supplier, settlement, receivable or continuity evidence exists.

**Olin output:** not yet supportable plus a precise evidence-building plan. Olin cannot responsibly recommend a loan solely because the inclusion goal is important.

## Pilot that answers whether this helps Elektra

### Phase 1 — Historical replay

Banco Azteca supplies the complete eligible population for a bank-selected period, not hand-picked cases. Include applications, evidence available at the original decision time, bank decision/override and mature repayment outcomes. Keep later outcomes isolated until Olin outputs are frozen.

Compare:

- Existing-process evidence coverage versus existing process plus Olin routes.
- Cases where Olin finds a valid alternative route among missing-document/manual-review cases.
- Analyst handling time and manual touches.
- Agreement and override reasons—not “accuracy” by itself.
- 30/60/90+ DPD and loss outcomes only when labels mature and the cohort is statistically adequate.
- Missingness, stability and bank-approved proxy/fairness analysis by channel and segment.

Rejected applications without repayment outcomes cannot prove that Olin would have made good loans. They support only workflow/evidence analysis until a controlled prospective design exists.

### Phase 2 — Shadow operation

Run beside the current process. Olin cannot affect customer offers. Measure valid-processing rate, evidence completion, analyst time, route distribution, exceptions, overrides and audit completeness.

### Phase 3 — Bank-controlled policy test

Only after credit and model-risk approval, Banco Azteca may test a narrowly defined policy change with exposure limits, human review, monitoring and stop conditions. The bank owns customer communication, pricing, contracting, funding, servicing and collections.

## Success metrics

### Primary

**Incremental reviewable coverage:** percentage of the agreed missing-document cohort for which Olin identifies a bank-accepted, verified evidence route and a reproducible capacity assessment.

### Operational

- Median analyst minutes per case.
- Percentage of cases requiring repeated customer contact.
- Evidence completeness and provenance rate.
- Valid-processing and exception rate.
- Override rate and standardized override reasons.

### Risk guardrails

- No Olin-originated official decision or money movement.
- No capacity recommendation without bank-approved evidence coverage.
- Delinquency/loss by route, amount band and business segment after maturity.
- Stability, proxy/fairness and data-quality monitoring.
- Immediate stop on consent/authority failure, cross-customer exposure or material security incident.

## Data requested from Elektra

Start with bank-derived features rather than raw personal data wherever possible:

- Pseudonymous customer/application and product identifiers.
- Requested amount, term, product/SKU/category and productive purpose.
- Existing relationship length and summarized payment behavior.
- Bank-defined bureau band or approved derived features.
- Business type, channel, location band and visit outcome.
- Derived bank-flow, TPV, supplier, fiscal or receivables features available at decision time.
- Missing-document reasons, manual touches and timestamps.
- Official decision, limit, override and reason codes.
- Repayment schedule, payment performance, 30/60/90+ DPD, restructuring, charge-off and observation window.

Elektra must confirm which fields may leave its boundary. Olin can be deployed inside the bank-approved environment if raw data cannot leave.

## Meeting ask

Ask Elektra to approve a **problem-discovery and historical-validation workstream**, not to replace its score.

> “Seleccionemos un solo flujo —por ejemplo, clientes con actividad productiva que solicitan equipo de Mi Negocio y quedan pendientes por evidencia insuficiente. Ustedes nos dan el diccionario y resultados históricos permitidos. Olin reconstruye qué rutas alternativas estaban disponibles, calcula capacidad bajo su política y mide cobertura y tiempo. No cambia ninguna decisión hasta que Riesgos valide el resultado.”

Request five named owners:

1. Product owner for the selected journey.
2. Credit-policy owner.
3. Model-risk/UAIR validator.
4. Data and integration owner.
5. Privacy/security/operations owner group.

## Questions that reveal product fit

1. At which exact step are productive-credit cases abandoned, rejected or sent to manual review?
2. Which “missing document” reason codes have the greatest volume?
3. Which existing Banco Azteca/Elektra datasets are available but not joined at decision time?
4. Does the target customer already use Credimax, Mi Negocio Azteca, Débito Negocio or another product?
5. Which decisions use a physical business visit, and what evidence does the visit capture?
6. What is the baseline handling time, approval/pending/decline mix and mature delinquency outcome?
7. Can Olin operate as an internal feature/evidence service behind the existing decision engine?
8. What evidence routes would Credit Risk accept for a historical replay?

## Preliminary legal and governance issue list

This is legal-operations analysis, not a definitive Mexican-law opinion.

| Severity | Finding | Proposed action | Decision owner |
|---|---|---|---|
| BLOCK | A data feed or sandbox key does not establish authority to process real customer data. | Execute an approved data exhibit covering purpose, fields, roles, security, retention and deletion before transfer. | Elektra privacy/legal + data owner |
| BLOCK | Credit-bureau information requires the appropriate user relationship and express customer authorization under the applicable process. | Banco Azteca remains the bureau user unless counsel and the bureau approve another arrangement; pass derived results where possible. | Banco Azteca legal/compliance |
| BLOCK | Financial/patrimonial data generally requires express consent under the current private-sector data law, subject to applicable exceptions and exact roles. | Confirm controller/processor roles, privacy notice, purpose, evidence, revocation and ARCO workflow with licensed counsel. | Privacy/legal |
| COUNSEL | It is not yet established whether every proposed alternative signal is lawful and proportionate for credit use. | Approve a purpose/source/retention matrix; exclude behavioral/device/proxy-prone data until reviewed. | Legal + Credit Risk + Model Risk |
| NEGOTIATE | Olin needs official decisions, overrides and outcomes for validation, but secondary model training cannot be assumed. | Contract the outcome dataset, permitted analyses, ownership, retention and prohibition/conditions on training. | Procurement + Legal + Model Risk |
| CLARIFY | Identity, ownership and signing authority are different facts. | Reuse bank attestations and define evidence required for individuals versus legal entities. | KYC/KYB + Legal |

## Safe wording for the meeting

- “Olin provides evidence and affordability decision support.”
- “Banco Azteca remains the lender and official decision owner.”
- “The objective is incremental reviewable coverage, not automatic approval.”
- “Every signal must have source, purpose, provenance and validation.”
- “We will first replay historical cases and then operate in shadow.”

## Wording not to use

- “Olin lets you approve everyone.”
- “The 28 signals predict default.”
- “Our AI is already validated for Banco Azteca.”
- “A Google/WhatsApp/psychometric signal proves willingness to pay.”
- “A checkbox gives us all required data rights.”
- “Collateral replaces repayment capacity.”
- “We are production ready.”

## Sources

- [Banco Azteca — 2Q 2026 management report](https://www.grupoelektra.com.mx/api/pdfEkt/4259)
- [Banco Azteca — 2Q 2026 risk-management methodologies](https://www.grupoelektra.com.mx/api/pdfEkt/4264)
- [Banco Azteca — Mi Negocio Azteca terms](https://www.bancoazteca.com.mx/content/dam/azteca/docs/producto/prestamos/prestamos-personales/240905/tyc-mi-negocio-azteca.pdf)
- [Elektra — Mi Negocio catalogue](https://www.elektra.mx/mi-negocio)
- [Banco Azteca — Préstamo Personal](https://www.bancoazteca.com.mx/productos/prestamos/prestamos-personales.html)
- [CNBV — Política Nacional de Inclusión Financiera 2025–2030](https://www.cnbv.gob.mx/Inclusi%C3%B3n/Documents/PNIF_2025_2030.pdf)
- [CNBV inclusion portal — Economic Census 2024 highlights](https://pnif.cnbv.gob.mx/dnoticia/CE2024)
- [CNBV — Annex 15, internal rating models](https://www.cnbv.gob.mx/Anexos/Anexo%2015%20CUB.pdf)
- [Cámara de Diputados — LFPDPPP, latest reform 14 November 2025](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf)
- [Cámara de Diputados — LRSIC, latest reform 24 January 2024](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf)
- [IFC — MSME Banking in the Digital Era](https://www.ifc.org/content/dam/ifc/doc/2025/msme-banking-in-the-digital-era.pdf)
- [CGAP — Leveraging Transactional Data for Micro and Small Enterprise Lending](https://www.cgap.org/research/publication/leveraging-transactional-data-for-micro-and-small-enterprise-lending)
- [World Bank — Alternative Data Transforming SME Finance](https://documents1.worldbank.org/curated/en/701331497329509915/pdf/116186-WP-AlternativeFinanceReportlowres-PUBLIC.pdf)

## Limitations

Public information does not reveal Elektra's actual application funnel, reason-code volumes, feature store, internal policy, data contracts or intended meeting ask. The proposed product is therefore a testable solution hypothesis. Olin's current six-layer indicators are transparent heuristics, not default probabilities. Legal positions require licensed Mexican counsel and Banco Azteca approval; model and policy changes require its accountable risk functions.
