# OLIN review output schema

Every important review should be concise, evidence-backed, and explicit about uncertainty. Use this structure in Markdown or an equivalent machine-readable representation.

## Review metadata

- **Review:** title and scope
- **Reviewer:** agent or person
- **Date:** review timestamp
- **Repository state:** branch and commit/snapshot reviewed
- **Mode:** read-only or implementation review
- **Files examined:** relevant paths, symbols, and tests

## Executive judgment

- **Decision:** `go`, `go-with-conditions`, `no-go`, or `insufficient-evidence`
- **Confidence:** `high`, `medium`, or `low`
- **Uncertainty:** what is unknown and why it matters
- **Material dissent:** disagreements that could change the decision

## Findings

Record one entry per material finding:

### Finding: <short title>

- **Finding:** precise claim, stated without speculation
- **Evidence:** file paths, symbols, test names, data records, or commands supporting it
- **Severity:** `critical`, `high`, `medium`, `low`, or `informational`
- **Confidence:** `high`, `medium`, or `low`
- **Assumptions:** assumptions required for the claim
- **Contradictions:** conflicting code, evidence, or reviewer conclusions
- **Impact:** effect on credit, money movement, safety, privacy, operations, or investigation quality
- **Recommended next check:** smallest check that could confirm, falsify, or reduce uncertainty

## Feature thesis (when applicable)

For a proposed credit, geo, fraud, or alternative-data feature, record:

- **Hypothesis**
- **Evidence source and provenance**
- **Expected economic value**
- **Failure mode**
- **Validation method**
- **Kill condition**

## Evidence and monetary integrity checks

Explicitly state whether the review found issues with:

- authoritative provenance and verification
- unknown-versus-bad treatment
- reason-code and consent-history preservation
- deterministic scoring boundaries
- approved amount, facility, tenor, pricing, repayment schedule, and outstanding balance
- LLM/agent authority boundaries
- reproducibility and version provenance
- evidence-type classification
- fairness and proxy risk
- accountable owner
- data lifecycle controls
- audit integrity
- production-boundary compliance

## Closing

- **Open questions**
- **Required owner and next action**
- **Evidence that would change the judgment**
