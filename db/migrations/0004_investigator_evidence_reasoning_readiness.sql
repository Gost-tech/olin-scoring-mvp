-- Investigator V1 Phase 2.5: semantic lineage and reasoning-readiness custody.
-- Canonical artifact bodies, consent authority, and source trust remain external.
-- Apply after 0001, 0002, and 0003 with the same dedicated migration owner.

BEGIN;

DO $preflight$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
    RAISE EXCEPTION 'Phase 2.5 migration requires a controlled superuser migration principal';
  END IF;
  IF to_regclass('investigator.investigation_evidence_reference') IS NULL
     OR to_regprocedure(
       'investigator.accept_evidence_reference(jsonb,uuid,bigint,uuid,text)'
     ) IS NULL THEN
    RAISE EXCEPTION 'Investigator migration 0003 must be applied first';
  END IF;
END
$preflight$;

CREATE SCHEMA evidence_authority
  AUTHORIZATION olin_investigator_owner;
REVOKE ALL ON SCHEMA evidence_authority FROM PUBLIC;

SET SESSION AUTHORIZATION olin_investigator_owner;

-- This append-only projection ledger is the authoritative eligibility state
-- consumed by Investigator reasoning. External systems remain upstream; their
-- changes become effective only when the isolated Evidence Authority commits a
-- corresponding row here.
CREATE TABLE evidence_authority.investigator_evidence_projection_change (
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  authority_revision bigint NOT NULL CHECK (authority_revision > 0),
  authority_state_digest text NOT NULL CHECK (
    authority_state_digest ~ '^[0-9a-f]{64}$'
  ),
  change_kind text NOT NULL CHECK (change_kind IN (
    'EVIDENCE_PROJECTED', 'CONSENT_CHANGED', 'EVIDENCE_REVOKED',
    'SOURCE_ATTESTATION_CHANGED', 'EVIDENCE_CORRECTED',
    'SEMANTIC_AUTHORITY_CHANGED'
  )),
  evidence_namespace text NOT NULL,
  evidence_id text NOT NULL,
  consent_purpose text NOT NULL,
  canonical_record jsonb NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  PRIMARY KEY (tenant_id, case_id, authority_revision),
  FOREIGN KEY (tenant_id, case_id)
    REFERENCES investigator.investigation_case (tenant_id, case_id)
);

CREATE INDEX investigator_evidence_projection_lookup_idx
  ON evidence_authority.investigator_evidence_projection_change (
    tenant_id, case_id, evidence_namespace, evidence_id, consent_purpose,
    authority_revision DESC
  );

CREATE FUNCTION evidence_authority.canonical_reader_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
STABLE
AS $function$
DECLARE
  role_name text := session_user;
  suffix text;
BEGIN
  IF role_name !~ '^olin_canonical_t_[0-9a-f]{32}$' THEN
    RETURN NULL;
  END IF;
  suffix := substring(role_name FROM length('olin_canonical_t_') + 1);
  RETURN (
    substring(suffix FROM 1 FOR 8) || '-' ||
    substring(suffix FROM 9 FOR 4) || '-' ||
    substring(suffix FROM 13 FOR 4) || '-' ||
    substring(suffix FROM 17 FOR 4) || '-' ||
    substring(suffix FROM 21 FOR 12)
  )::uuid;
END
$function$;

ALTER TABLE evidence_authority.investigator_evidence_projection_change
  ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_authority.investigator_evidence_projection_change
  FORCE ROW LEVEL SECURITY;
CREATE POLICY investigator_evidence_projection_tenant_policy
  ON evidence_authority.investigator_evidence_projection_change
  FOR ALL TO olin_investigator_owner
  USING (
    tenant_id = coalesce(
      investigator.session_tenant_id(),
      evidence_authority.canonical_reader_tenant_id()
    )
    AND tenant_id = investigator.context_tenant_id()
  )
  WITH CHECK (
    tenant_id = coalesce(
      investigator.session_tenant_id(),
      evidence_authority.canonical_reader_tenant_id()
    )
    AND tenant_id = investigator.context_tenant_id()
  );

