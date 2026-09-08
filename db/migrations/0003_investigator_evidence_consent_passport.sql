-- Investigator V1 Phase 2: immutable canonical evidence/consent references.
-- This migration does not copy artifact bodies, consent receipts, or source trust.

BEGIN;

DO $precondition$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
    RAISE EXCEPTION 'Phase 2 migration requires a controlled superuser migration principal';
  END IF;
  IF to_regclass('investigator.case_snapshot') IS NULL
     OR to_regprocedure('investigator.is_snapshot_current(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'Investigator Phase 1 migration must be applied first';
  END IF;
END
$precondition$;

DO $role$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'olin_investigator_evidence_authority'
  ) THEN
    CREATE ROLE olin_investigator_evidence_authority
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
END
$role$;
ALTER ROLE olin_investigator_evidence_authority
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
DO $unexpected_membership$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_auth_members membership
    JOIN pg_roles member ON member.oid = membership.member
    JOIN pg_roles granted ON granted.oid = membership.roleid
    WHERE member.rolname = 'olin_investigator_evidence_authority'
       OR granted.rolname = 'olin_investigator_evidence_authority'
  ) THEN
    RAISE EXCEPTION 'Investigator evidence authority has unexpected role membership';
  END IF;
END
$unexpected_membership$;

REVOKE ALL ON ALL TABLES IN SCHEMA public
  FROM olin_investigator_evidence_authority;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public
  FROM olin_investigator_evidence_authority;
REVOKE CREATE ON SCHEMA public FROM olin_investigator_evidence_authority;
DO $legacy_effective_privileges$
DECLARE
  exposed_relation text;
  exposed_routine text;
  exposed_schema text;
BEGIN
  SELECT namespace.nspname INTO exposed_schema
    FROM pg_namespace namespace
    WHERE namespace.nspname NOT IN ('investigator', 'pg_catalog', 'information_schema')
      AND namespace.nspname !~ '^pg_(toast|temp)'
      AND has_schema_privilege(
        'olin_investigator_evidence_authority', namespace.oid, 'CREATE'
      )
    LIMIT 1;
  IF exposed_schema IS NOT NULL THEN
    RAISE EXCEPTION 'Evidence authority inherits CREATE on non-Investigator schema %',
      exposed_schema;
  END IF;
  SELECT format('%I.%I', namespace.nspname, relation.relname)
    INTO exposed_relation
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname NOT IN ('investigator', 'pg_catalog', 'information_schema')
      AND namespace.nspname !~ '^pg_toast'
      AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
      AND has_table_privilege(
        'olin_investigator_evidence_authority', relation.oid,
        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
      )
    LIMIT 1;
  IF exposed_relation IS NOT NULL THEN
    RAISE EXCEPTION 'Evidence authority inherits privilege on non-Investigator relation %',
      exposed_relation;
  END IF;
  SELECT format('%I.%I', namespace.nspname, routine.proname)
    INTO exposed_routine
    FROM pg_proc routine
    JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
    WHERE namespace.nspname NOT IN ('investigator', 'pg_catalog', 'information_schema')
      AND namespace.nspname !~ '^pg_(toast|temp)'
      AND has_function_privilege(
        'olin_investigator_evidence_authority', routine.oid, 'EXECUTE'
      )
    LIMIT 1;
  IF exposed_routine IS NOT NULL THEN
    RAISE EXCEPTION 'Evidence authority inherits EXECUTE on non-Investigator routine %',
      exposed_routine;
  END IF;
END
$legacy_effective_privileges$;

SET SESSION AUTHORIZATION olin_investigator_owner;

-- Existing v1 rows remain byte-for-byte unchanged; only future v2 rows are enabled.
ALTER TABLE investigator.case_snapshot
  DROP CONSTRAINT case_snapshot_snapshot_schema_version_check,
  ADD CONSTRAINT case_snapshot_snapshot_schema_version_check
    CHECK (snapshot_schema_version IN (1, 2));

