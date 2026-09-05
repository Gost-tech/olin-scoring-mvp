-- Investigator V1 Phase 1: authoritative actor provenance and immutable snapshots.
-- Apply only after 0001_investigator_phase0.sql, using the same migration owner.

BEGIN;

DO $precondition$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
  ) THEN
    RAISE EXCEPTION
      'Phase 1 migration requires a controlled superuser or BYPASSRLS migration principal for the global empty-store cutover check';
  END IF;
  IF to_regclass('investigator.investigation_case') IS NULL
     OR to_regclass('investigator.investigation_event') IS NULL THEN
    RAISE EXCEPTION 'Investigator Phase 0 migration must be applied first';
  END IF;
  -- Phase 0 deliberately revokes this membership when it finishes. Reacquire
  -- the migration-owner role for DDL. The explicit BYPASSRLS requirement above
  -- ensures the global cutover check cannot have legacy rows hidden by FORCE RLS.
  EXECUTE format('GRANT olin_investigator_owner TO %I', current_user);
  IF EXISTS (SELECT 1 FROM investigator.investigation_event)
     OR EXISTS (SELECT 1 FROM investigator.investigation_case) THEN
    RAISE EXCEPTION
      'Phase 1 requires an empty Phase 0 case/event store; authenticated provenance cannot be backfilled';
  END IF;
END
$precondition$;

SET ROLE olin_investigator_owner;

-- These columns close the Phase 0 limitation where actor_id/workload_id were
-- contextual audit strings rather than a complete authentication provenance.
ALTER TABLE investigator.investigation_event
  ADD COLUMN actor_case_id uuid,
  ADD COLUMN authentication_reference text,
  ADD COLUMN authorization_source text,
  ADD COLUMN correlation_id text,
  ADD COLUMN actor_context_created_at timestamptz,
  ADD COLUMN event_digest text;

ALTER TABLE investigator.investigation_event
  ADD CONSTRAINT investigation_event_actor_case_scope CHECK (
    actor_case_id IS NULL OR actor_case_id = case_id
  ),
  ADD CONSTRAINT investigation_event_authentication_reference CHECK (
    authentication_reference IS NULL
    OR length(btrim(authentication_reference)) BETWEEN 1 AND 240
  ),
  ADD CONSTRAINT investigation_event_authorization_source CHECK (
    authorization_source IS NULL
    OR length(btrim(authorization_source)) BETWEEN 1 AND 240
  ),
  ADD CONSTRAINT investigation_event_correlation_id CHECK (
    correlation_id IS NULL OR length(btrim(correlation_id)) BETWEEN 1 AND 240
  ),
  ADD CONSTRAINT investigation_event_digest CHECK (
    event_digest IS NULL OR event_digest ~ '^[0-9a-f]{64}$'
  );

COMMENT ON COLUMN investigator.investigation_event.authentication_reference IS
  'Non-secret reference to the authentication result that resolved ActorContext';
COMMENT ON COLUMN investigator.investigation_event.authorization_source IS
  'Non-secret policy/authorization source that admitted the actor command';
COMMENT ON COLUMN investigator.investigation_event.event_digest IS
  'SHA-256 over the complete canonical event envelope; NULL only for pre-Phase-1 rows';

