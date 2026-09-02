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

For bank engineering, security, risk, and UAT, start with
[`docs/bank-integration-pack/README.md`](docs/bank-integration-pack/README.md).
Its go-live gate is authoritative: local readiness does not mean approval for
real-data production.

The active milestone and product freeze are defined in
[`docs/bank-integration-pack/PILOT_EXECUTION_PLAN.md`](docs/bank-integration-pack/PILOT_EXECUTION_PLAN.md).
Before a controlled shadow run, complete the pilot manifest and validate it
with `python3 -m scripts.pilot_gate path/to/pilot_manifest.json`.

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
`olin_scoring.db`. `OLIN_MODE=pilot` and `OLIN_MODE=production` reject mocked,
unverified, or unreferenced evidence. Pilot cannot enable money movement;
production real-data mode fails closed unless it uses managed PostgreSQL with
the required storage, identity, authorization, retention and operational evidence.

Production case routes require a named API key. Merchant self-origination is
disabled, public case data is blocked, and `case_mode=shadow` can never reach
the disbursement connector.

The authenticated intake can analyze an authorized bank CSV without retaining
transaction rows, perform a live Google Places lookup, and query INEGI DENUE
when `INEGI_DENUE_TOKEN` is configured. Syncfy backend access is configured,
but interactive real-bank linking remains disabled until the approved hosted
connection flow and commercial access are available.

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
cd website
pnpm install
cp public/config.example.js public/config.js
pnpm dev
```

Then open `http://127.0.0.1:8001`. It is a statically generated Astro site
built for mobile performance and deployed independently from the protected
analyst application. Node.js 22+ and pnpm are required for development.

The old WhatsApp-style onboarding simulator is retained only as a legacy
prototype and is not part of the shadow MVP:

```bash
python3 onboard.py
```

## Run the checks

Run the complete technical release gate from the repository root:

```bash
make technical-go
```

This verifies the complete Python suite, compatibility flows, the 1,000-case
synthetic safety gate, the Astro build, static QA, and browser QA at desktop
and mobile viewports. To run a bank-controlled shadow pilot, validate the
completed and signed manifest separately:

```bash
make pilot-gate MANIFEST=path/to/pilot_manifest.json
```

The underlying commands are:

```bash
python3 -m unittest discover -v
python3 -m olin.test_v2
python3 test_full_flow.py
python3 test_belvo_pipeline.py
python3 -m olin.synthetic_portfolio --cases 1000 --seed 42
cd website && pnpm test
```

The safety suite covers all 36 tier combinations, exact bureau/DSCR/score
boundaries, production mock rejection, decline non-override, CLABE checksum,
payment idempotency and partial payments, overpayment rejection, overdue
detection, and separation of demo and production payment rails.

## Production prerequisites

Before changing `OLIN_MODE` to `production` for the shadow pilot, follow
[`docs/BANK_REAL_DATA_UAT_DEPLOYMENT.md`](docs/BANK_REAL_DATA_UAT_DEPLOYMENT.md) and:

1. Set `OLIN_USERS` to named partner, analyst and admin identities with unique strong bootstrap credentials; require short-lived sessions.
2. Keep every submitted case in `case_mode=shadow`.
3. Use managed PostgreSQL with TLS, encryption, monitoring, backups and a proven restore.
4. Record the bank's approved data scope/processing reference and verified evidence references.
5. Run `python3 -m scripts.production_preflight` and require `ok: true`.
6. Complete the [shadow pilot runbook](docs/SHADOW_PILOT_RUNBOOK.md).

## Main components

- `olin/shadow_intake.html`: authenticated partner case intake
- `olin/scorecard.py`: scoring, repayment gates, tier matrix, and decision
- `olin/store.py`: case record, immutable workflow events, and cohort outcome
- `olin/server.py`: partner workspace and authenticated API
- `olin/signal_architecture.py`: SME-wide 28-signal evidence catalogue and evaluators
- `olin/weather.py`: Open-Meteo sector-context adapter
- `olin/geointelligence.py`: SME-wide DENUE radius analysis, competitor and
  complement classification, radial catchments, and versioned geo snapshots
- `docs/SME_28_SIGNAL_IMPLEMENTATION.md`: source readiness, sector applicability, and validation gates
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