CREATE FUNCTION evidence_authority.commit_investigator_evidence_projection(
  requested_record jsonb,
  expected_authority_revision bigint,
  requested_change_kind text
)
RETURNS TABLE(authority_revision bigint, authority_state_digest text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, evidence_authority, investigator
AS $function$
DECLARE
  tenant uuid := (requested_record->>'tenant_id')::uuid;
  case_identifier uuid := (requested_record->>'case_id')::uuid;
  next_revision bigint;
  prior_digest text;
  next_digest text;
BEGIN
  IF NOT pg_has_role(
    session_user, 'olin_investigator_evidence_authority', 'member'
  ) OR pg_has_role(session_user, 'olin_investigator_runtime', 'member')
     OR pg_has_role(session_user, 'olin_investigator_owner', 'member')
     OR EXISTS (
       SELECT 1 FROM pg_roles login
       WHERE login.rolname = session_user
         AND (login.rolsuper OR login.rolcreaterole OR login.rolcreatedb
              OR login.rolreplication OR login.rolbypassrls)
     )
     OR EXISTS (
       SELECT 1 FROM (
         SELECT (aclexplode(relacl)).grantee FROM pg_class
         UNION ALL SELECT (aclexplode(proacl)).grantee FROM pg_proc
         UNION ALL SELECT (aclexplode(nspacl)).grantee FROM pg_namespace
       ) direct_acl
       JOIN pg_roles grantee ON grantee.oid = direct_acl.grantee
       WHERE grantee.rolname = session_user
     )
     OR EXISTS (
       WITH RECURSIVE memberships(roleid) AS (
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN pg_roles login ON login.oid = membership.member
         WHERE login.rolname = session_user UNION
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN memberships prior ON membership.member = prior.roleid
       )
       SELECT 1 FROM memberships
       JOIN pg_roles granted ON granted.oid = memberships.roleid
       WHERE granted.rolname <> 'olin_investigator_evidence_authority'
     )
     OR NOT investigator.tenant_access_allowed(tenant) THEN
    RAISE EXCEPTION 'isolated tenant-bound evidence authority is required'
      USING ERRCODE = '42501';
  END IF;
  IF jsonb_typeof(requested_record) <> 'object'
     OR requested_record->>'projection_version'
        <> 'canonical-evidence-projection-1'
     OR requested_record->>'tenant_id' IS NULL
     OR requested_record->>'case_id' IS NULL
     OR nullif(requested_record->>'evidence_namespace', '') IS NULL
     OR nullif(requested_record->>'evidence_id', '') IS NULL
     OR nullif(requested_record->>'consent_purpose', '') IS NULL
     OR (requested_record - ARRAY[
       'projection_version', 'authority_digest', 'canonical_reference',
       'tenant_id', 'case_id', 'reference_id', 'subject_id', 'subject_digest',
       'evidence_namespace', 'evidence_id', 'evidence_version',
       'artifact_digest', 'evidence_class', 'lifecycle',
       'verification_status', 'proposition_type',
       'proposition_schema_version', 'proposition_value', 'proposition_unit',
       'verification_method', 'period_start', 'period_end', 'observed_at',
       'evidence_expires_at', 'source_id', 'issuer_id', 'acquisition_method',
       'source_class', 'source_attestation_id', 'source_attestation_version',
       'source_registry_digest', 'source_valid_until',
       'production_qualified_source', 'source_allows_proposition',
       'consent_namespace', 'consent_id', 'consent_version',
       'consent_purpose', 'consent_data_class', 'consent_use_scope',
       'consent_status', 'consent_expires_at', 'retention_until',
       'integrity_reference', 'integrity_valid',
       'semantic_independence_schema_version', 'semantic_lineage_id',
       'lineage_relation', 'derived_from_evidence_namespace',
       'derived_from_evidence_id', 'derived_from_evidence_version',
       'economic_event_id', 'upstream_issuer_id', 'independence_status',
       'independence_attestation_id', 'independence_attestation_version',
       'usability', 'unusable_reason', 'resolver_version', 'accepted_at',
       'supersedes_reference_id'
     ]::text[]) <> '{}'::jsonb THEN
    RAISE EXCEPTION 'canonical projection envelope is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF requested_change_kind NOT IN (
    'EVIDENCE_PROJECTED', 'CONSENT_CHANGED', 'EVIDENCE_REVOKED',
    'SOURCE_ATTESTATION_CHANGED', 'EVIDENCE_CORRECTED',
    'SEMANTIC_AUTHORITY_CHANGED'
  ) THEN
    RAISE EXCEPTION 'canonical projection change kind is unsupported'
      USING ERRCODE = '22023';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(
    tenant::text || ':reasoning-currentness:' || case_identifier::text, 0
  ));
  SELECT change.authority_revision, change.authority_state_digest
    INTO next_revision, prior_digest
  FROM evidence_authority.investigator_evidence_projection_change change
  WHERE change.tenant_id = tenant AND change.case_id = case_identifier
  ORDER BY change.authority_revision DESC LIMIT 1;
  next_revision := coalesce(next_revision, 0) + 1;
  IF expected_authority_revision <> next_revision - 1 THEN
    RAISE EXCEPTION 'stale canonical authority revision'
      USING ERRCODE = '40001';
  END IF;
  prior_digest := coalesce(prior_digest, repeat('0', 64));
  next_digest := encode(sha256(convert_to(
    prior_digest || ':' || next_revision::text || ':' ||
    requested_change_kind || ':' || investigator.canonical_json(requested_record),
    'UTF8'
  )), 'hex');
  INSERT INTO evidence_authority.investigator_evidence_projection_change (
    tenant_id, case_id, authority_revision, authority_state_digest,
    change_kind, evidence_namespace, evidence_id, consent_purpose,
    canonical_record
  ) VALUES (
    tenant, case_identifier, next_revision, next_digest,
    requested_change_kind, requested_record->>'evidence_namespace',
    requested_record->>'evidence_id', requested_record->>'consent_purpose',
    requested_record
  );
  RETURN QUERY SELECT next_revision, next_digest;
END
$function$;

CREATE VIEW evidence_authority.investigator_evidence_v1
WITH (security_barrier = true) AS
SELECT item.*, latest.authority_revision, latest.authority_state_digest
FROM (
  SELECT DISTINCT ON (
    change.tenant_id, change.case_id, change.evidence_namespace,
    change.evidence_id, change.consent_purpose
  ) change.*
  FROM evidence_authority.investigator_evidence_projection_change change
  ORDER BY change.tenant_id, change.case_id, change.evidence_namespace,
    change.evidence_id, change.consent_purpose, change.authority_revision DESC
) latest
CROSS JOIN LATERAL jsonb_to_record(latest.canonical_record) AS item(
  projection_version text, authority_digest text, canonical_reference jsonb,
  tenant_id uuid, case_id uuid, subject_id text, subject_digest text,
  evidence_namespace text, evidence_id text, evidence_version text,
  artifact_digest text, evidence_class text, lifecycle text,
  verification_status text, proposition_type text,
  proposition_schema_version integer, proposition_value text,
  proposition_unit text, verification_method text, period_start timestamptz,
  period_end timestamptz, observed_at timestamptz,
  evidence_expires_at timestamptz, source_id text, issuer_id text,
  acquisition_method text, source_class text, source_attestation_id text,
  source_attestation_version text, source_registry_digest text,
  source_valid_until timestamptz, production_qualified_source boolean,
  source_allows_proposition boolean, consent_namespace text, consent_id text,
  consent_version text, consent_purpose text, consent_data_class text,
  consent_use_scope text, consent_status text, consent_expires_at timestamptz,
  retention_until timestamptz, integrity_reference text,
  integrity_valid boolean, semantic_independence_schema_version integer,
  semantic_lineage_id text, lineage_relation text,
  derived_from_evidence_namespace text, derived_from_evidence_id text,
  derived_from_evidence_version text, economic_event_id text,
  upstream_issuer_id text, independence_status text,
  independence_attestation_id text, independence_attestation_version text,
  usability text, unusable_reason text
);

