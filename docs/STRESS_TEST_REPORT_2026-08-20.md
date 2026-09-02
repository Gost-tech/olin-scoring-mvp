# Olin bank API stress report — 2026-08-20

## Result

PASS after remediation. The local production-mode gate completed 789 pressured
requests at 32 concurrent clients with zero unexpected responses. It used
random credentials, a temporary SQLite database, provider-neutral synthetic
bank metrics, and `OLIN_LIVE_LENDING_ENABLED=0`.

This is a pilot-capacity engineering test, not proof of internet-scale capacity
or predictive model validation.

## What the test covers

- 500 concurrent readiness probes.
- 200 authenticated intake creations.
- Cross-partner record isolation.
- Concurrent replay of one signed bank webhook.
- Concurrent attempts to score the same intake.
- Persistence counts and the no-disbursement safety invariant.

## Baseline before remediation

| Scenario | RPS | P95 | Unexpected |
|---|---:|---:|---:|
| Readiness burst | 122.9 | 1,016.2 ms | 7 |
| Intake creation | 39.7 | 3,030.6 ms | 3 |
| Webhook replay | 15.0 | 2,034.0 ms | 1 |
| Duplicate scoring race | 14.8 | 2,034.2 ms | 2 |

The original process used a single-threaded HTTP server. When concurrency was
enabled, repeated readiness checks revealed a separate file-descriptor leak:
the SQLite context manager completed transactions but did not close readiness
connections. The process reached the macOS 256-file limit and reset requests.

## Remediation

- Replaced the single-request server with a bounded worker pool (16 workers by
  default, configurable with `OLIN_MAX_REQUEST_WORKERS`, capped at 64).
- Enabled SQLite WAL mode, a 10-second busy timeout, and one schema migration
  pass per database file/inode.
- Made readiness a read-only check and explicitly closed its SQLite connection.
- Added a reusable local stress command and CI-sized regression test.

## Verified result after remediation

| Scenario | Requests | RPS | P50 | P95 | P99 | Unexpected |
|---|---:|---:|---:|---:|---:|---:|
| Readiness burst | 500 | 539.1 | 56.6 ms | 73.2 ms | 82.9 ms | 0 |
| Intake creation | 200 | 275.4 | 56.3 ms | 294.0 ms | 686.0 ms | 0 |
| Cross-partner isolation | 25 | 350.7 | 32.3 ms | 52.8 ms | 57.6 ms | 0 |
| Webhook replay | 32 | 344.9 | 43.8 ms | 56.6 ms | 64.2 ms | 0 |
| Duplicate scoring race | 32 | 234.3 | 73.8 ms | 89.2 ms | 134.6 ms | 0 |

All 200 successful intake writes persisted. The replay storm produced one bank
event. The scoring race produced one scoring row (1 x 201, 31 x 422). No row
was disbursed. Maximum RSS increased by 7.0 MiB during the process-level run.

## Peak overload run

A second run pushed 2,653 measured requests through 64 concurrent clients,
four times the default 16-worker capacity. It passed with zero unexpected
responses: 2,000/2,000 readiness probes and 500/500 intake writes succeeded;
64 webhook replays remained one event; 64 scoring attempts remained one case;
and no money moved. Readiness P95 was 191.0 ms, intake-write P95 was 283.1 ms,
and maximum RSS increased by 11.8 MiB. The intake-write P99 reached 1,224.9 ms,
which is acceptable for a controlled pilot but should be monitored.

## Run it

```bash
python3 scripts/stress_test.py --reads 500 --writes 200 --concurrency 32
```

The command exits non-zero if an HTTP expectation or database invariant fails,
deletes its temporary database, and never contacts a real bank.

## Remaining scale boundary

SQLite plus an in-process worker pool is acceptable for a controlled bank pilot,
not a horizontally scaled lending platform. Before multi-instance production,
move transactional state and distributed idempotency to a managed PostgreSQL
service, put rate limiting at the gateway, and repeat this test in staging with
provider callbacks and production-like latency.
