# Olin product and marketing truth

Last reviewed: 27 July 2026

## One sentence

Olin helps Mexican lenders turn authorized but fragmented small-business
evidence into a reviewable credit recommendation and a labeled outcome.

## Buyer, subject and decision owner

- Buyer: bank, SOFOM, fintech, acquirer or merchant network with a credit team.
- Subject: a Mexican small business seeking a specific amount for a stated use.
- Decision owner: the regulated originator or lender, never Olin in the current
  product.
- Initial commercial motion: a controlled parallel pilot, not direct lending.

## Product boundary

Olin is B2B credit-decision software. It creates one case with four layers:

1. case: business, amount, purpose and partner reference;
2. evidence: authorized sources, verification state, date and reference;
3. recommendation: policy route, limits, reasons and missing information;
4. partner outcome: the institution's independent decision and later observed
   repayment result when available.

The application supports multiple business sectors through evidence routes:

- inventory-led: supplier or purchase history;
- TPV-led: card sales and settlement behavior;
- bank-flow-led: deposits, balances and outflows;
- hybrid: at least two verified operating sources.

This does not mean one universal policy is valid for every sector. In a pilot,
sector and evidence exceptions remain human-review cases until enough labeled
outcomes exist.

## What is real today

- deterministic scorecard with 14 technical routes covering the full
  Círculo × DSCR × internal-score matrix;
- canonical case API and analyst queue;
- partner, analyst and administrator roles using named static tokens;
- Círculo consent record;
- verified-source and retrievable-reference production gates;
- enforceable evidence-route requirements;
- synthetic cases for inventory, TPV and bank-flow routes;
- partner outcome recording;
- shadow-mode disbursement block;
- global live-lending feature flag off by default;
- SQLite audit trail;
- API, safety and flow tests.

## What is synthetic or incomplete

- bank, supplier and TPV data shown in the public demo;
- the scorecard thresholds and weights as predictive policy;
- the three merchant cases and their outcomes;
- integrations with Círculo, Syncfy, a POS acquirer, supplier networks, KYC,
  document storage and electronic signature;
- enterprise identity, MFA, Postgres, encryption-key management, retention,
  observability and disaster recovery;
- settlement-linked repayment;
- production collections, reconciliation and servicing;
- commercial pricing, approval lift, loss reduction and customer ROI.

## Validation ladder

1. Ten parallel cases validate workflow clarity, evidence coverage, time and
   partner usability. They do not validate repayment risk.
2. A historical backtest with hundreds of labeled cases can test policy
   separation, missing-data behavior and candidate thresholds.
3. A partner-funded live cohort with observed repayment validates economics
   and loss behavior. The partner keeps capital, underwriting authority,
   compliance and servicing unless contracts explicitly assign otherwise.

## Public language

Use:

- pequeños negocios
- institución financiera / otorgante
- evidencia autorizada y verificada
- capacidad estimada de pago
- recomendación crediticia
- expediente revisable
- ruta de política
- piloto en paralelo
- caso sintético
- resultado observado

Avoid:

- corner stores / tiendas de esquina / un abarrotes / microcomercios
- AI-powered / modelo entrenado
- sabemos quién pagará
- aprobación garantizada
- listo para producción
- alianza, cliente or integration when only a conversation or mock exists
- settlement-linked repayment until a signed integration is live
- Olin presta or Olin cobra in the current B2B positioning

## Approved headline

**De evidencia dispersa a una recomendación crediticia que su equipo puede
defender.**

Supporting line:

**Olin organiza datos autorizados, estima capacidad de pago y conserva las
razones, faltantes y resultados de cada expediente de pequeño negocio.**

## Investor truth

Olin is before product-market fit. The working MVP proves engineering ability,
not demand or credit performance. The next financing should buy:

- one paid design partner;
- access to historical or parallel cases;
- a local credit-risk owner;
- two high-value live data integrations;
- enterprise security and data governance;
- a backtest and a narrowly governed live cohort.

No traction slide may present synthetic cases, conversations, tests, website
visits or founder-funded experiments as customers, revenue, loans or repayment
performance.
