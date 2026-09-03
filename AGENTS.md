# OLIN durable review rules

These rules apply to every Codex task in this repository.

1. **Preserve before rewrite.** Understand existing architecture, reason codes, consent history, evidence provenance, deterministic scoring, safety boundaries, tests, and snapshots before changing anything. Read relevant code and tests before every non-trivial change.
2. **One monetary truth.** Do not introduce conflicting definitions of approved amount, facility structure, tenor, pricing, repayment schedule, or outstanding balance.
3. **Verified evidence only.** Caller-supplied labels such as `verified=true` never establish trust; derive trust from authoritative server-side provenance.
4. **Unknown is not bad.** Missing data is uncertainty, not automatically poor credit quality.
5. **Provenance is mandatory.** Every material conclusion identifies source, freshness/timestamp, verification state, confidence, and contradictions.
6. **No black-box credit authority.** LLMs and agents may investigate, infer, challenge, explain, and recommend; they may not be the authoritative money-moving decision mechanism.
7. **No big-bang rewrites.** Prefer incremental extraction, versioning, and migration.
8. **No feature without a thesis.** New credit, geo, fraud, or alternative-data features record a hypothesis, evidence source, expected economic value, failure mode, validation method, and kill condition.
9. **Security and privacy.** Grant minimum necessary permissions. Do not unnecessarily copy sensitive data, credentials, PII, financial records, or customer evidence.
10. **Independent review.** Important changes receive independent review before synthesis; reviewers must not anchor on one another.
11. **Required review output.** Use `docs/agent-governance/REVIEW_SCHEMA.md` and report findings, evidence, severity, confidence, assumptions, contradictions, and the recommended next check.
12. **Final judgment.** Agreement is not proof. Recommendations require evidence-weighted judgment and explicit uncertainty.
13. **OLIN doctrine.** OLIN investigates businesses conventional credit cannot fully understand: discover, verify, infer, and when possible create missing economic evidence; reconstruct business reality; search for viable financing structures; and learn from outcomes after capital is deployed.
14. **Relevant evidence over data volume.** Optimize for economically relevant evidence and information gain, not indiscriminate data collection.
15. **Research freedom, production separation.** Aggressively prototype challengers, novel evidence, simulations, agent workflows, and experimental underwriting in isolated research environments; the black-box prohibition applies to authoritative production and money-moving decisions.
16. **Distinct evidence types.** Keep verified observations, external evidence, merchant claims, model inferences, generated estimates, experimental observations, and research hypotheses distinct, each with provenance and confidence.
17. **Reproducibility.** Material results must be reproducible from versioned code, datasets/snapshots, feature definitions, models/configuration, prompts or agent versions, and policy versions.
18. **Human accountability.** Every consequential production credit decision, override, or money-moving authorization has an identifiable accountable human or institution.
19. **Fairness and proxy risk.** Test applicable credit, geo, behavioral, and alternative-data features for inappropriate proxies and disparate impact; geographic intelligence must measure economics, not protected characteristics.
20. **Audit integrity.** Durably audit material evidence acquisition, transformations, recommendations, overrides, and production decisions.
21. **Data lifecycle.** Define purpose, consent or authority, retention, deletion/withdrawal handling, and access boundaries for customer data.
22. **Secret and output hygiene.** Keep credentials, secrets, unnecessary raw PII, and sensitive customer evidence out of logs, prompts, reviews, summaries, and test fixtures.
23. **Hard production boundary.** Agents may not autonomously disburse money, alter terms, approve production credit, override policy, delete evidence, or expand permissions without the authorized production mechanism and required human or institutional approval.
