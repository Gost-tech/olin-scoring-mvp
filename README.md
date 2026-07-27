# Olin Credit Scoring

Olin is an explainable, rules-based credit-evaluation engine for Mexican
small businesses. It combines bureau, estimated repayment capacity, and
authorized operating evidence. It is a weighted scorecard with a V2
repayment layer—not a trained machine-learning model.

The current product is a 10-case shadow pilot: Olin produces a second,
explainable reading while the institution retains its official decision and
no money moves. Direct lending, public loan applications, repayment, and
collection are out of scope for this MVP. Legacy modules for those flows
remain in the repository but are blocked from shadow cases.

## Decision model

The engine combines three dimensions:

- Círculo de Crédito: C1 (670+), C2 (600–669), C3 (no file), C4
  (delinquent or below 600)
- DSCR: D1 (2.5+), D2 (1.5–2.49), D3 (below 1.5 or unavailable)
- Internal score: S1 (75+), S2 (50–74.99), S3 (below 50)

The 36 combinations resolve to Tier 1 route of approval, Tiers 2–12 review,
or Tier 13 do-not-recommend. Tier 14 is a pre-score safety block. These are
Olin recommendations, not the partner's final credit decision.

## Safety modes

`OLIN_MODE=demo` allows deterministic bank and FMCG mocks and writes to
`olin_scoring.db`. `OLIN_MODE=production` rejects mocked, unverified, or
unreferenced bank and FMCG evidence and defaults to the separate
`olin_production.db`.

Production case routes require a named API key. Merchant self-origination is
disabled, public case data is blocked, and `case_mode=shadow` can never reach
the disbursement connector.

## Run the demo webpage

```bash
cp .env.example .env
python3 -m olin.server --seed-demo
```

The partner workspace opens at `http://127.0.0.1:8080`. Use
`http://127.0.0.1:8080/nuevo` to create a shadow case. Demo seeding is
explicit; starting the server normally does not create applications.

Run the public partner website separately with:

```bash
python3 -m http.server 8001 --bind 127.0.0.1 --directory website
```

Then open `http://127.0.0.1:8001`. It is a dependency-free static site built
for mobile performance and can be deployed independently from the protected
analyst application.

The old WhatsApp-style onboarding simulator is retained only as a legacy
prototype and is not part of the shadow MVP:

```bash
python3 onboard.py
```

## Run the checks

```bash
python3 test_pilot_safety.py
python3 -m unittest -v test_shadow_mvp
python3 -m olin.test_v2
python3 test_full_flow.py
python3 test_belvo_pipeline.py
```

The safety suite covers all 36 tier combinations, exact bureau/DSCR/score
boundaries, production mock rejection, decline non-override, CLABE checksum,
payment idempotency and partial payments, overpayment rejection, overdue
detection, and separation of demo and production payment rails.

## Production prerequisites

Before changing `OLIN_MODE` to `production` for the shadow pilot:

1. Set `OLIN_API_KEYS` to a JSON object of named users and strong tokens.
2. Keep every submitted case in `case_mode=shadow`.
3. Connect verified bank and distributor/receipt evidence with retrievable references.
4. Use a clean production database and make an encrypted backup routine.
5. Complete the [shadow pilot runbook](docs/SHADOW_PILOT_RUNBOOK.md).

## Main components

- `olin/shadow_intake.html`: authenticated partner case intake
- `olin/scorecard.py`: scoring, repayment gates, tier matrix, and decision
- `olin/store.py`: case record, immutable workflow events, and cohort outcome
- `olin/server.py`: partner workspace and authenticated API
- `olin/stp.py`, `olin/collection.py`, `jobs/daily.py`: legacy lending modules,
  not used by the shadow MVP

Olin is still a controlled pilot system, not an unattended production lending
platform. The public site and Monex materials describe only the parallel-pilot
track. Credit policy, consumer notices, privacy, security, and operating
procedures require qualified local review before any live lending.

## Founder and partner materials

- [`START_HERE_OLIN.md`](START_HERE_OLIN.md): the immediate one-week and
  30/60/90-day execution plan.
- [`docs/OLIN_BRAND_AND_MESSAGE.md`](docs/OLIN_BRAND_AND_MESSAGE.md): approved
  positioning, visual system, wording, and claims to avoid.
- [`output/pdf/Olin_Founder_Field_Guide.pdf`](output/pdf/Olin_Founder_Field_Guide.pdf):
  plain-language credit, product, pitch, and investor training guide.
- [`output/pptx/Olin_Partner_Pilot_Deck_ES.pptx`](output/pptx/Olin_Partner_Pilot_Deck_ES.pptx):
  editable partner meeting deck in Spanish.
- [`output/pdf/Olin_Partner_Pilot_Deck_ES.pdf`](output/pdf/Olin_Partner_Pilot_Deck_ES.pdf):
  shareable partner meeting deck in Spanish.
- `output/pdf/Olin_Founder_Field_Guide.pdf`: printable founder guide when the
  generated artifact is present.
