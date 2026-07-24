# Marketing Context

*Last updated: 2026-07-20*

## Product Overview

**One-liner:** Olin helps banks, Sofomes, and fintechs estimate whether a small business can pay a specific loan amount and term, then shows the reasons behind the recommendation.

**What it does:** Olin is an explainable credit-decision prototype for Mexican small businesses. It combines Círculo de Crédito, estimated payment capacity, and operating evidence into a policy route that a lender or credit committee can reconstruct. The first proposed cohort is `tiendas de abarrotes`; other business types need separate rules and validation. The current product is suitable for demonstrations and an institution-led parallel pilot; it is not a lender, a loan application, or a production machine-learning model.

**Product category:** Explainable credit-decision infrastructure / underwriting decision support for small businesses.

**Product type:** B2B financial software prototype, intended to operate with a regulated lender or originator.

**Business model:** Unvalidated. Hypotheses to test are a per-decision fee, a monthly platform fee plus usage, or an origination/servicing revenue share through a qualified lending partner. Do not publish pricing until partner discovery clarifies who owns the borrower, data, credit risk, collections, and funding.

### Internal strategic boundary — unresolved

Two tracks currently exist and must not be merged in external messaging:

- **Track B — public and Monex-facing:** decisioning-as-a-service. Olin produces an explainable second reading for a 10-case parallel pilot; the institution keeps the official decision and no funds move.
- **Track A — private exploration:** Olin may use the engine for loans funded with its own raised capital, distributed through Demian's TPV network, with collection timed to settlement days. This is not live, funded, legally operational, or approved for public claims.

The shared asset is the decision engine. Whether Olin becomes primarily an internal lender or a decisioning vendor is an open founder decision. Do not change product architecture, commercial positioning, or advisor scope in a way that assumes either outcome. The Monex meeting remains strictly Track B.

### Current product truth

**Built and verifiable:** Three decision dimensions; fourteen tiers covering all 36 scorecard combinations; human approval required during the pilot; decline non-override; deterministic demo mocks; production fail-closed for synthetic bank and FMCG evidence; analyst workflow; consent evidence fields; disbursement claim pattern; payment ledger; outcome records; alert fallback; and safety tests.

**Not yet live or proven:** No completed real-loan cohort; no observed default or approval-lift evidence; no production ML model; no confirmed live FMCG feed; no permission to show partner logos; and no claim of legal or unattended-production readiness. Named-user authentication, dual control, encryption/retention, and authoritative settlement reconciliation remain live-lending prerequisites.

## Target Audience

**Primary target companies:** Mexican banks, Sofomes, fintech lenders, and other qualified originators with authorized cases and an existing underwriting operation.

**Secondary ecosystem partners:** POS/acquiring providers, distributors, and data providers that may supply consented operating evidence or distribution. They are not the primary buyer unless they also originate credit.

**Decision-makers:** Head of Credit, Chief Risk Officer, Head of SME/Microbusiness Lending, Product or Partnerships Director, Innovation Lead, and—later—an early-stage investor who understands credit infrastructure.

**Primary use case:** Evaluate 10 authorized small-business cases in parallel without changing the institution's official decision, then compare Olin's recommendation, reasons, data coverage, exceptions, and workflow effort.

**Jobs to be done:**

- Estimate whether the payment for a specific amount and term fits the business's available cash, without claiming certainty.
- Evaluate thin-file small businesses with more operating context while retaining credit control.
- Give a committee a recommendation it can inspect and challenge.
- Capture source, decision, analyst, repayment, and outcome data consistently enough to support later calibration.
- Test partner data and workflow fit before committing to a large integration.

**Use cases:**

- A lender runs historical or parallel `tiendas de abarrotes` files through Olin and compares them with its own policy.
- A POS provider or distributor explores whether consented transaction or purchase evidence improves underwriting coverage.
- A credit team reviews an illustrative dossier in the analyst demo before designing a controlled pilot.
- Later, separate cohorts for taquerías/fondas, papelerías/ferreterías, or local services test whether different signals and thresholds are needed.

## Personas

| Persona | Role | Cares about | Challenge | Value we promise |
|---|---|---|---|---|
| Credit analyst | User | Clear reasons, exceptions, evidence freshness | Thin or inconsistent files | One reconstructable dossier and tier |
| Partnerships lead | Champion | Low-friction pilot, partner value, speed to learning | Too many integrations before evidence | A bounded shadow pilot with defined outputs |
| Head of Credit / CRO | Decision Maker | Loss control, policy integrity, auditability | Black-box or unsupported alternative signals | Human-controlled, explainable recommendations |
| Business or finance sponsor | Financial Buyer | Strategic value, implementation effort, path to scale | Unproven ROI and data access | Milestone-based validation before scale spend |

## Problems & Pain Points

**Core problem:** A viable small business may have cash sales, recurring purchases, years at the same address, and little formal credit history. A conventional file can therefore contain too little evidence to answer the lender's core question: can this business handle this payment for this amount and term?