CREATE FUNCTION investigator.canonical_json(value jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $function$
  SELECT CASE jsonb_typeof(value)
    WHEN 'object' THEN (
      SELECT '{' || coalesce(
        string_agg(to_jsonb(item.key)::text || ':' || investigator.canonical_json(item.value), ',' ORDER BY item.key COLLATE "C"),
        ''
      ) || '}'
      FROM jsonb_each(value) AS item
    )
    WHEN 'array' THEN (
      SELECT '[' || coalesce(
        string_agg(investigator.canonical_json(item.value), ',' ORDER BY item.ordinality),
        ''
      ) || ']'
      FROM jsonb_array_elements(value) WITH ORDINALITY AS item(value, ordinality)
    )
    ELSE value::text
  END
$function$;

REVOKE ALL ON FUNCTION investigator.canonical_json(jsonb) FROM PUBLIC;

CREATE FUNCTION investigator.event_integrity_valid(
  event_row investigator.investigation_event
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog, investigator
AS $function$
  SELECT coalesce(
    event_row.payload_digest = encode(sha256(convert_to(
      investigator.canonical_json(event_row.payload), 'UTF8'
    )), 'hex')
    AND event_row.event_digest = encode(sha256(convert_to(
      investigator.canonical_json(jsonb_build_object(
        'actor', jsonb_build_object(
          'actor_type', event_row.actor_type,
          'actor_reference', event_row.actor_id,
          'tenant_id', event_row.tenant_id::text,
          'case_id', event_row.actor_case_id::text,
          'authentication_reference', event_row.authentication_reference,
          'authorization_source', event_row.authorization_source,
          'correlation_id', event_row.correlation_id,
          'created_at', to_char(
            event_row.actor_context_created_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
          )
        ),
        'case_id', event_row.case_id::text,
        'causation_event_id', event_row.causation_event_id::text,
        'event_id', event_row.event_id::text,
        'event_type', event_row.event_type,
        'idempotency_key', event_row.idempotency_key,
        'occurred_at', to_char(
          event_row.occurred_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'parent_event_id', event_row.parent_event_id::text,
        'payload', event_row.payload,
        'recorded_at', to_char(
          event_row.recorded_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        ),
        'schema_version', event_row.payload_schema_version,
        'sequence', event_row.event_sequence,
        'tenant_id', event_row.tenant_id::text
      )), 'UTF8'
    )), 'hex'),
    false
  )
$function$;

REVOKE ALL ON FUNCTION investigator.event_integrity_valid(
  investigator.investigation_event
) FROM PUBLIC;

CREATE TABLE investigator.case_snapshot (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  case_version bigint NOT NULL CHECK (case_version > 0),
  event_head_sequence bigint NOT NULL CHECK (event_head_sequence > 0),
  snapshot_schema_version integer NOT NULL CHECK (snapshot_schema_version = 1),
  canonical_snapshot_payload jsonb NOT NULL CHECK (
    jsonb_typeof(canonical_snapshot_payload) = 'object'
  ),
  canonical_snapshot_bytes bytea NOT NULL,
  digest_algorithm text NOT NULL DEFAULT 'sha256' CHECK (digest_algorithm = 'sha256'),
  canonical_digest text NOT NULL CHECK (canonical_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  created_by_actor_type text NOT NULL CHECK (
    created_by_actor_type IN ('bank_service', 'human', 'system')
  ),
  created_by_actor_reference text NOT NULL CHECK (
    length(btrim(created_by_actor_reference)) BETWEEN 1 AND 240
  ),
  created_by_actor_case_id uuid,
  authentication_reference text NOT NULL CHECK (
    length(btrim(authentication_reference)) BETWEEN 1 AND 240
  ),
  authorization_source text NOT NULL CHECK (
    length(btrim(authorization_source)) BETWEEN 1 AND 240
  ),
  correlation_id text NOT NULL CHECK (length(btrim(correlation_id)) BETWEEN 1 AND 240),
  actor_context_created_at timestamptz NOT NULL,
  CONSTRAINT case_snapshot_tenant_case_fk
    FOREIGN KEY (tenant_id, case_id)
    REFERENCES investigator.investigation_case (tenant_id, case_id),
  CONSTRAINT case_snapshot_actor_case_scope CHECK (
    created_by_actor_case_id IS NULL OR created_by_actor_case_id = case_id
  ),
  CONSTRAINT case_snapshot_version_head_match CHECK (case_version = event_head_sequence),
  CONSTRAINT case_snapshot_head_unique UNIQUE (
    tenant_id, case_id, event_head_sequence, snapshot_schema_version
  ),
  CONSTRAINT case_snapshot_tenant_case_snapshot_unique UNIQUE (tenant_id, case_id, snapshot_id),
  CONSTRAINT case_snapshot_bytes_limit CHECK (octet_length(canonical_snapshot_bytes) <= 1048576),
  CONSTRAINT case_snapshot_payload_limit CHECK (
    octet_length(canonical_snapshot_payload::text) <= 1048576
  )
);

CREATE TABLE investigator.case_snapshot_request (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 8 AND 240),
  case_id uuid NOT NULL,
  expected_case_version bigint NOT NULL CHECK (expected_case_version > 0),
  snapshot_id uuid NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  requested_by_actor_type text NOT NULL CHECK (requested_by_actor_type = 'system'),
  requested_by_actor_reference text NOT NULL CHECK (
    length(btrim(requested_by_actor_reference)) BETWEEN 1 AND 240
  ),
  authentication_reference text NOT NULL CHECK (
    length(btrim(authentication_reference)) BETWEEN 1 AND 240
  ),
  authorization_source text NOT NULL CHECK (
    length(btrim(authorization_source)) BETWEEN 1 AND 240
  ),
  correlation_id text NOT NULL CHECK (length(btrim(correlation_id)) BETWEEN 1 AND 240),
  CONSTRAINT case_snapshot_request_key_unique UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT case_snapshot_request_snapshot_fk
    FOREIGN KEY (tenant_id, case_id, snapshot_id)
    REFERENCES investigator.case_snapshot (tenant_id, case_id, snapshot_id)
);

CREATE TABLE investigator.case_snapshot_invalidation (
  invalidation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  snapshot_id uuid NOT NULL,
  invalidation_event_id uuid NOT NULL,
  reason_code text NOT NULL CHECK (reason_code IN (
    'DIGEST_MISMATCH',
    'EVENT_STREAM_CORRUPTION',
    'CANONICALIZATION_FAILURE',
    'PROVENANCE_FAILURE'
  )),
  reason_reference text NOT NULL CHECK (
    length(btrim(reason_reference)) BETWEEN 1 AND 240
  ),
  invalidated_at timestamptz NOT NULL,
  invalidated_by_actor_type text NOT NULL CHECK (
    invalidated_by_actor_type IN ('bank_service', 'human', 'system')
  ),
  invalidated_by_actor_reference text NOT NULL CHECK (
    length(btrim(invalidated_by_actor_reference)) BETWEEN 1 AND 240
  ),
  authentication_reference text NOT NULL CHECK (
    length(btrim(authentication_reference)) BETWEEN 1 AND 240
  ),
  authorization_source text NOT NULL CHECK (
    length(btrim(authorization_source)) BETWEEN 1 AND 240
  ),
  correlation_id text NOT NULL CHECK (length(btrim(correlation_id)) BETWEEN 1 AND 240),
  actor_context_created_at timestamptz NOT NULL,
  idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 8 AND 240),
  CONSTRAINT case_snapshot_invalidation_snapshot_fk
    FOREIGN KEY (tenant_id, case_id, snapshot_id)
    REFERENCES investigator.case_snapshot (tenant_id, case_id, snapshot_id),
  CONSTRAINT case_snapshot_invalidation_event_fk
    FOREIGN KEY (tenant_id, case_id, invalidation_event_id)
    REFERENCES investigator.investigation_event (tenant_id, case_id, event_id),
  CONSTRAINT case_snapshot_one_invalidation UNIQUE (tenant_id, case_id, snapshot_id),
  CONSTRAINT case_snapshot_invalidation_idempotency_unique UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX case_snapshot_case_created_idx
  ON investigator.case_snapshot (tenant_id, case_id, created_at DESC);
CREATE INDEX case_snapshot_invalidation_case_idx
  ON investigator.case_snapshot_invalidation (tenant_id, case_id, invalidated_at DESC);

ALTER TABLE investigator.case_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.case_snapshot FORCE ROW LEVEL SECURITY;
ALTER TABLE investigator.case_snapshot_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.case_snapshot_request FORCE ROW LEVEL SECURITY;
ALTER TABLE investigator.case_snapshot_invalidation ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.case_snapshot_invalidation FORCE ROW LEVEL SECURITY;

CREATE POLICY case_snapshot_tenant_policy
  ON investigator.case_snapshot
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE POLICY case_snapshot_invalidation_tenant_policy
  ON investigator.case_snapshot_invalidation
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE POLICY case_snapshot_request_tenant_policy
  ON investigator.case_snapshot_request
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE FUNCTION investigator.reject_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'Investigator history records are immutable' USING ERRCODE = '55000';
END
$function$;

REVOKE ALL ON FUNCTION investigator.reject_history_mutation() FROM PUBLIC;

CREATE TRIGGER case_snapshot_immutable
BEFORE UPDATE OR DELETE ON investigator.case_snapshot
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER case_snapshot_request_immutable
BEFORE UPDATE OR DELETE ON investigator.case_snapshot_request
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER case_snapshot_invalidation_immutable
BEFORE UPDATE OR DELETE ON investigator.case_snapshot_invalidation
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER investigation_event_immutable
BEFORE UPDATE OR DELETE ON investigator.investigation_event
FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER investigation_event_no_truncate
BEFORE TRUNCATE ON investigator.investigation_event
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER case_snapshot_no_truncate
BEFORE TRUNCATE ON investigator.case_snapshot
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER case_snapshot_request_no_truncate
BEFORE TRUNCATE ON investigator.case_snapshot_request
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

CREATE TRIGGER case_snapshot_invalidation_no_truncate
BEFORE TRUNCATE ON investigator.case_snapshot_invalidation
FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation();

-- Replace the Phase 0 functions without changing their signatures. Until a real
-- human-authentication resolver exists, the only database ActorContext is SYSTEM
-- and its identity/authentication provenance is derived from the tenant login.
-- Caller-writable GUCs cannot override these authoritative fields.
CREATE OR REPLACE FUNCTION investigator.create_case(
  requested_case_id uuid,
  requested_tenant_id uuid,
  requested_legacy_reference text,
  requested_cohort_reference text,
  requested_event_id uuid,
  requested_occurred_at timestamptz,
  requested_payload jsonb,
  requested_payload_schema_version integer,
  requested_idempotency_key text,
  requested_payload_digest text,
  requested_integrity_metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  context_actor text := session_user;
  context_actor_type text := 'system';
  context_workload text := session_user;
  context_authentication text := 'postgres-login:' || session_user;
  context_authorization text := 'investigator-tenant-role-binding';
  context_correlation text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
  context_actor_case uuid := requested_case_id;
  context_created_at timestamptz := transaction_timestamp();
  calculated_payload_digest text;
  calculated_event_digest text;
  existing_event investigator.investigation_event%ROWTYPE;
  existing_case investigator.investigation_case%ROWTYPE;
  recorded_time timestamptz := statement_timestamp();
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login' USING ERRCODE = '42501';
  END IF;
  IF requested_payload <> '{}'::jsonb OR requested_payload_schema_version <> 1
     OR requested_integrity_metadata <> '{}'::jsonb THEN
    RAISE EXCEPTION 'CASE_CREATED payload/schema/metadata must be empty/v1' USING ERRCODE = '22023';
  END IF;
  calculated_payload_digest := encode(sha256(convert_to(investigator.canonical_json(requested_payload), 'UTF8')), 'hex');
  IF requested_payload_digest <> calculated_payload_digest THEN
    RAISE EXCEPTION 'payload digest does not match canonical JSON payload' USING ERRCODE = '22000';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0));
  SELECT * INTO existing_event FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    SELECT * INTO existing_case FROM investigator.investigation_case
      WHERE tenant_id = requested_tenant_id AND case_id = existing_event.case_id;
    IF existing_event.case_id = requested_case_id
       AND existing_event.event_type = 'CASE_CREATED'
       AND existing_event.event_id = requested_event_id
       AND existing_event.occurred_at = requested_occurred_at
       AND existing_event.actor_type = context_actor_type
       AND existing_event.actor_id = context_actor
       AND existing_event.workload_id IS NOT DISTINCT FROM context_workload
       AND existing_event.actor_case_id IS NOT DISTINCT FROM context_actor_case
       AND existing_event.authentication_reference = context_authentication
       AND existing_event.authorization_source = context_authorization
       AND existing_event.correlation_id = context_correlation
       AND existing_event.payload = requested_payload
       AND existing_event.payload_schema_version = requested_payload_schema_version
       AND existing_event.payload_digest = calculated_payload_digest
       AND existing_event.integrity_metadata = requested_integrity_metadata
       AND existing_case.legacy_case_reference IS NOT DISTINCT FROM requested_legacy_reference
       AND existing_case.cohort_reference IS NOT DISTINCT FROM requested_cohort_reference THEN
      RETURN existing_event.case_id;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing event' USING ERRCODE = '23505';
  END IF;

  calculated_event_digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'actor', jsonb_build_object(
      'actor_type', context_actor_type, 'actor_reference', context_actor,
      'tenant_id', requested_tenant_id::text, 'case_id', context_actor_case::text,
      'authentication_reference', context_authentication,
      'authorization_source', context_authorization, 'correlation_id', context_correlation,
      'created_at', to_char(context_created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'case_id', requested_case_id::text, 'causation_event_id', NULL,
    'event_id', requested_event_id::text, 'event_type', 'CASE_CREATED',
    'idempotency_key', requested_idempotency_key,
    'occurred_at', to_char(requested_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'parent_event_id', NULL, 'payload', requested_payload,
    'recorded_at', to_char(recorded_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'schema_version', 1, 'sequence', 1, 'tenant_id', requested_tenant_id::text
  )), 'UTF8')), 'hex');

  INSERT INTO investigator.investigation_case (
    case_id, tenant_id, legacy_case_reference, cohort_reference,
    case_version, created_at, created_by, updated_at
  ) VALUES (
    requested_case_id, requested_tenant_id, requested_legacy_reference,
    requested_cohort_reference, 1, recorded_time, context_actor, recorded_time
  );
  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at, recorded_at,
    actor_type, actor_id, workload_id, actor_case_id, authentication_reference,
    authorization_source, correlation_id, actor_context_created_at, payload,
    payload_schema_version, idempotency_key, payload_digest, integrity_metadata, event_digest
  ) VALUES (
    requested_event_id, requested_tenant_id, requested_case_id, 1, 'CASE_CREATED',
    requested_occurred_at, recorded_time, context_actor_type, context_actor, context_workload,
    context_actor_case, context_authentication, context_authorization, context_correlation,
    context_created_at, requested_payload, 1, requested_idempotency_key,
    calculated_payload_digest, requested_integrity_metadata, calculated_event_digest
  );
  RETURN requested_case_id;