CREATE FUNCTION investigator.current_canonical_authority_revision(
  requested_tenant_id uuid,
  requested_case_id uuid
)
RETURNS TABLE(authority_revision bigint, authority_state_digest text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, evidence_authority, investigator
STABLE
AS $function$
BEGIN
  IF NOT pg_has_role(session_user, 'olin_investigator_runtime', 'member')
     OR pg_has_role(
       session_user, 'olin_investigator_evidence_authority', 'member'
     )
     OR pg_has_role(session_user, 'olin_investigator_owner', 'member')
     OR NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'isolated tenant-bound Investigator runtime is required'
      USING ERRCODE = '42501';
  END IF;
  RETURN QUERY
  SELECT change.authority_revision, change.authority_state_digest
  FROM evidence_authority.investigator_evidence_projection_change change
  WHERE change.tenant_id = requested_tenant_id
    AND change.case_id = requested_case_id
  ORDER BY change.authority_revision DESC LIMIT 1;
  IF NOT FOUND THEN
    RETURN QUERY SELECT 0::bigint, repeat('0', 64)::text;
  END IF;
END
$function$;

CREATE TABLE investigator.investigation_evidence_semantics (
  reference_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  semantic_schema_version integer NOT NULL CHECK (
    semantic_schema_version IN (0, 1)
  ),
  semantic_lineage_id text NOT NULL CHECK (
    octet_length(btrim(semantic_lineage_id)) BETWEEN 1 AND 240
  ),
  lineage_relation text NOT NULL CHECK (lineage_relation IN (
    'ORIGINAL', 'DERIVED_COPY', 'CORRECTION', 'UNKNOWN'
  )),
  derived_from_evidence_namespace text,
  derived_from_evidence_id text,
  derived_from_evidence_version text,
  economic_event_id text CHECK (
    economic_event_id IS NULL
    OR octet_length(btrim(economic_event_id)) BETWEEN 1 AND 240
  ),
  upstream_issuer_id text NOT NULL CHECK (
    octet_length(btrim(upstream_issuer_id)) BETWEEN 1 AND 240
  ),
  independence_status text NOT NULL CHECK (independence_status IN (
    'INDEPENDENCE_UNKNOWN', 'INDEPENDENT_VERIFIED'
  )),
  independence_attestation_id text,
  independence_attestation_version text,
  semantics_digest text NOT NULL CHECK (semantics_digest ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  CONSTRAINT investigation_evidence_semantics_reference_fk
    FOREIGN KEY (tenant_id, case_id, reference_id)
    REFERENCES investigator.investigation_evidence_reference (
      tenant_id, case_id, reference_id
    ),
  CONSTRAINT investigation_evidence_semantics_parent_shape CHECK (
    (
      derived_from_evidence_namespace IS NULL
      AND derived_from_evidence_id IS NULL
      AND derived_from_evidence_version IS NULL
    ) OR (
      derived_from_evidence_namespace IS NOT NULL
      AND derived_from_evidence_id IS NOT NULL
      AND derived_from_evidence_version IS NOT NULL
      AND
      octet_length(btrim(derived_from_evidence_namespace)) BETWEEN 1 AND 120
      AND octet_length(btrim(derived_from_evidence_id)) BETWEEN 1 AND 240
      AND octet_length(btrim(derived_from_evidence_version)) BETWEEN 1 AND 120
    )
  ),
  CONSTRAINT investigation_evidence_semantics_relation_check CHECK (
    (
      lineage_relation IN ('DERIVED_COPY', 'CORRECTION')
      AND derived_from_evidence_id IS NOT NULL
    ) OR (
      lineage_relation = 'ORIGINAL'
      AND derived_from_evidence_id IS NULL
    ) OR (
      lineage_relation = 'UNKNOWN'
      AND derived_from_evidence_id IS NULL
    )
  ),
  CONSTRAINT investigation_evidence_semantics_independence_check CHECK (
    (
      independence_status = 'INDEPENDENCE_UNKNOWN'
      AND independence_attestation_id IS NULL
      AND independence_attestation_version IS NULL
    ) OR (
      independence_status = 'INDEPENDENT_VERIFIED'
      AND lineage_relation = 'ORIGINAL'
      AND independence_attestation_id IS NOT NULL
      AND independence_attestation_version IS NOT NULL
      AND octet_length(btrim(independence_attestation_id)) BETWEEN 1 AND 240
      AND octet_length(btrim(independence_attestation_version)) BETWEEN 1 AND 120
    )
  )
);

CREATE INDEX investigation_evidence_semantics_lineage_idx
  ON investigator.investigation_evidence_semantics (
    tenant_id, case_id, semantic_lineage_id
  );
CREATE UNIQUE INDEX investigation_evidence_semantics_independence_basis_uq
  ON investigator.investigation_evidence_semantics (
    tenant_id, case_id, independence_attestation_id
  ) WHERE independence_status = 'INDEPENDENT_VERIFIED';
CREATE UNIQUE INDEX investigation_evidence_semantics_event_upstream_uq
  ON investigator.investigation_evidence_semantics (
    tenant_id, case_id, economic_event_id, upstream_issuer_id
  ) WHERE independence_status = 'INDEPENDENT_VERIFIED'
      AND economic_event_id IS NOT NULL;

-- Durable Phase 2 rows remain auditable but are explicitly ineligible for the
-- reasoning gate until canonical semantic authority is established forward.
-- The Phase 2 reference table uses forced RLS.  The owner intentionally has no
-- cross-tenant read path, so the controlled migration principal must perform
-- this one-time backfill or the SELECT would silently see no legacy rows.
RESET SESSION AUTHORIZATION;

WITH legacy_semantics AS (
  SELECT
    ref.reference_id,
    ref.tenant_id,
    ref.case_id,
    'legacy:' || encode(sha256(convert_to(
      ref.evidence_namespace || ':' || ref.evidence_id,
      'UTF8'
    )), 'hex') AS semantic_lineage_id,
    CASE
      WHEN ref.supersedes_reference_id IS NULL THEN 'UNKNOWN'
      ELSE 'CORRECTION'
    END AS lineage_relation,
    prior.evidence_namespace AS derived_from_evidence_namespace,
    prior.evidence_id AS derived_from_evidence_id,
    prior.evidence_version AS derived_from_evidence_version,
    ref.issuer_id AS upstream_issuer_id
  FROM investigator.investigation_evidence_reference ref
  LEFT JOIN investigator.investigation_evidence_reference prior
    ON prior.tenant_id = ref.tenant_id
   AND prior.case_id = ref.case_id
   AND prior.reference_id = ref.supersedes_reference_id
)
INSERT INTO investigator.investigation_evidence_semantics (
  reference_id, tenant_id, case_id, semantic_schema_version,
  semantic_lineage_id, lineage_relation,
  derived_from_evidence_namespace, derived_from_evidence_id,
  derived_from_evidence_version, upstream_issuer_id,
  independence_status, semantics_digest
)
SELECT
  legacy.reference_id, legacy.tenant_id, legacy.case_id, 0,
  legacy.semantic_lineage_id, legacy.lineage_relation,
  legacy.derived_from_evidence_namespace,
  legacy.derived_from_evidence_id,
  legacy.derived_from_evidence_version,
  legacy.upstream_issuer_id, 'INDEPENDENCE_UNKNOWN',
  encode(sha256(convert_to(
    investigator.canonical_json(jsonb_build_object(
      'derived_from_evidence_id', legacy.derived_from_evidence_id,
      'derived_from_evidence_namespace', legacy.derived_from_evidence_namespace,
      'derived_from_evidence_version', legacy.derived_from_evidence_version,
      'economic_event_id', NULL,
      'independence_attestation_id', NULL,
      'independence_attestation_version', NULL,
      'independence_status', 'INDEPENDENCE_UNKNOWN',
      'lineage_relation', legacy.lineage_relation,
      'semantic_lineage_id', legacy.semantic_lineage_id,
      'semantic_schema_version', 0,
      'upstream_issuer_id', legacy.upstream_issuer_id
    )), 'UTF8'
  )), 'hex')
FROM legacy_semantics legacy;

SET SESSION AUTHORIZATION olin_investigator_owner;

ALTER TABLE investigator.investigation_evidence_semantics ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_evidence_semantics FORCE ROW LEVEL SECURITY;
CREATE POLICY investigation_evidence_semantics_tenant_policy
  ON investigator.investigation_evidence_semantics
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner,
     olin_investigator_evidence_authority
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE TRIGGER investigation_evidence_semantics_immutable
BEFORE UPDATE OR DELETE ON investigator.investigation_evidence_semantics
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();
CREATE TRIGGER investigation_evidence_semantics_no_truncate
BEFORE TRUNCATE ON investigator.investigation_evidence_semantics
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE FUNCTION investigator.accept_evidence_reference_v2(
  requested_reference jsonb,
  requested_semantics jsonb,
  requested_current_snapshot_id uuid,
  expected_case_version bigint,
  requested_event_id uuid,
  requested_idempotency_key text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  tenant uuid := (requested_reference->>'tenant_id')::uuid;
  case_identifier uuid := (requested_reference->>'case_id')::uuid;
  reference_identifier uuid := (requested_reference->>'reference_id')::uuid;
  semantic_digest text := encode(sha256(convert_to(
    investigator.canonical_json(requested_semantics), 'UTF8'
  )), 'hex');
  existing investigator.investigation_evidence_semantics%ROWTYPE;
  prior_namespace text;
  prior_evidence_id text;
  prior_version text;
  prior_lineage_id text;
  canonical_record jsonb;
  canonical_count bigint;
BEGIN
  IF NOT pg_has_role(
    session_user, 'olin_investigator_evidence_authority', 'member'
  ) OR pg_has_role(session_user, 'olin_investigator_runtime', 'member')
     OR pg_has_role(session_user, 'olin_investigator_owner', 'member')
     OR EXISTS (
       SELECT 1 FROM pg_roles login
       WHERE login.rolname = session_user
         AND (login.rolsuper OR login.rolcreaterole OR login.rolcreatedb
              OR login.rolreplication OR login.rolbypassrls)
     )
     OR EXISTS (
       SELECT 1 FROM pg_roles authority_role
       WHERE authority_role.rolname = 'olin_investigator_evidence_authority'
         AND (authority_role.rolsuper OR authority_role.rolcreaterole
              OR authority_role.rolcreatedb OR authority_role.rolreplication
              OR authority_role.rolbypassrls)
     )
     OR EXISTS (
       SELECT 1 FROM (
         SELECT (aclexplode(relacl)).grantee FROM pg_class
         UNION ALL SELECT (aclexplode(proacl)).grantee FROM pg_proc
         UNION ALL SELECT (aclexplode(nspacl)).grantee FROM pg_namespace
       ) direct_acl
       JOIN pg_roles grantee ON grantee.oid = direct_acl.grantee
       WHERE grantee.rolname = session_user
     )
     OR EXISTS (
       WITH RECURSIVE memberships(roleid) AS (
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN pg_roles login ON login.oid = membership.member
         WHERE login.rolname = session_user
         UNION
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN memberships prior ON membership.member = prior.roleid
       )
       SELECT 1 FROM memberships
       JOIN pg_roles granted ON granted.oid = memberships.roleid
       WHERE granted.rolname <> 'olin_investigator_evidence_authority'
     )
     OR NOT investigator.tenant_access_allowed(tenant) THEN
    RAISE EXCEPTION 'isolated tenant-bound evidence authority is required'
      USING ERRCODE = '42501';
  END IF;
  IF requested_reference ?| ARRAY[
    'independent', 'independence_status', 'semantic_lineage_id',
    'economic_event_id', 'derived_from_evidence_id',
    'independence_attestation_id'
  ] THEN
    RAISE EXCEPTION 'caller independence fields are forbidden in the reference envelope'
      USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(requested_semantics) <> 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(requested_semantics)) <> 11
     OR NOT requested_semantics ?& ARRAY[
       'semantic_schema_version', 'semantic_lineage_id', 'lineage_relation',
       'derived_from_evidence_namespace', 'derived_from_evidence_id',
       'derived_from_evidence_version', 'economic_event_id',
       'upstream_issuer_id', 'independence_status',
       'independence_attestation_id', 'independence_attestation_version'
     ] THEN
    RAISE EXCEPTION 'semantic independence envelope is not schema-exact'
      USING ERRCODE = '22023';
  END IF;
  IF octet_length(requested_semantics::text) > 4096
     OR requested_semantics->>'semantic_schema_version' <> '1'
     OR octet_length(btrim(requested_semantics->>'semantic_lineage_id')) NOT BETWEEN 1 AND 240
     OR octet_length(btrim(requested_semantics->>'upstream_issuer_id')) NOT BETWEEN 1 AND 240
     OR requested_semantics->>'lineage_relation' NOT IN (
       'ORIGINAL', 'DERIVED_COPY', 'CORRECTION', 'UNKNOWN'
     )
     OR requested_semantics->>'independence_status' NOT IN (
       'INDEPENDENCE_UNKNOWN', 'INDEPENDENT_VERIFIED'
     ) THEN
    RAISE EXCEPTION 'semantic independence values are invalid'
      USING ERRCODE = '22023';
  END IF;
  IF EXISTS (
    SELECT 1 FROM jsonb_each_text(requested_semantics) item
    WHERE item.key IN (
      'semantic_lineage_id', 'upstream_issuer_id', 'economic_event_id',
      'independence_attestation_id', 'independence_attestation_version',
      'derived_from_evidence_namespace', 'derived_from_evidence_id',
      'derived_from_evidence_version'
    ) AND item.value IS DISTINCT FROM btrim(item.value)
  ) THEN
    RAISE EXCEPTION 'semantic identifiers must be canonical without surrounding whitespace'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'lineage_relation' IN ('DERIVED_COPY', 'CORRECTION')
     AND (
       nullif(requested_semantics->>'derived_from_evidence_namespace', '') IS NULL
       OR nullif(requested_semantics->>'derived_from_evidence_id', '') IS NULL
       OR nullif(requested_semantics->>'derived_from_evidence_version', '') IS NULL
     ) THEN
    RAISE EXCEPTION 'derived/corrected evidence requires a canonical parent'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'lineage_relation' = 'ORIGINAL'
     AND nullif(requested_semantics->>'derived_from_evidence_id', '') IS NOT NULL THEN
    RAISE EXCEPTION 'original evidence cannot have a parent'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'lineage_relation' = 'UNKNOWN'
     AND (
       nullif(requested_semantics->>'derived_from_evidence_namespace', '') IS NOT NULL
       OR nullif(requested_semantics->>'derived_from_evidence_id', '') IS NOT NULL
       OR nullif(requested_semantics->>'derived_from_evidence_version', '') IS NOT NULL
     ) THEN
    RAISE EXCEPTION 'unknown lineage relation cannot claim a parent'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'lineage_relation' = 'CORRECTION'
     AND nullif(requested_reference->>'supersedes_reference_id', '') IS NULL THEN
    RAISE EXCEPTION 'correction requires an existing superseded evidence reference'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'lineage_relation' = 'DERIVED_COPY'
     AND NOT EXISTS (
       SELECT 1
       FROM investigator.investigation_evidence_reference ref
       JOIN investigator.investigation_evidence_semantics item
         ON item.tenant_id = ref.tenant_id AND item.case_id = ref.case_id
        AND item.reference_id = ref.reference_id
       WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
         AND ref.evidence_namespace =
             requested_semantics->>'derived_from_evidence_namespace'
         AND ref.evidence_id = requested_semantics->>'derived_from_evidence_id'
         AND ref.evidence_version =
             requested_semantics->>'derived_from_evidence_version'
         AND item.semantic_lineage_id =
             requested_semantics->>'semantic_lineage_id'
     ) THEN
    RAISE EXCEPTION 'derived copy requires an existing parent in the same lineage'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'independence_status' = 'INDEPENDENT_VERIFIED'
     AND (
       requested_semantics->>'lineage_relation' <> 'ORIGINAL'
       OR nullif(requested_semantics->>'independence_attestation_id', '') IS NULL
       OR nullif(requested_semantics->>'independence_attestation_version', '') IS NULL
     ) THEN
    RAISE EXCEPTION 'verified independence requires proven original lineage and a versioned canonical attestation'
      USING ERRCODE = '22023';
  END IF;
  IF requested_semantics->>'independence_status' = 'INDEPENDENCE_UNKNOWN'
     AND (
       nullif(requested_semantics->>'independence_attestation_id', '') IS NOT NULL
       OR nullif(requested_semantics->>'independence_attestation_version', '') IS NOT NULL
     ) THEN
    RAISE EXCEPTION 'unknown independence cannot carry an attestation'
      USING ERRCODE = '22023';
  END IF;

  -- Bind the write to the exact semantic state exposed by the separately owned
  -- canonical Passport/consent/source projection. Role custody alone does not
  -- prove that a claimed independence attestation exists.
  IF to_regclass('evidence_authority.investigator_evidence_v1') IS NULL THEN
    RAISE EXCEPTION 'canonical evidence authority projection is unavailable'
      USING ERRCODE = '55000';
  END IF;
  EXECUTE
    'SELECT count(*), (array_agg(to_jsonb(canonical)))[1] '
    'FROM (SELECT * FROM evidence_authority.investigator_evidence_v1 '
    'WHERE tenant_id=$1 AND case_id=$2 AND evidence_namespace=$3 '
    'AND evidence_id=$4 AND consent_purpose=$5 LIMIT 2) canonical'
    INTO canonical_count, canonical_record
    USING tenant, case_identifier,
      requested_reference->>'evidence_namespace',
      requested_reference->>'evidence_id',
      requested_reference->>'consent_purpose';
  IF canonical_count <> 1 OR canonical_record IS NULL
     OR canonical_record->>'projection_version'
        <> 'canonical-evidence-projection-1'
     OR jsonb_typeof(canonical_record->'canonical_reference') <> 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(
       canonical_record->'canonical_reference'
     )) <> 43
     OR canonical_record->'canonical_reference' IS DISTINCT FROM (
       requested_reference - ARRAY[
         'reference_id', 'accepted_at', 'supersedes_reference_id'
       ]::text[]
     )
     OR canonical_record->>'authority_digest'
        IS DISTINCT FROM requested_reference->>'authority_digest'
     OR jsonb_build_object(
       'semantic_schema_version',
         canonical_record->'semantic_independence_schema_version',
       'semantic_lineage_id', canonical_record->'semantic_lineage_id',
       'lineage_relation', canonical_record->'lineage_relation',
       'derived_from_evidence_namespace',
         canonical_record->'derived_from_evidence_namespace',
       'derived_from_evidence_id', canonical_record->'derived_from_evidence_id',
       'derived_from_evidence_version',
         canonical_record->'derived_from_evidence_version',
       'economic_event_id', canonical_record->'economic_event_id',
       'upstream_issuer_id', canonical_record->'upstream_issuer_id',
       'independence_status', canonical_record->'independence_status',
       'independence_attestation_id',
         canonical_record->'independence_attestation_id',
       'independence_attestation_version',
         canonical_record->'independence_attestation_version'
     ) IS DISTINCT FROM requested_semantics THEN
    RAISE EXCEPTION 'requested evidence semantics do not match canonical authority'
      USING ERRCODE = '22023';
  END IF;

  -- Distinct artifacts have distinct v1 locks. Serialize all decisions about a
  -- semantic lineage so concurrent requests cannot inflate independent support.
  PERFORM pg_advisory_xact_lock(hashtextextended(
    tenant::text || ':' || case_identifier::text || ':semantic-lineage:' ||
      (requested_semantics->>'semantic_lineage_id'), 0
  ));

  PERFORM investigator.accept_evidence_reference(
    requested_reference, requested_current_snapshot_id, expected_case_version,
    requested_event_id, requested_idempotency_key
  );

  SELECT * INTO existing FROM investigator.investigation_evidence_semantics item
    WHERE item.reference_id = reference_identifier AND item.tenant_id = tenant
      AND item.case_id = case_identifier;
  IF FOUND THEN
    IF existing.semantics_digest = semantic_digest THEN
      RETURN reference_identifier;
    END IF;
    RAISE EXCEPTION 'semantic replay conflicts with immutable history'
      USING ERRCODE = '23505';
  END IF;
  IF requested_semantics->>'independence_status' = 'INDEPENDENT_VERIFIED'
     AND EXISTS (
       SELECT 1 FROM investigator.investigation_evidence_semantics item
       WHERE item.tenant_id = tenant AND item.case_id = case_identifier
         AND item.reference_id <> reference_identifier
         AND item.independence_status = 'INDEPENDENT_VERIFIED'
         AND (
           (
             item.independence_attestation_id =
               requested_semantics->>'independence_attestation_id'
           ) OR (
             nullif(requested_semantics->>'economic_event_id', '') IS NOT NULL
             AND item.economic_event_id =
               requested_semantics->>'economic_event_id'
             AND item.upstream_issuer_id =
               requested_semantics->>'upstream_issuer_id'
           )
         )
     ) THEN
    RAISE EXCEPTION 'verified independence basis cannot be reused as new support'
      USING ERRCODE = '23505';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM investigator.investigation_evidence_reference ref
    JOIN investigator.investigation_evidence_semantics item
      ON item.tenant_id = ref.tenant_id AND item.case_id = ref.case_id
     AND item.reference_id = ref.reference_id
    WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
      AND ref.reference_id <> reference_identifier
      AND ref.artifact_digest = requested_reference->>'artifact_digest'
      AND item.semantic_lineage_id <> requested_semantics->>'semantic_lineage_id'
  ) THEN
    RAISE EXCEPTION 'the same artifact cannot acquire another semantic lineage'
      USING ERRCODE = '23505';
  END IF;
  IF requested_semantics->>'independence_status' = 'INDEPENDENT_VERIFIED'
     AND EXISTS (
       SELECT 1 FROM investigator.investigation_evidence_semantics item
       WHERE item.tenant_id = tenant AND item.case_id = case_identifier
         AND item.semantic_lineage_id = requested_semantics->>'semantic_lineage_id'
     ) THEN
    RAISE EXCEPTION 'the same semantic lineage cannot become independent support'
      USING ERRCODE = '23505';
  END IF;

  IF nullif(requested_reference->>'supersedes_reference_id', '') IS NOT NULL THEN
    SELECT ref.evidence_namespace, ref.evidence_id, ref.evidence_version,
           item.semantic_lineage_id
      INTO prior_namespace, prior_evidence_id, prior_version, prior_lineage_id
      FROM investigator.investigation_evidence_reference ref
      JOIN investigator.investigation_evidence_semantics item
        ON item.tenant_id = ref.tenant_id AND item.case_id = ref.case_id
       AND item.reference_id = ref.reference_id
      WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
        AND ref.reference_id = (requested_reference->>'supersedes_reference_id')::uuid;
    IF NOT FOUND
       OR requested_semantics->>'lineage_relation' <> 'CORRECTION'
       OR requested_semantics->>'semantic_lineage_id' <> prior_lineage_id
       OR requested_semantics->>'derived_from_evidence_namespace' <> prior_namespace
       OR requested_semantics->>'derived_from_evidence_id' <> prior_evidence_id
       OR requested_semantics->>'derived_from_evidence_version' <> prior_version THEN
      RAISE EXCEPTION 'correction must preserve canonical lineage and parent identity'
        USING ERRCODE = '22023';
    END IF;
  END IF;

  INSERT INTO investigator.investigation_evidence_semantics (
    reference_id, tenant_id, case_id, semantic_schema_version,
    semantic_lineage_id, lineage_relation,
    derived_from_evidence_namespace, derived_from_evidence_id,
    derived_from_evidence_version, economic_event_id, upstream_issuer_id,
    independence_status, independence_attestation_id,
    independence_attestation_version, semantics_digest
  ) VALUES (
    reference_identifier, tenant, case_identifier,
    (requested_semantics->>'semantic_schema_version')::integer,
    requested_semantics->>'semantic_lineage_id',
    requested_semantics->>'lineage_relation',
    nullif(requested_semantics->>'derived_from_evidence_namespace', ''),
    nullif(requested_semantics->>'derived_from_evidence_id', ''),
    nullif(requested_semantics->>'derived_from_evidence_version', ''),
    nullif(requested_semantics->>'economic_event_id', ''),
    requested_semantics->>'upstream_issuer_id',
    requested_semantics->>'independence_status',
    nullif(requested_semantics->>'independence_attestation_id', ''),
    nullif(requested_semantics->>'independence_attestation_version', ''),
    semantic_digest
  );
  RETURN reference_identifier;