**Why alternatives fall short:**

- Bureau-only screening does not fully describe operating continuity or current repayment capacity.
- Informal manual review is difficult to compare, audit, or turn into a clean outcome dataset.
- A large integration before a workflow test creates cost without proving decision value.
- A black-box model is inappropriate before enough representative repayment outcomes exist.

**What it costs them:** Qualified applicants can be rejected or held for manual investigation; analysts spend time reconstructing evidence; and the lender learns slowly because decisions and outcomes are not captured consistently. No monetary impact is yet verified for Olin.

**Emotional tension:** Credit leaders want better coverage but fear hidden model risk, poor consent evidence, unreliable alternative data, and a pilot that creates operational or regulatory exposure.

## Competitive Landscape

| Competitor | Type | How they fall short for Olin's intended wedge |
|---|---|---|
| Existing lender scorecard and manual committee | Direct status quo | Often not designed to combine merchant operating evidence with a source-level audit trail |
| Embedded-credit platforms serving broader SME populations | Direct / adjacent | May not focus on abarrotes evidence, explainable shadow pilots, or a partner's existing committee workflow |
| Traditional bureau-only underwriting | Secondary | Useful and required evidence, but not a complete picture of merchant operations or affordability |
| Spreadsheet, WhatsApp, and analyst judgment | Indirect | Flexible but difficult to standardize, reproduce, govern, and calibrate |

This landscape is a positioning hypothesis, not a validated win/loss study. Named competitors require a separate, current market review before public comparison.

## Differentiation

**Key differentiators:**

- A transparent three-dimensional policy: Círculo, DSCR, and internal operating score.
- Fourteen explicit routes over 36 tested combinations instead of an unexplained probability.
- Source, verification state, analyst rationale, payment events, and final outcome designed as one learning record.
- A shadow-pilot starting point that leaves the partner's current decision untouched.
- One adaptable application with separate policies by business type. `Tiendas de abarrotes` come first; taquerías, papelerías, ferreterías, and services cannot inherit the same thresholds automatically.

**How we do it differently:** Olin starts with an explainable scorecard and conservative human control. It separates what is built, what is synthetic in the demo, what requires a partner, and what belongs to future research.

**Why that's better:** A credit team can inspect the mechanism, identify missing evidence, challenge the recommendation, and learn from a small pilot before it accepts model or balance-sheet risk.

**Why customers choose us:** This remains to be validated. The intended decision drivers are auditability, a bounded pilot, merchant-specific evidence, and a credible path from rules to calibrated policy.

## Objections

| Objection | Response |
|---|---|
| “Thirty loans cannot train an AI model.” | Correct. The first cohort is for operational learning and scorecard calibration, not a production ML claim. |
| “Your bank and FMCG data are mocked.” | Correct in the demo. Production rejects synthetic evidence; a partner is needed to test verified inputs. |
| “We already have a credit policy.” | Olin should first run in shadow mode and be compared with that policy, not replace it. |
| “Who makes the final decision?” | The originator does. During the pilot, every approval requires a recorded human rationale. |
| “Are you ready to disburse live loans?” | No unattended launch is being proposed. Live lending requires legal, security, dual-control, reconciliation, and data readiness. |

**Anti-persona (NOT a good fit):** A partner seeking instant automated approval, fabricated AI performance, unconsented data use, or a vendor willing to bypass its credit and compliance owners.

## Switching Dynamics

**Push (away from current):** Slow or inconsistent manual review, rejected thin-file merchants, fragmented evidence, and poor outcome records.

**Pull (toward us):** An inspectable decision path, one evidence dossier, controlled shadow testing, and a clean learning loop.

**Habit (keeping them stuck):** Existing policy, analyst intuition, spreadsheet workflows, and integration priorities already competing for resources.

**Anxiety (about switching):** Model risk, consent, data quality, implementation work, regulatory exposure, responsibility for collections, and whether any signal actually predicts repayment.

## Customer Language

There is not yet a formal customer-research corpus. The following are observed or proposed phrases and must not be presented as validated customer quotations.

**How they describe the problem (proposed language to validate):**

- “Tenemos comercios que operan bien, pero el expediente no alcanza para decidir.”
- “Necesito entender por qué el motor recomienda comité o rechazo.”
- “¿La cuota realmente cabe en el flujo de este negocio?”

**How they describe us (proposed language to validate):**

- “Una segunda lectura explicable para expedientes con poca historia.”
- “Un piloto que podemos comparar sin cambiar nuestra política.”
- “Una forma de estimar capacidad de pago sin convertirla en una promesa.”

**Verbatim partner language observed in conversation:** “Let's talk more about the credits and card terminals.” This confirms interest in the combined credit/POS topic, not a partnership or product validation.