END
$function$;

CREATE OR REPLACE FUNCTION investigator.append_event(
  requested_tenant_id uuid,
  requested_case_id uuid,
  expected_case_version bigint,
  requested_event_id uuid,
  requested_event_type text,
  requested_occurred_at timestamptz,
  requested_payload jsonb,
  requested_payload_schema_version integer,
  requested_idempotency_key text,
  requested_payload_digest text,
  requested_parent_event_id uuid DEFAULT NULL,
  requested_causation_event_id uuid DEFAULT NULL,
  requested_integrity_metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  context_actor text := session_user;
  context_actor_type text := 'system';
  context_workload text := session_user;
  context_authentication text := 'postgres-login:' || session_user;
  context_authorization text := 'investigator-tenant-role-binding';
  context_correlation text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
  context_actor_case uuid := requested_case_id;
  context_created_at timestamptz := transaction_timestamp();
  calculated_payload_digest text;
  calculated_event_digest text;
  current_version bigint;
  current_head uuid;
  existing_event investigator.investigation_event%ROWTYPE;
  next_sequence bigint;
  recorded_time timestamptz := statement_timestamp();
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login' USING ERRCODE = '42501';
  END IF;
  IF requested_event_type <> 'INVESTIGATION_EVENT_RECORDED'
     OR requested_payload_schema_version <> 1 OR requested_payload <> '{}'::jsonb
     OR requested_integrity_metadata <> '{}'::jsonb THEN
    RAISE EXCEPTION 'event type/payload/schema is not allowed by the Phase 1 registry' USING ERRCODE = '22023';
  END IF;
  calculated_payload_digest := encode(sha256(convert_to(investigator.canonical_json(requested_payload), 'UTF8')), 'hex');
  IF requested_payload_digest <> calculated_payload_digest THEN
    RAISE EXCEPTION 'payload digest does not match canonical JSON payload' USING ERRCODE = '22000';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0));
  SELECT * INTO existing_event FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    IF existing_event.case_id = requested_case_id
       AND existing_event.event_type = requested_event_type
       AND existing_event.event_id = requested_event_id
       AND existing_event.occurred_at = requested_occurred_at
       AND existing_event.actor_type = context_actor_type
       AND existing_event.actor_id = context_actor
       AND existing_event.workload_id IS NOT DISTINCT FROM context_workload
       AND existing_event.actor_case_id IS NOT DISTINCT FROM context_actor_case
       AND existing_event.authentication_reference = context_authentication
       AND existing_event.authorization_source = context_authorization
       AND existing_event.correlation_id = context_correlation
       AND existing_event.payload = requested_payload
       AND existing_event.payload_schema_version = requested_payload_schema_version
       AND existing_event.parent_event_id = requested_parent_event_id
       AND existing_event.causation_event_id IS NOT DISTINCT FROM requested_causation_event_id
       AND existing_event.payload_digest = calculated_payload_digest
       AND existing_event.integrity_metadata = requested_integrity_metadata THEN
      RETURN existing_event.event_sequence;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing event' USING ERRCODE = '23505';
  END IF;

  SELECT case_version INTO current_version FROM investigator.investigation_case
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002';
  END IF;
  IF current_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale case version: expected %, current %', expected_case_version, current_version USING ERRCODE = '40001';
  END IF;
  SELECT event_id INTO current_head FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND event_sequence = current_version;
  IF requested_parent_event_id IS DISTINCT FROM current_head THEN
    RAISE EXCEPTION 'parent event is not the current event head' USING ERRCODE = '22023';
  END IF;
  IF requested_causation_event_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND event_id = requested_causation_event_id AND event_sequence <= current_version
  ) THEN
    RAISE EXCEPTION 'causation event is not in the prior case stream' USING ERRCODE = '22023';
  END IF;
  next_sequence := current_version + 1;
  calculated_event_digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'actor', jsonb_build_object(
      'actor_type', context_actor_type, 'actor_reference', context_actor,
      'tenant_id', requested_tenant_id::text, 'case_id', context_actor_case::text,
      'authentication_reference', context_authentication,
      'authorization_source', context_authorization, 'correlation_id', context_correlation,
      'created_at', to_char(context_created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'case_id', requested_case_id::text,
    'causation_event_id', requested_causation_event_id::text,
    'event_id', requested_event_id::text, 'event_type', requested_event_type,
    'idempotency_key', requested_idempotency_key,
    'occurred_at', to_char(requested_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'parent_event_id', requested_parent_event_id::text, 'payload', requested_payload,
    'recorded_at', to_char(recorded_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'schema_version', 1, 'sequence', next_sequence, 'tenant_id', requested_tenant_id::text
  )), 'UTF8')), 'hex');

  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at, recorded_at,
    actor_type, actor_id, workload_id, actor_case_id, authentication_reference,
    authorization_source, correlation_id, actor_context_created_at, payload,
    payload_schema_version, idempotency_key, parent_event_id, causation_event_id,
    payload_digest, integrity_metadata, event_digest
  ) VALUES (
    requested_event_id, requested_tenant_id, requested_case_id, next_sequence,
    requested_event_type, requested_occurred_at, recorded_time, context_actor_type,
    context_actor, context_workload, context_actor_case, context_authentication,
    context_authorization, context_correlation, context_created_at, requested_payload,
    1, requested_idempotency_key, requested_parent_event_id,
    requested_causation_event_id, calculated_payload_digest,
    requested_integrity_metadata, calculated_event_digest
  );
  UPDATE investigator.investigation_case
    SET case_version = next_sequence, updated_at = recorded_time
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id;
  RETURN next_sequence;