CREATE TABLE investigator.investigation_evidence_reference (
  reference_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  subject_id text NOT NULL CHECK (length(btrim(subject_id)) BETWEEN 1 AND 240),
  subject_digest text NOT NULL CHECK (subject_digest ~ '^[0-9a-f]{64}$'),
  evidence_namespace text NOT NULL CHECK (
    length(btrim(evidence_namespace)) BETWEEN 1 AND 120
  ),
  evidence_id text NOT NULL CHECK (length(btrim(evidence_id)) BETWEEN 1 AND 240),
  evidence_version text NOT NULL CHECK (
    length(btrim(evidence_version)) BETWEEN 1 AND 120
  ),
  artifact_digest text NOT NULL CHECK (artifact_digest ~ '^[0-9a-f]{64}$'),
  authority_digest text NOT NULL CHECK (authority_digest ~ '^[0-9a-f]{64}$'),
  evidence_class text NOT NULL CHECK (evidence_class IN (
    'VERIFIED_FACT', 'EXTERNAL_EVIDENCE', 'MERCHANT_SUPPLIED_ARTIFACT',
    'EXPERIMENTAL_OBSERVATION'
  )),
  lifecycle text NOT NULL CHECK (lifecycle = 'ACCEPTED'),
  verification_status text NOT NULL CHECK (verification_status IN (
    'UNVERIFIED', 'VERIFIED_FOR_PROPOSITION'
  )),
  proposition_type text CHECK (
    proposition_type IS NULL OR octet_length(proposition_type) BETWEEN 1 AND 120
  ),
  proposition_schema_version integer,
  proposition_value text CHECK (
    proposition_value IS NULL OR octet_length(proposition_value) BETWEEN 1 AND 512
  ),
  proposition_unit text CHECK (
    proposition_unit IS NULL OR octet_length(proposition_unit) BETWEEN 1 AND 64
  ),
  verification_method text CHECK (
    verification_method IS NULL OR octet_length(verification_method) BETWEEN 1 AND 160
  ),
  period_start timestamptz,
  period_end timestamptz,
  observed_at timestamptz NOT NULL,
  evidence_expires_at timestamptz NOT NULL,
  source_id text NOT NULL CHECK (length(btrim(source_id)) BETWEEN 1 AND 120),
  issuer_id text NOT NULL CHECK (length(btrim(issuer_id)) BETWEEN 1 AND 120),
  acquisition_method text NOT NULL CHECK (
    length(btrim(acquisition_method)) BETWEEN 1 AND 120
  ),
  source_class text NOT NULL CHECK (length(btrim(source_class)) BETWEEN 1 AND 120),
  source_attestation_id text NOT NULL CHECK (
    length(btrim(source_attestation_id)) BETWEEN 1 AND 240
  ),
  source_attestation_version text NOT NULL CHECK (
    length(btrim(source_attestation_version)) BETWEEN 1 AND 120
  ),
  source_registry_digest text NOT NULL CHECK (
    source_registry_digest ~ '^[0-9a-f]{64}$'
  ),
  source_valid_until timestamptz NOT NULL,
  consent_namespace text NOT NULL CHECK (
    length(btrim(consent_namespace)) BETWEEN 1 AND 120
  ),
  consent_id text NOT NULL CHECK (length(btrim(consent_id)) BETWEEN 1 AND 240),
  consent_version text NOT NULL CHECK (
    length(btrim(consent_version)) BETWEEN 1 AND 120
  ),
  consent_purpose text NOT NULL CHECK (
    length(btrim(consent_purpose)) BETWEEN 1 AND 120
  ),
  consent_data_class text NOT NULL CHECK (
    length(btrim(consent_data_class)) BETWEEN 1 AND 120
  ),
  consent_use_scope text NOT NULL CHECK (
    length(btrim(consent_use_scope)) BETWEEN 1 AND 240
  ),
  consent_expires_at timestamptz NOT NULL,
  retention_until timestamptz NOT NULL,
  integrity_reference text NOT NULL CHECK (
    length(btrim(integrity_reference)) BETWEEN 1 AND 240
  ),
  resolver_version text NOT NULL CHECK (
    resolver_version = 'investigator-evidence-resolver-1.0'
  ),
  accepted_at timestamptz NOT NULL,
  acceptance_snapshot_id uuid NOT NULL,
  acceptance_event_id uuid NOT NULL,
  acceptance_request_digest text NOT NULL CHECK (
    acceptance_request_digest ~ '^[0-9a-f]{64}$'
  ),
  supersedes_reference_id uuid,
  CONSTRAINT investigation_evidence_reference_case_fk
    FOREIGN KEY (tenant_id, case_id)
    REFERENCES investigator.investigation_case (tenant_id, case_id),
  CONSTRAINT investigation_evidence_reference_event_fk
    FOREIGN KEY (tenant_id, case_id, acceptance_event_id)
    REFERENCES investigator.investigation_event (tenant_id, case_id, event_id),
  CONSTRAINT investigation_evidence_reference_snapshot_fk
    FOREIGN KEY (tenant_id, case_id, acceptance_snapshot_id)
    REFERENCES investigator.case_snapshot (tenant_id, case_id, snapshot_id),
  CONSTRAINT investigation_evidence_reference_tenant_case_reference_unique UNIQUE (
    tenant_id, case_id, reference_id
  ),
  CONSTRAINT investigation_evidence_reference_supersedes_fk
    FOREIGN KEY (tenant_id, case_id, supersedes_reference_id)
    REFERENCES investigator.investigation_evidence_reference (
      tenant_id, case_id, reference_id
    ),
  CONSTRAINT investigation_evidence_reference_canonical_unique UNIQUE (
    tenant_id, case_id, evidence_namespace, evidence_id, evidence_version
  ),
  CONSTRAINT investigation_evidence_reference_supersession_unique UNIQUE (
    tenant_id, case_id, supersedes_reference_id
  ),
  CONSTRAINT investigation_evidence_reference_proposition_check CHECK (
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
    )
  ),
  CONSTRAINT investigation_evidence_reference_period_check CHECK (
    period_start IS NULL OR period_end IS NULL OR period_start <= period_end
  ),
  CONSTRAINT investigation_evidence_reference_validity_check CHECK (
    source_valid_until > accepted_at
    AND consent_expires_at > accepted_at
    AND retention_until > accepted_at
    AND evidence_expires_at > accepted_at
    AND observed_at <= accepted_at + interval '5 minutes'
    AND (period_end IS NULL OR period_end <= accepted_at + interval '5 minutes')
  )
);

CREATE INDEX investigation_evidence_reference_case_idx
  ON investigator.investigation_evidence_reference (tenant_id, case_id, accepted_at);
CREATE INDEX investigation_evidence_reference_consent_idx
  ON investigator.investigation_evidence_reference (
    tenant_id, consent_namespace, consent_id
  );
CREATE UNIQUE INDEX investigation_evidence_reference_root_artifact_unique
  ON investigator.investigation_evidence_reference (
    tenant_id, case_id, artifact_digest
  ) WHERE supersedes_reference_id IS NULL;

ALTER TABLE investigator.investigation_evidence_reference ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_evidence_reference FORCE ROW LEVEL SECURITY;
CREATE POLICY investigation_evidence_reference_tenant_policy
  ON investigator.investigation_evidence_reference
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner,
     olin_investigator_evidence_authority
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE TRIGGER investigation_evidence_reference_immutable
BEFORE UPDATE OR DELETE ON investigator.investigation_evidence_reference
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();
CREATE TRIGGER investigation_evidence_reference_no_truncate
BEFORE TRUNCATE ON investigator.investigation_evidence_reference
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

-- Support separate tenant-bound evidence-authority logins without widening the
-- Phase 1 runtime login pattern.
CREATE OR REPLACE FUNCTION investigator.session_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $function$
DECLARE
  compact_id text;
BEGIN
  compact_id := coalesce(
    substring(session_user FROM '^olin_inv_t_([0-9a-f]{32})$'),
    substring(session_user FROM '^olin_evidence_t_([0-9a-f]{32})$')
  );
  IF compact_id IS NULL THEN RETURN NULL; END IF;
  RETURN (
    substr(compact_id, 1, 8) || '-' || substr(compact_id, 9, 4) || '-' ||
    substr(compact_id, 13, 4) || '-' || substr(compact_id, 17, 4) || '-' ||
    substr(compact_id, 21, 12)
  )::uuid;
END
$function$;

