-- Investigator V1 Phase 3: closed assertion metadata profiles.
-- This changes evidence-reference eligibility only; reasoning results remain in memory.
-- Apply after 0001 through 0004 with the same controlled migration owner.

BEGIN;

DO $preflight$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
    RAISE EXCEPTION 'Phase 3 assertion migration requires a controlled superuser migration principal';
  END IF;
  IF to_regclass('investigator.investigation_evidence_reference') IS NULL
     OR to_regclass('investigator.investigation_evidence_semantics') IS NULL
     OR to_regclass('evidence_authority.investigator_evidence_projection_change') IS NULL THEN
    RAISE EXCEPTION 'Investigator migration 0004 must be applied first';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'investigator.investigation_evidence_reference'::regclass
      AND conname = 'investigation_evidence_reference_proposition_check'
  ) THEN
    RAISE EXCEPTION 'Expected Phase 2 proposition constraint is missing';
  END IF;
END
$preflight$;

SET SESSION AUTHORIZATION olin_investigator_owner;

ALTER TABLE investigator.investigation_evidence_reference
  DROP CONSTRAINT investigation_evidence_reference_proposition_check;

ALTER TABLE investigator.investigation_evidence_reference
  ADD CONSTRAINT investigation_evidence_reference_proposition_check CHECK ((
    (
      evidence_class = 'VERIFIED_FACT'
      AND verification_status = 'VERIFIED_FOR_PROPOSITION'
      AND proposition_type IS NOT NULL
      AND proposition_schema_version > 0
      AND proposition_value IS NOT NULL
      AND proposition_unit IS NOT NULL
      AND verification_method IS NOT NULL
      AND period_start IS NOT NULL
      AND period_end IS NOT NULL
      AND source_class IN (
        'accredited_data_provider', 'government_registry',
        'independent_auditor', 'regulated_financial_institution'
      )
    ) OR (
      evidence_class <> 'VERIFIED_FACT'
      AND verification_status = 'UNVERIFIED'
      AND proposition_type IS NULL
      AND proposition_schema_version IS NULL
      AND proposition_value IS NULL
      AND proposition_unit IS NULL
      AND verification_method IS NULL
    ) OR (
      verification_status = 'UNVERIFIED'
      AND proposition_type IS NOT NULL
      AND length(btrim(proposition_type)) > 0
      AND proposition_schema_version IS NOT NULL
      AND proposition_schema_version = 1
      AND proposition_value IS NOT NULL
      AND length(btrim(proposition_value)) > 0
      AND proposition_unit IS NOT NULL
      AND length(btrim(proposition_unit)) > 0
      AND verification_method IS NOT NULL
      AND period_start IS NOT NULL
      AND period_end IS NOT NULL
      AND issuer_id IS NOT NULL
      AND length(btrim(issuer_id)) > 0
      AND (
        (
          evidence_class = 'MERCHANT_SUPPLIED_ARTIFACT'
          AND verification_method = 'merchant_assertion_recorded:v1'
        ) OR (
          evidence_class = 'EXTERNAL_EVIDENCE'
          AND verification_method = 'external_assertion_recorded:v1'
        )
      )
    )
  ) IS TRUE);

RESET SESSION AUTHORIZATION;
COMMIT;
