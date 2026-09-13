# Phase 3: claims, unknowns, and contradictions

## Purpose and boundary

Phase 3 classifies sealed proposition metadata. It does not acquire or verify
evidence, reconstruct economics, score credit, recommend terms, rank actions,
invoke models, or persist assessments. Its output is an immutable in-memory
assessment, valid for the authority state bound to the completed operation.
Later use must not treat that historical binding as fresh authorization.

The supported production path is the PostgreSQL reasoning-currentness wrapper,
a capability active within that wrapper's transaction, the synchronous kernel,
an eager closed result, and final transaction/currentness checks before return.
An operation-local revocable lease binds the exact capability identity and
fingerprint; copied contexts and mutated capabilities fail after or during use.
Raw snapshots and serialized payloads are not authorization. The existing
in-memory evidence boundary remains an executable specification, not a production
Phase 3 authorization path.

## Meaning

The six epistemic types are `VERIFIED_FACT`, `MERCHANT_CLAIM`, `EXTERNAL_CLAIM`,
`UNKNOWN`, `CONTRADICTION`, and `POSSIBLE_EXPLANATION`.

Only an exact proposition already verified by Phase 2 can become a verified
fact. Authenticity of an artifact cannot verify its economic interpretation.
Claims preserve their source and asserted meaning. Observation time is not
assertion time; unavailable assertion timestamps remain unknown.

The closed assertion profiles are `merchant_assertion_recorded:v1` for
`MERCHANT_SUPPLIED_ARTIFACT` and `external_assertion_recorded:v1` for
`EXTERNAL_EVIDENCE`. Each requires `UNVERIFIED`, a complete proposition and period,
and a nonblank issuer. The existing authority-owned `verification_method` field
records the profile; its meaning here is that the Evidence Authority recorded an
assertion by the issuer, not that it verified the asserted economic value. An
ordinary upload, OCR extraction, or other document-processing method does not
qualify. The Evidence Authority owner is responsible for recording only
authorized assertion events under these profiles. Caller labels cannot publish
canonical authority or bypass the existing exact-reference checks.

The wrapper installs an operation-local lease binding the exact readiness
capability and a fingerprint of its sealed metadata. The kernel requires that
live lease. Wrapper completion invalidates the lease even in copied Python
contexts; mutation, direct activation, and post-operation reuse fail closed.
This enforces the application API and transaction-lifetime contract. It is not
a sandbox against arbitrary reflection or monkeypatching by trusted code running
in the same Python interpreter.

Migration `0005` admits those profiles into the existing durable reference
contract. The real PostgreSQL target test proves that both the unverified merchant
assertion and the verified bank observation reach the sealed wrapper together.

Missing proof and failed verification are uncertainty. Neither establishes
adverse credit quality or a contradiction. Contradictions do not establish fraud.
Possible explanations remain hypotheses, are not evidence, and are not ranked.

## First reconciliation rule

The synthetic target pairs claimed monthly revenue of 260,000 MXN with verified
bank-visible inflows of 118,000 MXN for the same subject and period. These are
different propositions. Their gap can trigger a reconciliation disagreement;
it cannot establish that the remaining revenue is false or that inflows equal
business revenue.

The initial rules use an explicit 20% reconciliation-gap threshold. For the
cross-scope revenue rule, the denominator is claimed revenue. For the supported
same-proposition rule, the denominator is the larger absolute compared value.
The canonical contradiction records both `0.20` and the denominator identifier,
and labels the result `RECONCILIATION_GAP_AT_LEAST_20_PERCENT`. This is a
versioned engineering policy for surfacing disagreement, not a calibrated
measure of economic or credit materiality. Its usefulness is unvalidated; a
change needs a rules-version change and new boundary examples.

The predefined explanation families cover cash revenue, another financial
account, processor or delivery-platform settlements, period or accounting
classification mismatch, and overstatement. No explanation is selected as true.

Only explicitly supported proposition meanings and compatible versions, periods,
and units may participate in a comparison. Phase 3 does not convert currencies,
normalize gross to net amounts, infer account coverage, or reconcile periods.

## Independence and provenance

References retain authority-owned semantic lineage and independence status.
Copies and corrections cannot add independent corroboration. Unknown independence
remains unknown. Cross-scope reconciliation also requires distinct original
semantic lineages and rejects shared economic-event or upstream-issuer identity;
this suppresses known circularity without promoting unknown independence.
Grouping references is provenance presentation, not voting or confidence
weighting.

Assessments bind tenant, case, snapshot identifier and digest, authority revision
and digest, evidence-state digest, and Phase 3 rules/schema versions. Findings
identify the relevant propositions, evidence references, and rule identifiers.

## Validation limits and ownership

The foundation tests representation, deterministic rule application, and boundary
enforcement. It establishes no approval lift, loss improvement, fraud detection,
or statistical calibration. Any later use in consequential credit decisions needs
its own validation and accountable institutional owner.

Preserve the Phase 2/2.5 authority, consent, lifecycle, and snapshot contracts.
Phase 4 is out of scope.

## Necessary forward migration

The accepted Phase 2 table constraint permits proposition metadata only on
verified facts. Its unverified branch requires all proposition fields, including
the recording method, to be null. Consequently, the canonical projection can
carry an unverified assertion but cannot accept it as a durable evidence
reference, and the readiness gate cannot seal it into a reasoning snapshot.

Migration `0005` is required to admit the two closed, versioned assertion profiles
on unverified evidence references. It preserves the verified-fact clause and the
legacy artifact-without-proposition clause. It adds no table, permission, evidence
acquisition mechanism, or assessment persistence. Existing evidence rows and
historical snapshots are not rewritten. New assertion references still pass the
existing canonical-equality, authority, tenant, consent, lineage, and lifecycle
checks and produce the existing evidence-acceptance audit events.

This migration is evidence-input contract support, not permission to persist
Phase 3 reasoning results. Deployment remains a controlled migration-owner
operation; this task validates it only in a disposable PostgreSQL 16 database.