CREATE FUNCTION investigator.append_evidence_authority_event(
  requested_tenant_id uuid,
  requested_case_id uuid,
  expected_case_version bigint,
  requested_event_id uuid,
  requested_event_type text,
  requested_payload jsonb,
  requested_occurred_at timestamptz,
  requested_idempotency_key text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  case_version bigint;
  parent_id uuid;
  next_sequence bigint;
  next_evidence_state bigint;
  recorded_time timestamptz := statement_timestamp();
  payload_digest text;
  event_digest text;
  existing investigator.investigation_event%ROWTYPE;
  actor_reference text := session_user;
  correlation_reference text := 'evidence-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
BEGIN
  IF NOT pg_has_role(session_user, 'olin_investigator_evidence_authority', 'member')
     OR NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant-bound evidence authority is required' USING ERRCODE = '42501';
  END IF;
  IF requested_event_type NOT IN (
    'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
  ) THEN
    RAISE EXCEPTION 'event type is not an evidence-authority event' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'EVIDENCE_ACCEPTED' AND (
    (SELECT count(*) FROM jsonb_object_keys(requested_payload)) <> 2
    OR NOT requested_payload ?& ARRAY['reference_id', 'evidence_state_version']
  ) THEN
    RAISE EXCEPTION 'EVIDENCE_ACCEPTED payload is not schema-exact' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'EVIDENCE_BECAME_UNUSABLE' AND (
    (SELECT count(*) FROM jsonb_object_keys(requested_payload)) <> 4
    OR NOT requested_payload ?& ARRAY[
      'reference_id', 'evidence_state_version', 'reason_code', 'reason_reference'
    ]
  ) THEN
    RAISE EXCEPTION 'EVIDENCE_BECAME_UNUSABLE payload is not schema-exact' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'EVIDENCE_BECAME_UNUSABLE'
     AND requested_payload->>'reason_code' NOT IN (
       'CONSENT_MISSING', 'CONSENT_WITHDRAWN', 'CONSENT_EXPIRED',
       'CONSENT_OUT_OF_SCOPE', 'EVIDENCE_QUARANTINED', 'EVIDENCE_DISPUTED',
       'EVIDENCE_SUPERSEDED', 'EVIDENCE_REVOKED', 'EVIDENCE_EXPIRED',
       'SOURCE_NOT_TRUSTED', 'SOURCE_ATTESTATION_CHANGED',
       'SOURCE_ATTESTATION_EXPIRED', 'TENANT_MISMATCH', 'CASE_MISMATCH',
       'SUBJECT_MISMATCH', 'INTEGRITY_FAILURE', 'AUTHORITY_REFERENCE_CHANGED',
       'EVIDENCE_NOT_YET_OBSERVED'
     ) THEN
    RAISE EXCEPTION 'evidence unusable reason is unknown' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'CONSENT_STATE_CHANGED' AND (
    (SELECT count(*) FROM jsonb_object_keys(requested_payload)) <> 5
    OR NOT requested_payload ?& ARRAY[
      'consent_namespace', 'consent_id', 'evidence_state_version', 'status',
      'reason_reference'
    ]
  ) THEN
    RAISE EXCEPTION 'CONSENT_STATE_CHANGED payload is not schema-exact' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'CONSENT_STATE_CHANGED'
     AND requested_payload->>'status' NOT IN (
       'ACTIVE', 'WITHDRAWN', 'EXPIRED', 'SUPERSEDED'
     ) THEN
    RAISE EXCEPTION 'consent state is unknown' USING ERRCODE = '22023';
  END IF;
  IF coalesce((requested_payload->>'evidence_state_version')::bigint, 0) < 1 THEN
    RAISE EXCEPTION 'evidence_state_version must be positive' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type IN ('EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE') THEN
    PERFORM (requested_payload->>'reference_id')::uuid;
  END IF;
  IF requested_event_type = 'EVIDENCE_BECAME_UNUSABLE' AND (
    coalesce(length(btrim(requested_payload->>'reason_reference')), 0)
      NOT BETWEEN 1 AND 240
  ) THEN
    RAISE EXCEPTION 'reason_reference is invalid' USING ERRCODE = '22023';
  END IF;
  IF requested_event_type = 'CONSENT_STATE_CHANGED' AND (
    coalesce(length(btrim(requested_payload->>'consent_namespace')), 0)
      NOT BETWEEN 1 AND 120
    OR coalesce(length(btrim(requested_payload->>'consent_id')), 0)
      NOT BETWEEN 1 AND 240
    OR coalesce(length(btrim(requested_payload->>'reason_reference')), 0)
      NOT BETWEEN 1 AND 240
  ) THEN
    RAISE EXCEPTION 'consent state reference is invalid' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(
    hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0)
  );
  SELECT event.* INTO existing FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id
      AND event.idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    IF existing.case_id = requested_case_id
       AND existing.event_id = requested_event_id
       AND existing.event_type = requested_event_type
       AND existing.payload = requested_payload
       AND existing.occurred_at = requested_occurred_at THEN
      RETURN existing.event_sequence;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing event'
      USING ERRCODE = '23505';
  END IF;
  SELECT stored_case.case_version INTO case_version
    FROM investigator.investigation_case stored_case
    WHERE stored_case.tenant_id = requested_tenant_id
      AND stored_case.case_id = requested_case_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002'; END IF;
  IF case_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale expected case version' USING ERRCODE = '40001';
  END IF;
  SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0) + 1
    INTO next_evidence_state FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id
      AND event.case_id = requested_case_id
      AND event.event_type IN (
        'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
      );
  IF (requested_payload->>'evidence_state_version')::bigint <> next_evidence_state THEN
    RAISE EXCEPTION 'evidence_state_version is not the next authoritative version'
      USING ERRCODE = '40001';
  END IF;
  SELECT event.event_id INTO parent_id FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_sequence = case_version;
  next_sequence := case_version + 1;
  payload_digest := encode(sha256(convert_to(
    investigator.canonical_json(requested_payload), 'UTF8'
  )), 'hex');
  event_digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'actor', jsonb_build_object(
      'actor_type', 'system', 'actor_reference', actor_reference,
      'tenant_id', requested_tenant_id::text, 'case_id', requested_case_id::text,
      'authentication_reference', 'postgres-login:' || session_user,
      'authorization_source', 'canonical-evidence-authority-role',
      'correlation_id', correlation_reference,
      'created_at', to_char(transaction_timestamp() AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'case_id', requested_case_id::text, 'causation_event_id', NULL,
    'event_id', requested_event_id::text, 'event_type', requested_event_type,
    'idempotency_key', requested_idempotency_key,
    'occurred_at', to_char(requested_occurred_at AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'parent_event_id', parent_id::text, 'payload', requested_payload,
    'recorded_at', to_char(recorded_time AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'schema_version', 1, 'sequence', next_sequence,
    'tenant_id', requested_tenant_id::text
  )), 'UTF8')), 'hex');
  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at, recorded_at,
    actor_type, actor_id, workload_id, actor_case_id, authentication_reference,
    authorization_source, correlation_id, actor_context_created_at, payload,
    payload_schema_version, idempotency_key, parent_event_id, payload_digest,
    integrity_metadata, event_digest
  ) VALUES (
    requested_event_id, requested_tenant_id, requested_case_id, next_sequence,
    requested_event_type, requested_occurred_at, recorded_time, 'system', actor_reference,
    session_user, requested_case_id, 'postgres-login:' || session_user,
    'canonical-evidence-authority-role', correlation_reference,
    transaction_timestamp(), requested_payload, 1, requested_idempotency_key,
    parent_id, payload_digest, '{}'::jsonb, event_digest
  );
  UPDATE investigator.investigation_case stored_case
    SET case_version = next_sequence, updated_at = recorded_time
    WHERE stored_case.tenant_id = requested_tenant_id
      AND stored_case.case_id = requested_case_id;
  RETURN next_sequence;
END
$function$;

