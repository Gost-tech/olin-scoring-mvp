# Olin Credit Scoring

Olin is an explainable, rules-based credit-evaluation engine for Mexican
small businesses. It combines bureau, estimated repayment capacity, and
authorized operating evidence. It is a weighted scorecard with a V2
repayment layer—not a trained machine-learning model.

The current external proposal is a 10-case parallel pilot: Olin produces a
second, explainable reading while the institution retains its official
decision and no money moves. A separate direct-lending track is under
strategic review and must not be presented externally or treated as live.
The shared codebase is the decision engine; product packaging for those two
tracks remains deliberately unresolved.

## Decision model

The engine combines three dimensions:

- Círculo de Crédito: C1 (670+), C2 (600–669), C3 (no file), C4
  (delinquent or below 600)
- DSCR: D1 (2.5+), D2 (1.5–2.49), D3 (below 1.5 or unavailable)
- Internal score: S1 (75+), S2 (50–74.99), S3 (below 50)

The 36 combinations resolve to Tier 1 auto-approve, Tiers 2–12 committee,
or Tier 13 decline. Tier 14 is a pre-score safety block. During the pilot,
every approval still requires a recorded analyst decision and rationale.

## Safety modes

`OLIN_MODE=demo` allows deterministic bank and FMCG mocks and writes to
`olin_scoring.db`. `OLIN_MODE=production` rejects mocked or unverified bank
and FMCG evidence and defaults to the separate `olin_production.db`.

The payment connector enforces the same boundary: demo can only use the STP
sandbox, while production can only use real STP. Production startup also
requires analyst and webhook secrets and refuses a database containing demo
rows.

## Run the demo webpage

```bash
cp .env.example .env
python3 -m olin.server --seed-demo
```

The analyst interface opens at `http://127.0.0.1:8080`. Demo seeding is
explicit; starting the server normally does not create applications.

Run the public partner website separately with:

```bash
python3 -m http.server 8001 --bind 127.0.0.1 --directory website
```

Then open `http://127.0.0.1:8001`. It is a dependency-free static site built
for mobile performance and can be deployed independently from the protected
analyst application.

Run the WhatsApp-style onboarding simulator with:

```bash
python3 onboard.py
```

## Run the checks

```bash
python3 test_pilot_safety.py
python3 -m olin.test_v2
python3 test_full_flow.py
python3 test_belvo_pipeline.py
```

The safety suite covers all 36 tier combinations, exact bureau/DSCR/score
boundaries, production mock rejection, decline non-override, CLABE checksum,
payment idempotency and partial payments, overpayment rejection, overdue
detection, and separation of demo and production payment rails.

## Production prerequisites

Before changing `OLIN_MODE` to `production`:

1. Set strong `OLIN_ANALYST_TOKEN` and `OLIN_STP_WEBHOOK_SECRET` values.
2. Configure real STP credentials and set `STP_SANDBOX=0`.
3. Connect verified Syncfy and distributor/receipt evidence; mocks fail closed.
4. Use a clean production database and make an encrypted backup routine.
5. Complete the operational checklist in [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md).

## Main components

- `onboard.py`: application collection and mock/real connector selection
- `olin/scorecard.py`: scoring, repayment gates, tier matrix, and decision
- `olin/store.py`: audit log, analyst decision, disbursement, payment ledger,
  outcomes, and training export
- `olin/server.py`: analyst webpage and authenticated API
- `olin/stp.py`: CLABE validation and SPEI disbursement
- `olin/collection.py`: repayment matching, idempotency, overdue detection
- `jobs/daily.py`: overdue/default monitoring and portfolio snapshot

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