END
$function$;

CREATE FUNCTION investigator.create_snapshot(
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
  context_actor text := session_user;
  context_actor_type text := 'system';
  context_authentication text := 'postgres-login:' || session_user;
  context_authorization text := 'investigator-tenant-role-binding';
  context_correlation text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
  context_actor_case uuid := requested_case_id;
  context_created_at timestamptz := transaction_timestamp();
  case_row investigator.investigation_case%ROWTYPE;
  first_event investigator.investigation_event%ROWTYPE;
  head_event investigator.investigation_event%ROWTYPE;
  snapshot_payload jsonb;
  snapshot_bytes bytea;
  snapshot_digest text;
  stream_digest text;
  existing_snapshot investigator.case_snapshot%ROWTYPE;
  existing_request investigator.case_snapshot_request%ROWTYPE;
  new_snapshot_id uuid := gen_random_uuid();
  event_count bigint;
  minimum_sequence bigint;
  maximum_sequence bigint;
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login' USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(requested_tenant_id::text || ':snapshot:' || requested_idempotency_key, 0));
  SELECT * INTO existing_request FROM investigator.case_snapshot_request
    WHERE tenant_id = requested_tenant_id AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    IF existing_request.case_id = requested_case_id
       AND existing_request.expected_case_version = expected_case_version
       AND existing_request.requested_by_actor_type = context_actor_type
       AND existing_request.requested_by_actor_reference = context_actor
       AND existing_request.authentication_reference = context_authentication
       AND existing_request.authorization_source = context_authorization
       AND existing_request.correlation_id = context_correlation
       THEN
      SELECT * INTO STRICT existing_snapshot FROM investigator.case_snapshot
        WHERE tenant_id = existing_request.tenant_id
          AND case_id = existing_request.case_id
          AND snapshot_id = existing_request.snapshot_id;
      RETURN QUERY SELECT existing_snapshot.snapshot_id, existing_snapshot.canonical_digest;
      RETURN;
    END IF;
    RAISE EXCEPTION 'snapshot idempotency key conflicts with an existing request' USING ERRCODE = '23505';
  END IF;

  SELECT * INTO case_row FROM investigator.investigation_case
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002';
  END IF;
  IF case_row.case_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale case version: expected %, current %', expected_case_version, case_row.case_version USING ERRCODE = '40001';
  END IF;
  SELECT count(*), min(event_sequence), max(event_sequence)
    INTO event_count, minimum_sequence, maximum_sequence
    FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id;
  IF event_count <> expected_case_version
     OR minimum_sequence <> 1 OR maximum_sequence <> expected_case_version THEN
    RAISE EXCEPTION 'event stream head/count does not match case version' USING ERRCODE = '22000';
  END IF;
  SELECT * INTO first_event FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id AND event_sequence = 1;
  SELECT * INTO head_event FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id AND event_sequence = expected_case_version;
  IF first_event.event_type <> 'CASE_CREATED' OR first_event.event_digest IS NULL
     OR head_event.event_digest IS NULL OR EXISTS (
       SELECT 1 FROM investigator.investigation_event
       WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
         AND (authentication_reference IS NULL OR authorization_source IS NULL
              OR correlation_id IS NULL OR actor_context_created_at IS NULL OR event_digest IS NULL)
     ) THEN
    RAISE EXCEPTION 'event stream lacks complete Phase 1 provenance/integrity' USING ERRCODE = '22000';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM investigator.investigation_event event
    LEFT JOIN investigator.investigation_event parent
      ON parent.tenant_id = event.tenant_id AND parent.case_id = event.case_id
     AND parent.event_sequence = event.event_sequence - 1
    WHERE event.tenant_id = requested_tenant_id AND event.case_id = requested_case_id
      AND (
        (event.event_sequence = 1 AND (
          event.event_type <> 'CASE_CREATED' OR event.parent_event_id IS NOT NULL
        ))
        OR (event.event_sequence > 1 AND event.event_type = 'CASE_CREATED')
        OR (event.event_sequence > 1 AND event.parent_event_id IS DISTINCT FROM parent.event_id)
        OR (event.causation_event_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM investigator.investigation_event cause
          WHERE cause.tenant_id = event.tenant_id AND cause.case_id = event.case_id
            AND cause.event_id = event.causation_event_id
            AND cause.event_sequence < event.event_sequence
        ))
        OR (event.event_type = 'CASE_CREATED' AND (
          event.payload_schema_version <> 1 OR event.payload <> '{}'::jsonb
        ))
        OR (event.event_type = 'INVESTIGATION_EVENT_RECORDED' AND (
          event.payload_schema_version <> 1 OR event.payload <> '{}'::jsonb
        ))
        OR (event.event_type = 'CASE_SNAPSHOT_INVALIDATED' AND (
          event.payload_schema_version <> 1
          OR (SELECT count(*) FROM jsonb_object_keys(event.payload)) <> 3
          OR NOT event.payload ?& ARRAY['snapshot_id', 'reason_code', 'reason_reference']
          OR coalesce(event.payload->>'snapshot_id' !~
            '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', true)
          OR coalesce(event.payload->>'reason_code' NOT IN (
            'DIGEST_MISMATCH', 'EVENT_STREAM_CORRUPTION',
            'CANONICALIZATION_FAILURE', 'PROVENANCE_FAILURE'
          ), true)
          OR coalesce(length(btrim(event.payload->>'reason_reference')) NOT BETWEEN 1 AND 240, true)
        ))
        OR event.event_type NOT IN (
          'CASE_CREATED', 'INVESTIGATION_EVENT_RECORDED', 'CASE_SNAPSHOT_INVALIDATED'
        )
        OR NOT investigator.event_integrity_valid(event)
      )
  ) THEN
    RAISE EXCEPTION 'event stream violates sequence, causation, or registry invariants' USING ERRCODE = '22000';
  END IF;
  SELECT encode(sha256(convert_to(investigator.canonical_json(jsonb_agg(
      event_digest ORDER BY event_sequence
    )), 'UTF8')), 'hex')
    INTO stream_digest
    FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id;

  snapshot_payload := jsonb_build_object(
    'applicable_versions', jsonb_build_object(
      'canonicalization', 'olin-canonical-json-1',
      'event_registry', 'investigator-events-1.0'
    ),
    'audit', jsonb_build_object(
      'case_created_actor', jsonb_build_object(
        'actor_type', first_event.actor_type, 'actor_reference', first_event.actor_id,
        'tenant_id', first_event.tenant_id::text, 'case_id', first_event.actor_case_id::text,
        'authentication_reference', first_event.authentication_reference,
        'authorization_source', first_event.authorization_source,
        'correlation_id', first_event.correlation_id,
        'created_at', to_char(first_event.actor_context_created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
      ),
      'latest_event_actor', jsonb_build_object(
        'actor_type', head_event.actor_type, 'actor_reference', head_event.actor_id,
        'tenant_id', head_event.tenant_id::text, 'case_id', head_event.actor_case_id::text,
        'authentication_reference', head_event.authentication_reference,
        'authorization_source', head_event.authorization_source,
        'correlation_id', head_event.correlation_id,
        'created_at', to_char(head_event.actor_context_created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
      )
    ),
    'case', jsonb_build_object(
      'case_id', case_row.case_id::text, 'case_version', case_row.case_version,
      'cohort_reference', case_row.cohort_reference,
      'created_at', to_char(case_row.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'created_by', case_row.created_by,
      'legacy_case_reference', case_row.legacy_case_reference,
      'tenant_id', case_row.tenant_id::text,
      'updated_at', to_char(case_row.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'event_stream', jsonb_build_object(
      'head_event_digest', head_event.event_digest,
      'head_event_id', head_event.event_id::text,
      'head_sequence', head_event.event_sequence,
      'stream_digest', stream_digest
    ),
    'lifecycle', jsonb_build_object('state', 'OPEN'),
    'snapshot_schema_version', 1
  );
  snapshot_bytes := convert_to(investigator.canonical_json(snapshot_payload), 'UTF8');
  snapshot_digest := encode(sha256(snapshot_bytes), 'hex');

  SELECT * INTO existing_snapshot FROM investigator.case_snapshot
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND event_head_sequence = expected_case_version AND snapshot_schema_version = 1;
  IF FOUND THEN
    IF existing_snapshot.canonical_snapshot_bytes <> snapshot_bytes
       OR existing_snapshot.canonical_digest <> snapshot_digest THEN
      RAISE EXCEPTION 'snapshot content conflicts at the same event head' USING ERRCODE = '40001';
    END IF;
    INSERT INTO investigator.case_snapshot_request (
      tenant_id, idempotency_key, case_id, expected_case_version, snapshot_id,
      requested_by_actor_type, requested_by_actor_reference,
      authentication_reference, authorization_source, correlation_id
    ) VALUES (
      requested_tenant_id, requested_idempotency_key, requested_case_id,
      expected_case_version, existing_snapshot.snapshot_id, context_actor_type,
      context_actor, context_authentication, context_authorization, context_correlation
    );
    RETURN QUERY SELECT existing_snapshot.snapshot_id, existing_snapshot.canonical_digest;
    RETURN;
  END IF;

  INSERT INTO investigator.case_snapshot (
    snapshot_id, tenant_id, case_id, case_version, event_head_sequence,
    snapshot_schema_version, canonical_snapshot_payload, canonical_snapshot_bytes,
    canonical_digest, created_by_actor_type, created_by_actor_reference,
    created_by_actor_case_id, authentication_reference, authorization_source,
    correlation_id, actor_context_created_at
  ) VALUES (
    new_snapshot_id, requested_tenant_id, requested_case_id, case_row.case_version,
    head_event.event_sequence, 1, snapshot_payload, snapshot_bytes, snapshot_digest,
    context_actor_type, context_actor, context_actor_case, context_authentication,
    context_authorization, context_correlation, context_created_at
  );
  INSERT INTO investigator.case_snapshot_request (
    tenant_id, idempotency_key, case_id, expected_case_version, snapshot_id,
    requested_by_actor_type, requested_by_actor_reference,
    authentication_reference, authorization_source, correlation_id
  ) VALUES (
    requested_tenant_id, requested_idempotency_key, requested_case_id,
    expected_case_version, new_snapshot_id, context_actor_type, context_actor,
    context_authentication, context_authorization, context_correlation
  );
  RETURN QUERY SELECT new_snapshot_id, snapshot_digest;
END
$function$;

CREATE FUNCTION investigator.invalidate_snapshot(
  requested_tenant_id uuid,
  requested_case_id uuid,
  requested_snapshot_id uuid,
  expected_case_version bigint,
  requested_reason_code text,
  requested_reason_reference text,
  requested_occurred_at timestamptz,
  requested_idempotency_key text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  context_actor text := session_user;
  context_actor_type text := 'system';
  context_authentication text := 'postgres-login:' || session_user;
  context_authorization text := 'investigator-tenant-role-binding';
  context_correlation text := 'postgres-command:' || encode(
    sha256(convert_to(requested_idempotency_key, 'UTF8')), 'hex'
  );
  context_actor_case uuid := requested_case_id;
  context_created_at timestamptz := transaction_timestamp();
  case_row investigator.investigation_case%ROWTYPE;
  snapshot_row investigator.case_snapshot%ROWTYPE;
  existing_invalidation investigator.case_snapshot_invalidation%ROWTYPE;
  existing_event investigator.investigation_event%ROWTYPE;
  current_head uuid;
  event_id uuid := gen_random_uuid();
  next_sequence bigint;
  event_payload jsonb;
  payload_digest text;
  event_digest text;
  recorded_time timestamptz := statement_timestamp();
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login' USING ERRCODE = '42501';
  END IF;
  IF requested_reason_code NOT IN (
    'DIGEST_MISMATCH', 'EVENT_STREAM_CORRUPTION',
    'CANONICALIZATION_FAILURE', 'PROVENANCE_FAILURE'
  ) OR length(btrim(requested_reason_reference)) NOT BETWEEN 1 AND 240 THEN
    RAISE EXCEPTION 'snapshot invalidation reason is not allowed' USING ERRCODE = '22023';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0));
  SELECT * INTO existing_invalidation FROM investigator.case_snapshot_invalidation
    WHERE tenant_id = requested_tenant_id AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    SELECT * INTO STRICT existing_event FROM investigator.investigation_event
      WHERE tenant_id = existing_invalidation.tenant_id
        AND case_id = existing_invalidation.case_id
        AND event_id = existing_invalidation.invalidation_event_id;
    IF existing_invalidation.case_id = requested_case_id
       AND existing_invalidation.snapshot_id = requested_snapshot_id
       AND existing_invalidation.reason_code = requested_reason_code
       AND existing_invalidation.reason_reference = btrim(requested_reason_reference)
       AND existing_invalidation.invalidated_by_actor_type = context_actor_type
       AND existing_invalidation.invalidated_by_actor_reference = context_actor
       AND existing_invalidation.authentication_reference = context_authentication
       AND existing_invalidation.authorization_source = context_authorization
       AND existing_invalidation.correlation_id = context_correlation
       AND existing_event.event_sequence = expected_case_version + 1
       AND existing_event.occurred_at = requested_occurred_at
       THEN
      RETURN existing_invalidation.invalidation_id;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing invalidation' USING ERRCODE = '23505';
  END IF;

  SELECT * INTO case_row FROM investigator.investigation_case
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002'; END IF;
  IF case_row.case_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale case version: expected %, current %', expected_case_version, case_row.case_version USING ERRCODE = '40001';
  END IF;
  SELECT * INTO snapshot_row FROM investigator.case_snapshot
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND snapshot_id = requested_snapshot_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'snapshot not found' USING ERRCODE = 'P0002'; END IF;
  IF EXISTS (
    SELECT 1 FROM investigator.case_snapshot_invalidation
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND snapshot_id = requested_snapshot_id
  ) THEN
    RAISE EXCEPTION 'snapshot is already invalidated' USING ERRCODE = '23505';
  END IF;
  SELECT investigation_event.event_id INTO current_head
    FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
      AND event_sequence = expected_case_version;
  next_sequence := expected_case_version + 1;
  event_payload := jsonb_build_object(
    'snapshot_id', requested_snapshot_id::text,
    'reason_code', requested_reason_code,
    'reason_reference', btrim(requested_reason_reference)
  );
  payload_digest := encode(sha256(convert_to(investigator.canonical_json(event_payload), 'UTF8')), 'hex');
  event_digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'actor', jsonb_build_object(
      'actor_type', context_actor_type, 'actor_reference', context_actor,
      'tenant_id', requested_tenant_id::text, 'case_id', context_actor_case::text,
      'authentication_reference', context_authentication,
      'authorization_source', context_authorization, 'correlation_id', context_correlation,
      'created_at', to_char(context_created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    ),
    'case_id', requested_case_id::text, 'causation_event_id', NULL,
    'event_id', event_id::text, 'event_type', 'CASE_SNAPSHOT_INVALIDATED',
    'idempotency_key', requested_idempotency_key,
    'occurred_at', to_char(requested_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'parent_event_id', current_head::text, 'payload', event_payload,
    'recorded_at', to_char(recorded_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'schema_version', 1, 'sequence', next_sequence, 'tenant_id', requested_tenant_id::text
  )), 'UTF8')), 'hex');

  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at, recorded_at,
    actor_type, actor_id, actor_case_id, authentication_reference, authorization_source,
    correlation_id, actor_context_created_at, payload, payload_schema_version,
    idempotency_key, parent_event_id, payload_digest, event_digest
  ) VALUES (
    event_id, requested_tenant_id, requested_case_id, next_sequence,
    'CASE_SNAPSHOT_INVALIDATED', requested_occurred_at, recorded_time,
    context_actor_type, context_actor, context_actor_case, context_authentication,
    context_authorization, context_correlation, context_created_at, event_payload, 1,
    requested_idempotency_key, current_head, payload_digest, event_digest
  );
  UPDATE investigator.investigation_case
    SET case_version = next_sequence, updated_at = recorded_time
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id;
  INSERT INTO investigator.case_snapshot_invalidation (
    tenant_id, case_id, snapshot_id, invalidation_event_id, reason_code,
    reason_reference, invalidated_at, invalidated_by_actor_type,
    invalidated_by_actor_reference, authentication_reference, authorization_source,
    correlation_id, actor_context_created_at, idempotency_key
  ) VALUES (
    requested_tenant_id, requested_case_id, requested_snapshot_id, event_id,
    requested_reason_code, btrim(requested_reason_reference), recorded_time,
    context_actor_type, context_actor, context_authentication, context_authorization,
    context_correlation, context_created_at, requested_idempotency_key
  ) RETURNING invalidation_id INTO existing_invalidation.invalidation_id;
  RETURN existing_invalidation.invalidation_id;
END
$function$;

CREATE FUNCTION investigator.is_snapshot_current(
  requested_tenant_id uuid,
  requested_snapshot_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
  SELECT investigator.tenant_access_allowed(requested_tenant_id)
     AND EXISTS (
       SELECT 1
       FROM investigator.case_snapshot snapshot
       JOIN investigator.investigation_case investigation_case
         ON investigation_case.tenant_id = snapshot.tenant_id
        AND investigation_case.case_id = snapshot.case_id
       WHERE snapshot.tenant_id = requested_tenant_id
         AND snapshot.snapshot_id = requested_snapshot_id
         AND snapshot.event_head_sequence = investigation_case.case_version
         AND snapshot.canonical_snapshot_bytes = convert_to(
           investigator.canonical_json(snapshot.canonical_snapshot_payload), 'UTF8'
         )
         AND snapshot.canonical_digest = encode(
           sha256(snapshot.canonical_snapshot_bytes), 'hex'
         )
         AND snapshot.canonical_snapshot_payload #>> '{event_stream,stream_digest}' = (
           SELECT encode(sha256(convert_to(investigator.canonical_json(jsonb_agg(
               event.event_digest ORDER BY event.event_sequence
             )), 'UTF8')), 'hex')
           FROM investigator.investigation_event event
           WHERE event.tenant_id = snapshot.tenant_id
             AND event.case_id = snapshot.case_id
         )
         AND NOT EXISTS (
           SELECT 1 FROM investigator.investigation_event event
           WHERE event.tenant_id = snapshot.tenant_id
             AND event.case_id = snapshot.case_id
             AND NOT investigator.event_integrity_valid(event)
         )
         AND NOT EXISTS (
           SELECT 1 FROM investigator.case_snapshot_invalidation invalidation
           WHERE invalidation.tenant_id = snapshot.tenant_id
             AND invalidation.case_id = snapshot.case_id
             AND invalidation.snapshot_id = snapshot.snapshot_id
         )
     )
$function$;

REVOKE ALL ON ALL TABLES IN SCHEMA investigator FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA investigator FROM olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.create_snapshot(uuid, uuid, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.invalidate_snapshot(uuid, uuid, uuid, bigint, text, text, timestamptz, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.is_snapshot_current(uuid, uuid) FROM PUBLIC;

GRANT SELECT ON investigator.case_snapshot TO olin_investigator_runtime;
GRANT SELECT ON investigator.case_snapshot_invalidation TO olin_investigator_runtime;
GRANT SELECT ON investigator.investigation_case TO olin_investigator_runtime;
GRANT SELECT ON investigator.investigation_event TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.create_snapshot(uuid, uuid, bigint, text) TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.invalidate_snapshot(uuid, uuid, uuid, bigint, text, text, timestamptz, text) TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.is_snapshot_current(uuid, uuid) TO olin_investigator_runtime;

COMMENT ON TABLE investigator.case_snapshot IS
  'Immutable canonical CaseSnapshot; the only permitted future Investigator reasoning input';
COMMENT ON TABLE investigator.case_snapshot_invalidation IS
  'Append-only integrity invalidation history; never rewrites historical snapshot content';
COMMENT ON ROLE olin_investigator_runtime IS
  'NOLOGIN Phase 1 capability role: tenant-bound case/event/snapshot reads plus constrained functions only';

RESET ROLE;
DO $remove_owner_membership$
BEGIN
  EXECUTE format('REVOKE olin_investigator_owner FROM %I', current_user);
END
$remove_owner_membership$;

COMMIT;