CREATE FUNCTION investigator.mark_evidence_unusable(
  requested_tenant_id uuid,
  requested_case_id uuid,
  requested_current_snapshot_id uuid,
  requested_reference_id uuid,
  expected_case_version bigint,
  requested_event_id uuid,
  requested_reason_code text,
  requested_reason_reference text,
  requested_occurred_at timestamptz,
  requested_idempotency_key text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  state_version bigint;
BEGIN
  IF NOT pg_has_role(
    session_user, 'olin_investigator_evidence_authority', 'member'
  ) OR NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant-bound evidence authority is required'
      USING ERRCODE = '42501';
  END IF;
  IF requested_occurred_at < statement_timestamp() - interval '5 minutes'
     OR requested_occurred_at > statement_timestamp() + interval '5 minutes' THEN
    RAISE EXCEPTION 'state event time is outside server clock tolerance'
      USING ERRCODE = '22023';
  END IF;
  IF NOT investigator.is_snapshot_current(
    requested_tenant_id, requested_current_snapshot_id
  ) OR NOT EXISTS (
    SELECT 1 FROM investigator.case_snapshot snapshot
    WHERE snapshot.tenant_id = requested_tenant_id
      AND snapshot.case_id = requested_case_id
      AND snapshot.snapshot_id = requested_current_snapshot_id
  ) THEN
    RAISE EXCEPTION 'a current tenant/case CaseSnapshot is required'
      USING ERRCODE = '40001';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = requested_tenant_id AND ref.case_id = requested_case_id
      AND ref.reference_id = requested_reference_id
  ) THEN
    RAISE EXCEPTION 'evidence reference was not found' USING ERRCODE = 'P0002';
  END IF;
  SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0) + 1
    INTO state_version FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_type IN (
        'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
      );
  RETURN investigator.append_evidence_authority_event(
    requested_tenant_id, requested_case_id, expected_case_version,
    requested_event_id, 'EVIDENCE_BECAME_UNUSABLE', jsonb_build_object(
      'reference_id', requested_reference_id::text,
      'evidence_state_version', state_version,
      'reason_code', requested_reason_code,
      'reason_reference', requested_reason_reference
    ), requested_occurred_at, requested_idempotency_key
  );
END
$function$;

CREATE FUNCTION investigator.record_consent_state_change(
  requested_tenant_id uuid,
  requested_case_id uuid,
  requested_current_snapshot_id uuid,
  requested_consent_namespace text,
  requested_consent_id text,
  requested_status text,
  expected_case_version bigint,
  requested_event_id uuid,
  requested_reason_reference text,
  requested_occurred_at timestamptz,
  requested_idempotency_key text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  state_version bigint;
BEGIN
  IF NOT pg_has_role(
    session_user, 'olin_investigator_evidence_authority', 'member'
  ) OR NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant-bound evidence authority is required'
      USING ERRCODE = '42501';
  END IF;
  IF requested_occurred_at < statement_timestamp() - interval '5 minutes'
     OR requested_occurred_at > statement_timestamp() + interval '5 minutes' THEN
    RAISE EXCEPTION 'consent event time is outside server clock tolerance'
      USING ERRCODE = '22023';
  END IF;
  IF requested_status NOT IN ('WITHDRAWN', 'EXPIRED', 'SUPERSEDED') THEN
    RAISE EXCEPTION 'only a canonical loss of consent may be recorded'
      USING ERRCODE = '22023';
  END IF;
  IF NOT investigator.is_snapshot_current(
    requested_tenant_id, requested_current_snapshot_id
  ) OR NOT EXISTS (
    SELECT 1 FROM investigator.case_snapshot snapshot
    WHERE snapshot.tenant_id = requested_tenant_id
      AND snapshot.case_id = requested_case_id
      AND snapshot.snapshot_id = requested_current_snapshot_id
  ) THEN
    RAISE EXCEPTION 'a current tenant/case CaseSnapshot is required'
      USING ERRCODE = '40001';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = requested_tenant_id AND ref.case_id = requested_case_id
      AND ref.consent_namespace = requested_consent_namespace
      AND ref.consent_id = requested_consent_id
  ) THEN
    RAISE EXCEPTION 'consent does not authorize any case evidence'
      USING ERRCODE = 'P0002';
  END IF;
  SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0) + 1
    INTO state_version FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_type IN (
        'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
      );
  RETURN investigator.append_evidence_authority_event(
    requested_tenant_id, requested_case_id, expected_case_version,
    requested_event_id, 'CONSENT_STATE_CHANGED', jsonb_build_object(
      'consent_namespace', requested_consent_namespace,
      'consent_id', requested_consent_id,
      'evidence_state_version', state_version,
      'status', requested_status,
      'reason_reference', requested_reason_reference
    ), requested_occurred_at, requested_idempotency_key
  );
END
$function$;