**Public words to use:** pequeños negocios, pequeños comercios, tiendas de abarrotes, capacidad estimada de pago, monto y plazo, recomendación, razones, expediente, equipo de crédito, institución financiera, fuente, autorización, piloto en paralelo, prototipo funcional.

**Words to avoid:** `microcomercios`, `corner stores`, `tiendas de esquina`, `un abarrotes`, `reembolso` in customer-facing copy, AI-powered, revolutionary, instant cash, forgotten 95%, 89% accuracy, partnership, production-ready, guaranteed approval, trained model.

| Term | Meaning |
|---|---|
| Ruta | Public-language name for the policy route produced by the Círculo × DSCR × internal-score matrix; the code calls it a tier |
| DSCR | Cash available for debt service divided by required debt service |
| Piloto en paralelo | Olin makes a second recommendation without changing the institution's official decision |
| Evidencia verificada | Data with an identified source, observation date, and appropriate verification state |

## Brand Voice

**Tone:** Calm, professional, precise, evidence-based, and human.

**Style:** Short declarative Mexican Spanish, concrete nouns, restrained technical detail, and explicit labels for current versus future capabilities. Lead with the simple question—`¿Puede este negocio pagar este crédito?`—before explaining the mechanism.

**Personality:** Credible, transparent, disciplined, curious, and locally grounded.

**Voice DO's:** State maturity early; explain the mechanism; name the human decision owner; label examples as illustrative; separate built, tested, partner-required, and future.

**Voice DON'T's:** Inflate traction; imply legal certainty; use partner logos without permission; promise speed, approval, accuracy, loss reduction, or investor return without evidence.

## Style Guide

**Grammar:** Spanish-first public copy; active voice; one idea per sentence; define acronyms the first time; use `pago`, `cumplir con sus pagos`, or `capacidad de pago` instead of `reembolso`; use decimal comma only in Spanish prose and decimal point in code/data exports.

**Capitalization:** Brand is lowercase `olin` in the wordmark and `Olin` in prose. Use `Círculo de Crédito`, `DSCR`, `Tier 1`, and `COMITÉ` only when reflecting an interface status.

**Formatting:** Use short headings, visible status labels, tabular numerals for scores and ratios, and one primary CTA per section.

**Preferred terms:** `recomendación explicable`, `capacidad estimada de pago`, `monto y plazo concretos`, `piloto controlado`, `piloto en paralelo`, and `la institución conserva la decisión`.

## Proof Points

**Metrics:**

- 3 decision dimensions.
- 14 policy tiers.
- 36 scorecard combinations covered by tests.
- 13 pilot-safety tests passing as of 2026-07-14, plus a passing full-flow check.

**Customers:** None claimed. No logo may be shown as a customer or partner without written permission.

**Testimonials:** None collected. A meeting invitation or positive chat response is not a testimonial.

| Value Theme | Supporting Proof |
|---|---|
| Explainability | Tier matrix and reason codes in `olin/scorecard.py` |
| Human control | Analyst approval and rationale required during the pilot |
| Demo/production separation | Synthetic evidence is allowed in demo and rejected in production |
| Outcome learning | Payment ledger, final outcome states, and filtered training export |

## Content & SEO Context

**Target keywords:** Secondary priority until partner validation; the immediate site is a relationship and demo asset.

| Cluster | Primary Keyword | Secondary Keywords | Intent |
|---|---|---|---|
| Credit decisioning Mexico | evaluación crediticia para pequeños negocios | motor de decisión crediticia, capacidad de pago, crédito para tiendas de abarrotes | Commercial / educational |
| Explainability | scoring de crédito explicable | comité de crédito, trazabilidad crediticia | Educational / commercial |
| Pilot | piloto de crédito para pequeños negocios | piloto en paralelo, datos alternativos | Commercial |

**Internal links map:**

| Page | URL | Use for | Anchor text |
|---|---|---|---|
| Public site | `/website/index.html` | Product overview and pilot CTA | Explorar Olin |
| Analyst demo | Configured by `OLIN_DEMO_URL` | Product evidence | Ver un expediente de ejemplo |
| Founder guide | `/output/pdf/Olin_Founder_Field_Guide.pdf` | Founder education | Guía del fundador |

**Writing examples:** `docs/OLIN_BRAND_AND_MESSAGE.md` defines the approved promise, maturity line, voice, and banned claims.

## Goals

**Business goal:** Secure one well-defined parallel pilot with a qualified lender, starting with ten authorized cases, and produce a complete, usable evidence-and-decision dataset. The first scorecard calibration cohort remains focused on `tiendas de abarrotes`; larger TPV merchants and other business types require separate policies. Outcome data requires a later live cohort or historical backtest; the parallel pilot alone does not validate repayment risk.

**Conversion action:** Request a working session to design a 10-case shadow pilot; secondary action is to open the analyst demo.

**Current metrics:** No live-loan or customer-performance metrics. Current evidence is prototype functionality and passing safety/full-flow checks.