END
$function$;

-- Preserve the Phase 2 builder as an internal implementation, then enrich only
-- newly inserted v2 snapshots at the immutable table boundary. The public
-- wrapper returns the post-trigger digest, avoiding a second snapshot authority.
ALTER FUNCTION investigator.create_snapshot_v2(uuid, uuid, bigint, text)
  RENAME TO create_snapshot_v2_phase2_legacy;

CREATE FUNCTION investigator.enrich_snapshot_v2_semantics()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  payload jsonb := NEW.canonical_snapshot_payload;
  accepted_refs jsonb;
  unusable_refs jsonb;
  evidence_digest text;
  authority_revision bigint;
  authority_state_digest text;
BEGIN
  IF NEW.snapshot_schema_version <> 2 THEN
    RETURN NEW;
  END IF;
  SELECT change.authority_revision, change.authority_state_digest
    INTO authority_revision, authority_state_digest
  FROM evidence_authority.investigator_evidence_projection_change change
  WHERE change.tenant_id = NEW.tenant_id AND change.case_id = NEW.case_id
  ORDER BY change.authority_revision DESC LIMIT 1;
  authority_revision := coalesce(authority_revision, 0);
  authority_state_digest := coalesce(authority_state_digest, repeat('0', 64));
  WITH enriched AS (
    SELECT item.ordinality, item.value || jsonb_build_object(
      'semantic_independence', jsonb_build_object(
        'schema_version', sem.semantic_schema_version,
        'semantic_lineage_id', sem.semantic_lineage_id,
        'lineage_relation', sem.lineage_relation,
        'derived_from_evidence_namespace', sem.derived_from_evidence_namespace,
        'derived_from_evidence_id', sem.derived_from_evidence_id,
        'derived_from_evidence_version', sem.derived_from_evidence_version,
        'economic_event_id', sem.economic_event_id,
        'upstream_issuer_id', sem.upstream_issuer_id,
        'independence_status', sem.independence_status,
        'independence_attestation_id', sem.independence_attestation_id,
        'independence_attestation_version', sem.independence_attestation_version
      )
    ) AS value
    FROM jsonb_array_elements(
      payload #> '{evidence,accepted_evidence_refs}'
    ) WITH ORDINALITY item(value, ordinality)
    JOIN investigator.investigation_evidence_semantics sem
      ON sem.tenant_id = NEW.tenant_id AND sem.case_id = NEW.case_id
     AND sem.reference_id = (item.value->>'reference_id')::uuid
  )
  SELECT coalesce(jsonb_agg(value ORDER BY ordinality), '[]'::jsonb)
    INTO accepted_refs FROM enriched;
  WITH enriched AS (
    SELECT item.ordinality, item.value || jsonb_build_object(
      'semantic_independence', jsonb_build_object(
        'schema_version', sem.semantic_schema_version,
        'semantic_lineage_id', sem.semantic_lineage_id,
        'lineage_relation', sem.lineage_relation,
        'derived_from_evidence_namespace', sem.derived_from_evidence_namespace,
        'derived_from_evidence_id', sem.derived_from_evidence_id,
        'derived_from_evidence_version', sem.derived_from_evidence_version,
        'economic_event_id', sem.economic_event_id,
        'upstream_issuer_id', sem.upstream_issuer_id,
        'independence_status', sem.independence_status,
        'independence_attestation_id', sem.independence_attestation_id,
        'independence_attestation_version', sem.independence_attestation_version
      )
    ) AS value
    FROM jsonb_array_elements(
      payload #> '{evidence,unusable_evidence_refs}'
    ) WITH ORDINALITY item(value, ordinality)
    JOIN investigator.investigation_evidence_semantics sem
      ON sem.tenant_id = NEW.tenant_id AND sem.case_id = NEW.case_id
     AND sem.reference_id = (item.value->>'reference_id')::uuid
  )
  SELECT coalesce(jsonb_agg(value ORDER BY ordinality), '[]'::jsonb)
    INTO unusable_refs FROM enriched;
  IF jsonb_array_length(accepted_refs) + jsonb_array_length(unusable_refs) <>
     jsonb_array_length(payload #> '{evidence,accepted_evidence_refs}') +
     jsonb_array_length(payload #> '{evidence,unusable_evidence_refs}') THEN
    RAISE EXCEPTION 'snapshot semantic authority is incomplete'
      USING ERRCODE = '55000';
  END IF;
  SELECT encode(sha256(convert_to(investigator.canonical_json(
    jsonb_build_object(
      'accepted_reference_ids', coalesce((
        SELECT jsonb_agg(item->>'reference_id' ORDER BY item->>'reference_id')
        FROM jsonb_array_elements(accepted_refs) item
      ), '[]'::jsonb),
      'unusable_references', coalesce((
        SELECT jsonb_agg(jsonb_build_object(
          'reference_id', item->>'reference_id',
          'reason', item->>'unusable_reason'
        ) ORDER BY item->>'reference_id')
        FROM jsonb_array_elements(unusable_refs) item
      ), '[]'::jsonb),
      'evidence_state_version',
        payload #> '{evidence,evidence_state_version}',
      'references', coalesce((
        SELECT jsonb_agg(item - 'unusable_reason' ORDER BY item->>'reference_id')
        FROM jsonb_array_elements(accepted_refs || unusable_refs) item
      ), '[]'::jsonb)
    )
  ), 'UTF8')), 'hex') INTO evidence_digest;
  payload := jsonb_set(
    payload,
    '{applicable_versions,semantic_independence}',
    to_jsonb('investigator-evidence-semantics-1'::text),
    true
  );
  payload := jsonb_set(
    payload, '{canonical_authority}', jsonb_build_object(
      'projection_version', 'canonical-evidence-projection-1',
      'authority_revision', authority_revision,
      'authority_state_digest', authority_state_digest
    ), true
  );
  payload := jsonb_set(
    payload, '{evidence,accepted_evidence_refs}', accepted_refs, false
  );
  payload := jsonb_set(
    payload, '{evidence,unusable_evidence_refs}', unusable_refs, false
  );
  payload := jsonb_set(
    payload, '{evidence,evidence_state_digest}', to_jsonb(evidence_digest), false
  );
  NEW.canonical_snapshot_payload := payload;
  NEW.canonical_snapshot_bytes := convert_to(
    investigator.canonical_json(payload), 'UTF8'
  );
  NEW.canonical_digest := encode(sha256(NEW.canonical_snapshot_bytes), 'hex');
  RETURN NEW;
END
$function$;

CREATE TRIGGER case_snapshot_v2_semantic_enrichment
BEFORE INSERT ON investigator.case_snapshot
FOR EACH ROW EXECUTE FUNCTION investigator.enrich_snapshot_v2_semantics();

-- A reasoning transaction holds the shared form of this case lock. Every
-- event-head or explicit invalidation mutation takes the exclusive form, so a
-- fresh READ COMMITTED gate query and its synchronous consumer observe one
-- currentness interval without relying on an old repeatable-read MVCC snapshot.
CREATE FUNCTION investigator.lock_reasoning_case_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(
    NEW.tenant_id::text || ':reasoning-currentness:' || NEW.case_id::text, 0
  ));
  RETURN NEW;
END
$function$;

CREATE TRIGGER investigation_event_reasoning_currentness_lock
BEFORE INSERT ON investigator.investigation_event
FOR EACH ROW EXECUTE FUNCTION investigator.lock_reasoning_case_mutation();

CREATE TRIGGER snapshot_invalidation_reasoning_currentness_lock
BEFORE INSERT ON investigator.case_snapshot_invalidation
FOR EACH ROW EXECUTE FUNCTION investigator.lock_reasoning_case_mutation();

CREATE FUNCTION investigator.create_snapshot_v2(
  requested_tenant_id uuid,
  requested_case_id uuid,
  expected_case_version bigint,
  requested_idempotency_key text
)
RETURNS TABLE(snapshot_id uuid, canonical_digest text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  created_snapshot_id uuid;
  existing_snapshot investigator.case_snapshot%ROWTYPE;
  existing_request investigator.case_snapshot_request%ROWTYPE;
  case_version bigint;
  correlation_reference text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login'
      USING ERRCODE = '42501';
  END IF;
  -- Serialize identical requests before their first lookup. The internal
  -- builder takes the same transaction lock; advisory locks are re-entrant.
  PERFORM pg_advisory_xact_lock(hashtextextended(
    requested_tenant_id::text || ':snapshot-v2:' || requested_idempotency_key, 0
  ));
  SELECT request.* INTO existing_request
  FROM investigator.case_snapshot_request request
  WHERE request.tenant_id = requested_tenant_id
    AND request.idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    SELECT snapshot.* INTO STRICT existing_snapshot
    FROM investigator.case_snapshot snapshot
    WHERE snapshot.tenant_id = requested_tenant_id
      AND snapshot.snapshot_id = existing_request.snapshot_id;
    IF existing_request.case_id = requested_case_id
       AND existing_request.expected_case_version = expected_case_version
       AND existing_snapshot.snapshot_schema_version = 2 THEN
      RETURN QUERY
        SELECT existing_snapshot.snapshot_id, existing_snapshot.canonical_digest;
      RETURN;
    END IF;
    RAISE EXCEPTION 'snapshot idempotency key conflicts with an existing request'
      USING ERRCODE = '23505';
  END IF;
  -- Serialize all same-case builders before checking for a post-trigger row.
  SELECT stored_case.case_version INTO case_version
  FROM investigator.investigation_case stored_case
  WHERE stored_case.tenant_id = requested_tenant_id
    AND stored_case.case_id = requested_case_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002';
  END IF;
  IF case_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale expected case version' USING ERRCODE = '40001';
  END IF;
  SELECT snapshot.* INTO existing_snapshot
  FROM investigator.case_snapshot snapshot
  WHERE snapshot.tenant_id = requested_tenant_id
    AND snapshot.case_id = requested_case_id
    AND snapshot.event_head_sequence = expected_case_version
    AND snapshot.snapshot_schema_version = 2;
  IF FOUND THEN
    INSERT INTO investigator.case_snapshot_request (
      tenant_id, idempotency_key, case_id, expected_case_version, snapshot_id,
      requested_by_actor_type, requested_by_actor_reference,
      authentication_reference, authorization_source, correlation_id
    ) VALUES (
      requested_tenant_id, requested_idempotency_key, requested_case_id,
      expected_case_version, existing_snapshot.snapshot_id, 'system',
      session_user, 'postgres-login:' || session_user,
      'investigator-tenant-role-binding', correlation_reference
    );
    RETURN QUERY
      SELECT existing_snapshot.snapshot_id, existing_snapshot.canonical_digest;
    RETURN;
  END IF;
  SELECT result.snapshot_id INTO STRICT created_snapshot_id
  FROM investigator.create_snapshot_v2_phase2_legacy(
    requested_tenant_id, requested_case_id, expected_case_version,
    requested_idempotency_key
  ) result;
  RETURN QUERY
    SELECT snapshot.snapshot_id, snapshot.canonical_digest
    FROM investigator.case_snapshot snapshot
    WHERE snapshot.tenant_id = requested_tenant_id
      AND snapshot.case_id = requested_case_id
      AND snapshot.snapshot_id = created_snapshot_id;
END
$function$;

REVOKE ALL ON TABLE investigator.investigation_evidence_semantics FROM PUBLIC;
REVOKE ALL ON TABLE evidence_authority.investigator_evidence_projection_change
  FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON evidence_authority.investigator_evidence_v1
  FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON TABLE investigator.investigation_evidence_semantics
  FROM olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.accept_evidence_reference(
  jsonb, uuid, bigint, uuid, text
) FROM olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.accept_evidence_reference_v2(
  jsonb, jsonb, uuid, bigint, uuid, text
) FROM PUBLIC, olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.create_snapshot_v2_phase2_legacy(
  uuid, uuid, bigint, text
) FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.enrich_snapshot_v2_semantics()
  FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.lock_reasoning_case_mutation()
  FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.create_snapshot_v2(
  uuid, uuid, bigint, text
) FROM PUBLIC, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION evidence_authority.canonical_reader_tenant_id()
  FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION evidence_authority.commit_investigator_evidence_projection(
  jsonb, bigint, text
) FROM PUBLIC, olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.current_canonical_authority_revision(
  uuid, uuid
) FROM PUBLIC, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.is_snapshot_structurally_current_v2(
  uuid, uuid
) FROM olin_investigator_evidence_authority;

GRANT SELECT ON investigator.investigation_evidence_semantics
  TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.accept_evidence_reference_v2(
  jsonb, jsonb, uuid, bigint, uuid, text
) TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.create_snapshot_v2(
  uuid, uuid, bigint, text
) TO olin_investigator_runtime;
GRANT USAGE ON SCHEMA evidence_authority
  TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION evidence_authority.commit_investigator_evidence_projection(
  jsonb, bigint, text
) TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.current_canonical_authority_revision(
  uuid, uuid
) TO olin_investigator_runtime;

COMMENT ON TABLE investigator.investigation_evidence_semantics IS
  'Immutable server-derived semantic lineage references; no artifact bodies, claims, weights, or scores';
COMMENT ON TABLE evidence_authority.investigator_evidence_projection_change IS
  'Append-only authoritative eligibility projection for Investigator reasoning; no artifact bodies';

RESET SESSION AUTHORIZATION;
COMMIT;