CREATE FUNCTION investigator.accept_evidence_reference(
  requested_reference jsonb,
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
  occurred timestamptz := (requested_reference->>'accepted_at')::timestamptz;
  request_digest text := encode(sha256(convert_to(
    investigator.canonical_json(requested_reference), 'UTF8'
  )), 'hex');
  state_version bigint;
  existing investigator.investigation_evidence_reference%ROWTYPE;
  prior investigator.investigation_evidence_reference%ROWTYPE;
  existing_event investigator.investigation_event%ROWTYPE;
BEGIN
  IF NOT pg_has_role(
    session_user, 'olin_investigator_evidence_authority', 'member'
  ) OR NOT investigator.tenant_access_allowed(tenant) THEN
    RAISE EXCEPTION 'tenant-bound evidence authority is required'
      USING ERRCODE = '42501';
  END IF;
  IF jsonb_typeof(requested_reference) <> 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(requested_reference)) <> 46
     OR NOT requested_reference ?& ARRAY[
       'tenant_id', 'case_id', 'reference_id', 'subject_id', 'subject_digest',
       'evidence_namespace', 'evidence_id', 'evidence_version', 'artifact_digest',
       'authority_digest', 'evidence_class', 'lifecycle', 'verification_status', 'proposition_type',
       'proposition_schema_version', 'proposition_value', 'proposition_unit',
       'verification_method',
       'period_start', 'period_end', 'observed_at', 'evidence_expires_at',
       'source_id', 'issuer_id', 'acquisition_method', 'source_class',
       'source_attestation_id', 'source_attestation_version',
       'source_registry_digest', 'source_valid_until',
       'production_qualified_source', 'source_allows_proposition',
       'consent_namespace', 'consent_id', 'consent_version', 'consent_purpose',
       'consent_data_class', 'consent_use_scope', 'consent_status',
       'consent_expires_at', 'retention_until', 'integrity_valid',
       'integrity_reference', 'resolver_version', 'accepted_at',
       'supersedes_reference_id'
     ] THEN
    RAISE EXCEPTION 'evidence reference envelope is not schema-exact' USING ERRCODE = '22023';
  END IF;
  IF octet_length(requested_reference::text) > 16384 THEN
    RAISE EXCEPTION 'evidence reference envelope exceeds 16384 bytes'
      USING ERRCODE = '22023';
  END IF;
  IF requested_reference ?| ARRAY[
    'verified', 'trusted', 'authoritative', 'issuer_validated', 'source_verified',
    'official', 'validated'
  ] THEN
    RAISE EXCEPTION 'caller trust labels are forbidden' USING ERRCODE = '22023';
  END IF;
  IF requested_reference->>'production_qualified_source' <> 'true'
     OR requested_reference->>'source_allows_proposition' <> 'true'
     OR requested_reference->>'integrity_valid' <> 'true'
     OR requested_reference->>'consent_status' <> 'ACTIVE'
     OR requested_reference->>'consent_use_scope' <> 'case_evidence_analysis'
     OR requested_reference->>'lifecycle' <> 'ACCEPTED'
     OR occurred < statement_timestamp() - interval '5 minutes'
     OR occurred > statement_timestamp() + interval '5 minutes'
     OR nullif(requested_reference->>'evidence_expires_at', '') IS NULL
     OR (requested_reference->>'evidence_expires_at')::timestamptz <= occurred
     OR (requested_reference->>'observed_at')::timestamptz
          > occurred + interval '5 minutes'
     OR (
       nullif(requested_reference->>'period_end', '') IS NOT NULL
       AND (requested_reference->>'period_end')::timestamptz
             > occurred + interval '5 minutes'
     )
     OR (
       requested_reference->>'verification_status' = 'VERIFIED_FOR_PROPOSITION'
       AND requested_reference->>'source_class' NOT IN (
         'accredited_data_provider', 'government_registry',
         'independent_auditor', 'regulated_financial_institution'
       )
     )
     OR requested_reference->>'evidence_class' = 'EXPERIMENTAL_OBSERVATION'
     OR lower(concat_ws(' ',
       requested_reference->>'source_id', requested_reference->>'issuer_id',
       requested_reference->>'source_class',
       requested_reference->>'source_attestation_id'
     )) ~ '(example|placeholder|synthetic|demo)'
     OR requested_reference->>'proposition_type' = '*' THEN
    RAISE EXCEPTION 'canonical evidence authority did not resolve usable production evidence'
      USING ERRCODE = '42501';
  END IF;
  IF jsonb_typeof(requested_reference->'production_qualified_source') <> 'boolean'
     OR jsonb_typeof(requested_reference->'source_allows_proposition') <> 'boolean'
     OR jsonb_typeof(requested_reference->'integrity_valid') <> 'boolean' THEN
    RAISE EXCEPTION 'authority decisions must be JSON booleans'
      USING ERRCODE = '22023';
  END IF;
  IF requested_reference->>'authority_digest' !~ '^[0-9a-f]{64}$'
     OR octet_length(coalesce(requested_reference->>'proposition_type', '')) > 120
     OR octet_length(coalesce(requested_reference->>'proposition_value', '')) > 512
     OR octet_length(coalesce(requested_reference->>'proposition_unit', '')) > 64
     OR octet_length(coalesce(requested_reference->>'verification_method', '')) > 160
     OR (
       requested_reference->>'verification_status' = 'VERIFIED_FOR_PROPOSITION'
       AND (
         nullif(requested_reference->>'period_start', '') IS NULL
         OR nullif(requested_reference->>'period_end', '') IS NULL
       )
     ) THEN
    RAISE EXCEPTION 'authority reference fields exceed or violate the closed schema'
      USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    tenant::text || ':evidence-accept:' || requested_idempotency_key, 0
  ));
  SELECT * INTO existing FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
      AND ref.reference_id = reference_identifier;
  IF FOUND THEN
    SELECT event.* INTO STRICT existing_event
      FROM investigator.investigation_event event
      WHERE event.tenant_id = existing.tenant_id
        AND event.case_id = existing.case_id
        AND event.event_id = existing.acceptance_event_id;
    IF existing.acceptance_request_digest = request_digest
       AND existing.acceptance_snapshot_id = requested_current_snapshot_id
       AND existing.acceptance_event_id = requested_event_id
       AND existing_event.idempotency_key = requested_idempotency_key
       AND existing_event.event_sequence = expected_case_version + 1 THEN
      RETURN reference_identifier;
    END IF;
    RAISE EXCEPTION 'reference replay conflicts with immutable history' USING ERRCODE = '23505';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    tenant::text || ':' || case_identifier::text || ':artifact:'
      || (requested_reference->>'artifact_digest'), 0
  ));
  IF EXISTS (
    SELECT 1 FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
      AND ref.artifact_digest = requested_reference->>'artifact_digest'
      AND (
        nullif(requested_reference->>'supersedes_reference_id', '') IS NULL
        OR ref.reference_id <>
          (requested_reference->>'supersedes_reference_id')::uuid
      )
  ) THEN
    RAISE EXCEPTION 'artifact content is already referenced by another lineage'
      USING ERRCODE = '23505';
  END IF;
  IF NOT investigator.is_snapshot_current(tenant, requested_current_snapshot_id)
     OR NOT EXISTS (
       SELECT 1 FROM investigator.case_snapshot snapshot
       WHERE snapshot.tenant_id = tenant AND snapshot.case_id = case_identifier
         AND snapshot.snapshot_id = requested_current_snapshot_id
     ) THEN
    RAISE EXCEPTION 'a current tenant/case CaseSnapshot is required'
      USING ERRCODE = '40001';
  END IF;
  IF nullif(requested_reference->>'supersedes_reference_id', '') IS NOT NULL THEN
    SELECT ref.* INTO prior FROM investigator.investigation_evidence_reference ref
      WHERE ref.tenant_id = tenant AND ref.case_id = case_identifier
        AND ref.reference_id = (
          requested_reference->>'supersedes_reference_id'
        )::uuid;
    IF NOT FOUND
       OR prior.evidence_namespace <> requested_reference->>'evidence_namespace'
       OR prior.evidence_id <> requested_reference->>'evidence_id'
       OR prior.evidence_version = requested_reference->>'evidence_version' THEN
      RAISE EXCEPTION 'correction must append a new version of the same evidence'
        USING ERRCODE = '22023';
    END IF;
  END IF;
  SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0) + 1
    INTO state_version FROM investigator.investigation_event event
    WHERE event.tenant_id = tenant AND event.case_id = case_identifier
      AND event.event_type IN (
        'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
      );
  PERFORM investigator.append_evidence_authority_event(
    tenant, case_identifier, expected_case_version, requested_event_id,
    'EVIDENCE_ACCEPTED', jsonb_build_object(
      'reference_id', reference_identifier::text,
      'evidence_state_version', state_version
    ), occurred, requested_idempotency_key
  );
  INSERT INTO investigator.investigation_evidence_reference (
    reference_id, tenant_id, case_id, subject_id, subject_digest,
    evidence_namespace, evidence_id, evidence_version, artifact_digest,
    authority_digest, evidence_class, lifecycle, verification_status, proposition_type,
    proposition_schema_version, proposition_value, proposition_unit,
    verification_method,
    period_start, period_end, observed_at, evidence_expires_at, source_id,
    issuer_id, acquisition_method, source_class, source_attestation_id,
    source_attestation_version, source_registry_digest, source_valid_until,
    consent_namespace, consent_id, consent_version, consent_purpose,
    consent_data_class, consent_use_scope, consent_expires_at, retention_until,
    integrity_reference, resolver_version, accepted_at, acceptance_event_id,
    acceptance_snapshot_id, acceptance_request_digest, supersedes_reference_id
  ) VALUES (
    reference_identifier, tenant, case_identifier, requested_reference->>'subject_id',
    requested_reference->>'subject_digest', requested_reference->>'evidence_namespace',
    requested_reference->>'evidence_id', requested_reference->>'evidence_version',
    requested_reference->>'artifact_digest', requested_reference->>'authority_digest',
    requested_reference->>'evidence_class', requested_reference->>'lifecycle',
    requested_reference->>'verification_status',
    nullif(requested_reference->>'proposition_type', ''),
    nullif(requested_reference->>'proposition_schema_version', '')::integer,
    nullif(requested_reference->>'proposition_value', ''),
    nullif(requested_reference->>'proposition_unit', ''),
    nullif(requested_reference->>'verification_method', ''),
    nullif(requested_reference->>'period_start', '')::timestamptz,
    nullif(requested_reference->>'period_end', '')::timestamptz,
    (requested_reference->>'observed_at')::timestamptz,
    nullif(requested_reference->>'evidence_expires_at', '')::timestamptz,
    requested_reference->>'source_id', requested_reference->>'issuer_id',
    requested_reference->>'acquisition_method', requested_reference->>'source_class',
    requested_reference->>'source_attestation_id',
    requested_reference->>'source_attestation_version',
    requested_reference->>'source_registry_digest',
    (requested_reference->>'source_valid_until')::timestamptz,
    requested_reference->>'consent_namespace', requested_reference->>'consent_id',
    requested_reference->>'consent_version', requested_reference->>'consent_purpose',
    requested_reference->>'consent_data_class', requested_reference->>'consent_use_scope',
    (requested_reference->>'consent_expires_at')::timestamptz,
    (requested_reference->>'retention_until')::timestamptz,
    requested_reference->>'integrity_reference', requested_reference->>'resolver_version',
    occurred, requested_event_id, requested_current_snapshot_id, request_digest,
    nullif(requested_reference->>'supersedes_reference_id', '')::uuid
  );
  RETURN reference_identifier;
