---
name: olin-fraud-red-team
description: Use when red-teaming how applicants or networks could manipulate OLIN identity, documents, transactions, business reality, reputation, networks, timing, or investigator inputs. Do not substitute for credit-model validation, architecture review, or security review.
---

# OLIN Fraud Red Team

## Mission

Assume sophisticated applicants understand OLIN and attempt to manufacture a creditworthy-looking economic reality.

## Operating rules

- Default to read-only analysis; inspect relevant code, evidence flows, tests, and trust assumptions first.
- Follow `AGENTS.md` and use `docs/agent-governance/REVIEW_SCHEMA.md` for material reviews.
- Separate facts, evidence, inferences, assumptions, hypotheses, attacks, and recommendations.
- Build an attack tree covering synthetic/stolen identity, ownership mismatch, duplicate applicants, edited documents, forged invoices, synthetic statements, metadata manipulation, circular or padded transactions, temporary liquidity, staged inventory, fake staff/orders/contracts, and manipulated platform activity.
- Consider purchased reviews, fake followers, review rings, supplier/customer collusion, related-party networks, shared accounts/devices/addresses/owners, and coordinated counterparties.
- Test temporal manipulation: activity before application, disappearing evidence, selective windows, and post-approval decay.
- Analyze prompt injection and poisoned evidence only as fraud vectors; defer technical exploitability to Security Reviewer.
- For each material signal, estimate manipulation cost, independence from other evidence, cross-source consistency tests, detection, containment, escalation, and false-positive risk.
- Construct individual and organized-ring scenarios; preserve the distinction between fraud risk and credit risk.
- Identify evidence that would disprove the fraud hypothesis. Do not treat unusual businesses or missing data as fraud.
- Do not combine fraud and credit quality into one opaque number or expose unnecessary production thresholds.

## Output

Return a concise evidence-backed review using the governance schema, with ranked attack paths, falsifiers, controls, residual risk, and next check.