END
$function$;

-- Snapshot v2 stores only bounded references. Canonical status is re-resolved by
-- the application adapter; this database function additionally enforces local
-- event-head, expiry, and append-only state transitions.
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
  case_row investigator.investigation_case%ROWTYPE;
  first_event investigator.investigation_event%ROWTYPE;
  head_event investigator.investigation_event%ROWTYPE;
  snapshot_payload jsonb;
  snapshot_bytes bytea;
  snapshot_digest text;
  stream_digest text;
  evidence_digest text;
  evidence_version bigint;
  accepted_refs jsonb;
  unusable_refs jsonb;
  consent_refs jsonb;
  source_refs jsonb;
  existing_snapshot investigator.case_snapshot%ROWTYPE;
  existing_request investigator.case_snapshot_request%ROWTYPE;
  new_snapshot_id uuid := gen_random_uuid();
  recorded_time timestamptz := statement_timestamp();
  correlation_reference text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login'
      USING ERRCODE = '42501';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    requested_tenant_id::text || ':snapshot-v2:' || requested_idempotency_key, 0
  ));
  SELECT request.* INTO existing_request FROM investigator.case_snapshot_request request
    WHERE request.tenant_id = requested_tenant_id
      AND request.idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    SELECT snapshot.* INTO STRICT existing_snapshot FROM investigator.case_snapshot snapshot
      WHERE snapshot.tenant_id = requested_tenant_id
        AND snapshot.snapshot_id = existing_request.snapshot_id;
    IF existing_request.case_id = requested_case_id
       AND existing_request.expected_case_version = expected_case_version
       AND existing_snapshot.snapshot_schema_version = 2 THEN
      RETURN QUERY SELECT existing_snapshot.snapshot_id, existing_snapshot.canonical_digest;
      RETURN;
    END IF;
    RAISE EXCEPTION 'snapshot idempotency key conflicts with an existing request'
      USING ERRCODE = '23505';
  END IF;
  SELECT stored_case.* INTO case_row FROM investigator.investigation_case stored_case
    WHERE stored_case.tenant_id = requested_tenant_id
      AND stored_case.case_id = requested_case_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002'; END IF;
  IF case_row.case_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale expected case version' USING ERRCODE = '40001';
  END IF;
  SELECT event.* INTO first_event FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_sequence = 1;
  SELECT event.* INTO head_event FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_sequence = expected_case_version;
  IF first_event.event_type <> 'CASE_CREATED' OR EXISTS (
    SELECT 1 FROM investigator.investigation_event event
    LEFT JOIN investigator.investigation_event parent
      ON parent.tenant_id = event.tenant_id AND parent.case_id = event.case_id
     AND parent.event_sequence = event.event_sequence - 1
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND (
        NOT investigator.event_integrity_valid(event)
        OR (event.event_sequence > 1 AND event.parent_event_id IS DISTINCT FROM parent.event_id)
      )
  ) THEN
    RAISE EXCEPTION 'event stream violates integrity or sequence invariants'
      USING ERRCODE = '22000';
  END IF;
  SELECT encode(sha256(convert_to(investigator.canonical_json(jsonb_agg(
      event.event_digest ORDER BY event.event_sequence
    )), 'UTF8')), 'hex') INTO stream_digest
    FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id;
  SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0)
    INTO evidence_version FROM investigator.investigation_event event
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND event.event_type IN (
        'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE', 'CONSENT_STATE_CHANGED'
      );
  WITH state AS (
    SELECT ref.*, coalesce(
      (
        SELECT 'EVIDENCE_SUPERSEDED'
        FROM investigator.investigation_evidence_reference successor
        WHERE successor.tenant_id = ref.tenant_id
          AND successor.case_id = ref.case_id
          AND successor.supersedes_reference_id = ref.reference_id
        LIMIT 1
      ),
      (
        SELECT event.payload->>'reason_code'
        FROM investigator.investigation_event event
        WHERE event.tenant_id = ref.tenant_id AND event.case_id = ref.case_id
          AND event.event_type = 'EVIDENCE_BECAME_UNUSABLE'
          AND event.payload->>'reference_id' = ref.reference_id::text
        ORDER BY event.event_sequence DESC LIMIT 1
      ),
      (
        SELECT CASE event.payload->>'status'
          WHEN 'WITHDRAWN' THEN 'CONSENT_WITHDRAWN'
          WHEN 'EXPIRED' THEN 'CONSENT_EXPIRED'
          WHEN 'SUPERSEDED' THEN 'CONSENT_OUT_OF_SCOPE'
        END
        FROM investigator.investigation_event event
        WHERE event.tenant_id = ref.tenant_id AND event.case_id = ref.case_id
          AND event.event_type = 'CONSENT_STATE_CHANGED'
          AND event.payload->>'consent_namespace' = ref.consent_namespace
          AND event.payload->>'consent_id' = ref.consent_id
        ORDER BY event.event_sequence DESC LIMIT 1
      ),
      CASE
        WHEN ref.source_valid_until <= recorded_time
          THEN 'SOURCE_ATTESTATION_EXPIRED'
        WHEN ref.consent_expires_at <= recorded_time
          OR ref.retention_until <= recorded_time THEN 'CONSENT_EXPIRED'
        WHEN ref.evidence_expires_at IS NOT NULL
          AND ref.evidence_expires_at <= recorded_time THEN 'EVIDENCE_EXPIRED'
      END
    ) AS unusable_reason
    FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = requested_tenant_id AND ref.case_id = requested_case_id
  ), classified AS (
    SELECT state.*,
      state.unusable_reason IS NOT NULL AS is_unusable,
      jsonb_build_object(
        'acceptance', jsonb_build_object(
          'accepted_at', to_char(state.accepted_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'authority_digest', state.authority_digest,
          'integrity_reference', state.integrity_reference,
          'resolver_version', state.resolver_version,
          'supersedes_reference_id', state.supersedes_reference_id::text
        ),
        'artifact', jsonb_build_object(
          'artifact_digest', state.artifact_digest,
          'evidence_class', state.evidence_class,
          'evidence_id', state.evidence_id,
          'evidence_namespace', state.evidence_namespace,
          'evidence_version', state.evidence_version,
          'expires_at', CASE WHEN state.evidence_expires_at IS NULL THEN NULL ELSE
            to_char(state.evidence_expires_at AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END,
          'lifecycle', state.lifecycle,
          'observed_at', to_char(state.observed_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'period_end', CASE WHEN state.period_end IS NULL THEN NULL ELSE
            to_char(state.period_end AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END,
          'period_start', CASE WHEN state.period_start IS NULL THEN NULL ELSE
            to_char(state.period_start AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END
        ),
        'consent', jsonb_build_object(
          'consent_data_class', state.consent_data_class,
          'consent_id', state.consent_id,
          'consent_namespace', state.consent_namespace,
          'consent_purpose', state.consent_purpose,
          'consent_use_scope', state.consent_use_scope,
          'consent_version', state.consent_version,
          'expires_at', to_char(state.consent_expires_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'retention_until', to_char(state.retention_until AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
          'status', 'ACTIVE'
        ),
        'proposition_verification', jsonb_build_object(
          'proposition_schema_version', state.proposition_schema_version,
          'proposition_type', state.proposition_type,
          'proposition_unit', state.proposition_unit,
          'proposition_value', state.proposition_value,
          'verification_method', state.verification_method,
          'status', state.verification_status
        ),
        'reference_id', state.reference_id::text,
        'schema_version', 1,
        'source_attestation', jsonb_build_object(
          'acquisition_method', state.acquisition_method,
          'attestation_id', state.source_attestation_id,
          'attestation_version', state.source_attestation_version,
          'issuer_id', state.issuer_id,
          'registry_digest', state.source_registry_digest,
          'source_class', state.source_class,
          'source_id', state.source_id,
          'valid_until', to_char(state.source_valid_until AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        ),
        'subject', jsonb_build_object(
          'subject_digest', state.subject_digest,
          'subject_id', state.subject_id
        )
      ) AS value
    FROM state
  )
  SELECT
    coalesce(jsonb_agg(value ORDER BY reference_id) FILTER (WHERE NOT is_unusable), '[]'),
    coalesce(jsonb_agg(value || jsonb_build_object(
      'unusable_reason', unusable_reason
    ) ORDER BY reference_id) FILTER (WHERE is_unusable), '[]')
    INTO accepted_refs, unusable_refs FROM classified;
  SELECT coalesce(jsonb_agg(value ORDER BY value::text), '[]') INTO consent_refs FROM (
    SELECT DISTINCT jsonb_build_object(
      'namespace', ref.consent_namespace, 'consent_id', ref.consent_id,
      'version', ref.consent_version
    ) AS value FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = requested_tenant_id AND ref.case_id = requested_case_id
  ) deduplicated_consents;
  SELECT coalesce(jsonb_agg(value ORDER BY value::text), '[]') INTO source_refs FROM (
    SELECT DISTINCT jsonb_build_object(
      'source_id', ref.source_id, 'attestation_id', ref.source_attestation_id,
      'attestation_version', ref.source_attestation_version,
      'registry_digest', ref.source_registry_digest
    ) AS value FROM investigator.investigation_evidence_reference ref
    WHERE ref.tenant_id = requested_tenant_id AND ref.case_id = requested_case_id
  ) deduplicated_sources;
  SELECT encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'accepted_reference_ids', coalesce((
      SELECT jsonb_agg(item->>'reference_id' ORDER BY item->>'reference_id')
      FROM jsonb_array_elements(accepted_refs) item
    ), '[]'),
    'unusable_references', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'reference_id', item->>'reference_id', 'reason', item->>'unusable_reason'
      ) ORDER BY item->>'reference_id')
      FROM jsonb_array_elements(unusable_refs) item
    ), '[]'),
    'evidence_state_version', evidence_version,
    'references', coalesce((
      SELECT jsonb_agg(item - 'unusable_reason' ORDER BY item->>'reference_id')
      FROM jsonb_array_elements(accepted_refs || unusable_refs) item
    ), '[]')
  )), 'UTF8')), 'hex') INTO evidence_digest;
  snapshot_payload := jsonb_build_object(
    'applicable_versions', jsonb_build_object(
      'canonicalization', 'olin-canonical-json-1',
      'event_registry', 'investigator-events-2.0',
      'evidence_reference', 'investigator-evidence-reference-1',
      'evidence_resolver', 'investigator-evidence-resolver-1.0'
    ),
    'audit', jsonb_build_object(
      'case_created_actor', jsonb_build_object(
        'actor_type', first_event.actor_type, 'actor_reference', first_event.actor_id,
        'tenant_id', first_event.tenant_id::text, 'case_id', first_event.actor_case_id::text,
        'authentication_reference', first_event.authentication_reference,
        'authorization_source', first_event.authorization_source,
        'correlation_id', first_event.correlation_id,
        'created_at', to_char(first_event.actor_context_created_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
      ),
      'latest_event_actor', jsonb_build_object(
        'actor_type', head_event.actor_type, 'actor_reference', head_event.actor_id,
        'tenant_id', head_event.tenant_id::text, 'case_id', head_event.actor_case_id::text,
        'authentication_reference', head_event.authentication_reference,
        'authorization_source', head_event.authorization_source,
        'correlation_id', head_event.correlation_id,
        'created_at', to_char(head_event.actor_context_created_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
      )
    ),
    'case', jsonb_build_object(
      'case_id', case_row.case_id::text, 'case_version', case_row.case_version,
      'cohort_reference', case_row.cohort_reference,
      'created_at', to_char(case_row.created_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'created_by', case_row.created_by,
      'legacy_case_reference', case_row.legacy_case_reference,
      'tenant_id', case_row.tenant_id::text,
      'updated_at', to_char(case_row.updated_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'event_stream', jsonb_build_object(
      'head_event_digest', head_event.event_digest,
      'head_event_id', head_event.event_id::text,
      'head_sequence', head_event.event_sequence,
      'stream_digest', stream_digest
    ),
    'evidence', jsonb_build_object(
      'accepted_evidence_refs', accepted_refs,
      'unusable_evidence_refs', unusable_refs,
      'consent_refs', consent_refs,
      'source_attestation_refs', source_refs,
      'evidence_state_version', evidence_version,
      'evidence_state_digest', evidence_digest
    ),
    'lifecycle', jsonb_build_object('state', 'OPEN'),
    'snapshot_schema_version', 2
  );
  snapshot_bytes := convert_to(investigator.canonical_json(snapshot_payload), 'UTF8');
  snapshot_digest := encode(sha256(snapshot_bytes), 'hex');
  SELECT snapshot.* INTO existing_snapshot FROM investigator.case_snapshot snapshot
    WHERE snapshot.tenant_id = requested_tenant_id AND snapshot.case_id = requested_case_id
      AND snapshot.event_head_sequence = expected_case_version
      AND snapshot.snapshot_schema_version = 2;
  IF FOUND THEN
    IF existing_snapshot.canonical_digest <> snapshot_digest THEN
      RAISE EXCEPTION 'snapshot content conflicts at the same event head'
        USING ERRCODE = '40001';
    END IF;
    new_snapshot_id := existing_snapshot.snapshot_id;
  ELSE
    INSERT INTO investigator.case_snapshot (
      snapshot_id, tenant_id, case_id, case_version, event_head_sequence,
      snapshot_schema_version, canonical_snapshot_payload, canonical_snapshot_bytes,
      canonical_digest, created_by_actor_type, created_by_actor_reference,
      created_by_actor_case_id, authentication_reference, authorization_source,
      correlation_id, actor_context_created_at
    ) VALUES (
      new_snapshot_id, requested_tenant_id, requested_case_id, case_row.case_version,
      head_event.event_sequence, 2, snapshot_payload, snapshot_bytes, snapshot_digest,
      'system', session_user, requested_case_id, 'postgres-login:' || session_user,
      'investigator-tenant-role-binding', correlation_reference, transaction_timestamp()
    );
  END IF;
  INSERT INTO investigator.case_snapshot_request (
    tenant_id, idempotency_key, case_id, expected_case_version, snapshot_id,
    requested_by_actor_type, requested_by_actor_reference,
    authentication_reference, authorization_source, correlation_id
  ) VALUES (
    requested_tenant_id, requested_idempotency_key, requested_case_id,
    expected_case_version, new_snapshot_id, 'system', session_user,
    'postgres-login:' || session_user, 'investigator-tenant-role-binding',
    correlation_reference
  );
  RETURN QUERY SELECT new_snapshot_id, snapshot_digest;
END
$function$;

CREATE FUNCTION investigator.is_snapshot_structurally_current_v2(
  requested_tenant_id uuid,
  requested_snapshot_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
  SELECT investigator.is_snapshot_current(requested_tenant_id, requested_snapshot_id)
     AND EXISTS (
       SELECT 1 FROM investigator.case_snapshot snapshot
       WHERE snapshot.tenant_id = requested_tenant_id
         AND snapshot.snapshot_id = requested_snapshot_id
         AND snapshot.snapshot_schema_version = 2
         AND (snapshot.canonical_snapshot_payload #>>
           '{evidence,evidence_state_version}')::bigint = (
             SELECT coalesce(max((event.payload->>'evidence_state_version')::bigint), 0)
             FROM investigator.investigation_event event
             WHERE event.tenant_id = snapshot.tenant_id AND event.case_id = snapshot.case_id
               AND event.event_type IN (
                 'EVIDENCE_ACCEPTED', 'EVIDENCE_BECAME_UNUSABLE',
                 'CONSENT_STATE_CHANGED'
               )
           )
         AND NOT EXISTS (
           SELECT 1 FROM jsonb_array_elements(
             snapshot.canonical_snapshot_payload #> '{evidence,accepted_evidence_refs}'
           ) accepted
           JOIN investigator.investigation_evidence_reference ref
             ON ref.tenant_id = snapshot.tenant_id AND ref.case_id = snapshot.case_id
            AND ref.reference_id = (accepted->>'reference_id')::uuid
           WHERE ref.source_valid_until <= statement_timestamp()
              OR ref.consent_expires_at <= statement_timestamp()
              OR ref.retention_until <= statement_timestamp()
              OR (ref.evidence_expires_at IS NOT NULL
                  AND ref.evidence_expires_at <= statement_timestamp())
         )
     )
$function$;

REVOKE ALL ON TABLE investigator.investigation_evidence_reference FROM PUBLIC;
REVOKE ALL ON TABLE investigator.investigation_evidence_reference
  FROM olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.append_evidence_authority_event(
  uuid, uuid, bigint, uuid, text, jsonb, timestamptz, text
) FROM PUBLIC, olin_investigator_runtime, olin_investigator_evidence_authority;
REVOKE ALL ON FUNCTION investigator.mark_evidence_unusable(
  uuid, uuid, uuid, uuid, bigint, uuid, text, text, timestamptz, text
) FROM PUBLIC, olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.record_consent_state_change(
  uuid, uuid, uuid, text, text, text, bigint, uuid, text, timestamptz, text
) FROM PUBLIC, olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.accept_evidence_reference(
  jsonb, uuid, bigint, uuid, text
) FROM PUBLIC, olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.create_snapshot_v2(uuid, uuid, bigint, text)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.is_snapshot_structurally_current_v2(uuid, uuid)
  FROM PUBLIC;

GRANT USAGE ON SCHEMA investigator TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.session_tenant_id(),
  investigator.context_tenant_id(), investigator.tenant_access_allowed(uuid)
  TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.accept_evidence_reference(
  jsonb, uuid, bigint, uuid, text
) TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.mark_evidence_unusable(
  uuid, uuid, uuid, uuid, bigint, uuid, text, text, timestamptz, text
) TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.record_consent_state_change(
  uuid, uuid, uuid, text, text, text, bigint, uuid, text, timestamptz, text
) TO olin_investigator_evidence_authority;
GRANT EXECUTE ON FUNCTION investigator.is_snapshot_structurally_current_v2(uuid, uuid)
  TO olin_investigator_evidence_authority;

GRANT SELECT ON investigator.investigation_evidence_reference
  TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.create_snapshot_v2(uuid, uuid, bigint, text)
  TO olin_investigator_runtime;
COMMENT ON TABLE investigator.investigation_evidence_reference IS
  'Immutable references to canonical evidence, consent, subject, and source-attestation authority; contains no artifact body or mutable trust state';

RESET SESSION AUTHORIZATION;
COMMIT;
