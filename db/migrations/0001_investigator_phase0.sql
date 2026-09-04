-- Investigator V1 Phase 0: case/event spine and least-privilege runtime role.
-- Apply as a dedicated migration owner. Tenant logins are provisioned outside
-- this migration as NOINHERIT roles named olin_inv_t_<tenant UUID, no dashes>,
-- then granted membership in olin_investigator_runtime.

BEGIN;

DO $role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olin_investigator_owner') THEN
    CREATE ROLE olin_investigator_owner
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olin_investigator_runtime') THEN
    CREATE ROLE olin_investigator_runtime
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
END
$role$;
ALTER ROLE olin_investigator_owner
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE olin_investigator_runtime
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
DO $unexpected_membership$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_auth_members memberships
    JOIN pg_roles member_role ON member_role.oid = memberships.member
    JOIN pg_roles granted_role ON granted_role.oid = memberships.roleid
    WHERE member_role.rolname IN ('olin_investigator_owner', 'olin_investigator_runtime')
       OR granted_role.rolname IN ('olin_investigator_owner', 'olin_investigator_runtime')
  ) THEN
    RAISE EXCEPTION 'Investigator owner/runtime role has unexpected role membership';
  END IF;
END
$unexpected_membership$;
DO $owner_membership$
BEGIN
  EXECUTE format('GRANT olin_investigator_owner TO %I', current_user);
END
$owner_membership$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM olin_investigator_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM olin_investigator_runtime;
REVOKE CREATE ON SCHEMA public FROM olin_investigator_runtime;

DO $legacy_effective_privileges$
DECLARE
  exposed_relation text;
  exposed_routine text;
  exposed_schema text;
BEGIN
  SELECT namespace.nspname
    INTO exposed_schema
    FROM pg_namespace namespace
    WHERE namespace.nspname NOT IN ('investigator', 'pg_catalog', 'information_schema')
      AND namespace.nspname !~ '^pg_(toast|temp)'
      AND has_schema_privilege('olin_investigator_runtime', namespace.oid, 'CREATE')
    LIMIT 1;
  IF exposed_schema IS NOT NULL THEN
    RAISE EXCEPTION 'Investigator runtime inherits CREATE on non-Investigator schema %',
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
        'olin_investigator_runtime', relation.oid,
        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
      )
    LIMIT 1;
  IF exposed_relation IS NOT NULL THEN
    RAISE EXCEPTION 'Investigator runtime inherits privilege on non-Investigator relation %',
      exposed_relation;
  END IF;
  SELECT format('%I.%I', namespace.nspname, routine.proname)
    INTO exposed_routine
    FROM pg_proc routine
    JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
    WHERE namespace.nspname NOT IN ('investigator', 'pg_catalog', 'information_schema')
      AND namespace.nspname !~ '^pg_(toast|temp)'
      AND has_function_privilege('olin_investigator_runtime', routine.oid, 'EXECUTE')
    LIMIT 1;
  IF exposed_routine IS NOT NULL THEN
    RAISE EXCEPTION 'Investigator runtime inherits EXECUTE on non-Investigator routine %',
      exposed_routine;
  END IF;
END
$legacy_effective_privileges$;

-- A pre-existing schema is an ownership ambiguity, so this first migration
-- fails rather than adopting it.
CREATE SCHEMA investigator AUTHORIZATION olin_investigator_owner;
REVOKE ALL ON SCHEMA investigator FROM PUBLIC;
GRANT USAGE ON SCHEMA investigator TO olin_investigator_runtime;
SET ROLE olin_investigator_owner;

CREATE FUNCTION investigator.session_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $function$
DECLARE
  compact_id text;
BEGIN
  compact_id := substring(session_user FROM '^olin_inv_t_([0-9a-f]{32})$');
  IF compact_id IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN (
    substr(compact_id, 1, 8) || '-' || substr(compact_id, 9, 4) || '-' ||
    substr(compact_id, 13, 4) || '-' || substr(compact_id, 17, 4) || '-' ||
    substr(compact_id, 21, 12)
  )::uuid;
END
$function$;

CREATE FUNCTION investigator.context_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $function$
DECLARE
  context_value text;
BEGIN
  context_value := nullif(current_setting('olin.tenant_id', true), '');
  IF context_value IS NULL THEN
    RETURN NULL;
  END IF;
  BEGIN
    RETURN context_value::uuid;
  EXCEPTION WHEN invalid_text_representation THEN
    RETURN NULL;
  END;
END
$function$;

CREATE FUNCTION investigator.tenant_access_allowed(row_tenant_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, investigator
AS $function$
  SELECT row_tenant_id IS NOT NULL
     AND row_tenant_id = investigator.session_tenant_id()
     AND row_tenant_id = investigator.context_tenant_id()
$function$;

REVOKE ALL ON FUNCTION investigator.session_tenant_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.context_tenant_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.tenant_access_allowed(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION investigator.session_tenant_id() TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.context_tenant_id() TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.tenant_access_allowed(uuid) TO olin_investigator_runtime;

CREATE TABLE investigator.investigation_case (
  case_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  legacy_case_reference text CHECK (
    legacy_case_reference IS NULL OR octet_length(legacy_case_reference) <= 240
  ),
  cohort_reference text CHECK (
    cohort_reference IS NULL OR octet_length(cohort_reference) <= 240
  ),
  case_version bigint NOT NULL DEFAULT 0 CHECK (case_version >= 0),
  created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  created_by text NOT NULL CHECK (length(btrim(created_by)) BETWEEN 1 AND 240),
  updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  CONSTRAINT investigation_case_tenant_case_unique UNIQUE (tenant_id, case_id),
  CONSTRAINT investigation_case_legacy_unique UNIQUE (tenant_id, legacy_case_reference)
);

CREATE TABLE investigator.investigation_event (
  event_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  event_sequence bigint NOT NULL CHECK (event_sequence > 0),
  event_type text NOT NULL CHECK (event_type ~ '^[A-Z][A-Z0-9_]{2,63}$'),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  actor_type text NOT NULL CHECK (actor_type IN ('bank_service', 'human', 'system')),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 240),
  workload_id text CHECK (workload_id IS NULL OR octet_length(workload_id) <= 240),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  payload_schema_version integer NOT NULL CHECK (payload_schema_version > 0),
  idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 8 AND 240),
  parent_event_id uuid,
  causation_event_id uuid,
  digest_algorithm text NOT NULL DEFAULT 'sha256' CHECK (digest_algorithm = 'sha256'),
  payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  integrity_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (
      jsonb_typeof(integrity_metadata) = 'object'
      AND octet_length(integrity_metadata::text) <= 65536
    ),
  CONSTRAINT investigation_event_tenant_case_fk
    FOREIGN KEY (tenant_id, case_id)
    REFERENCES investigator.investigation_case (tenant_id, case_id),
  CONSTRAINT investigation_event_sequence_unique UNIQUE (tenant_id, case_id, event_sequence),
  CONSTRAINT investigation_event_idempotency_unique UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT investigation_event_tenant_case_event_unique UNIQUE (tenant_id, case_id, event_id),
  CONSTRAINT investigation_event_parent_fk
    FOREIGN KEY (tenant_id, case_id, parent_event_id)
    REFERENCES investigator.investigation_event (tenant_id, case_id, event_id),
  CONSTRAINT investigation_event_causation_fk
    FOREIGN KEY (tenant_id, case_id, causation_event_id)
    REFERENCES investigator.investigation_event (tenant_id, case_id, event_id),
  CONSTRAINT investigation_event_payload_limit
    CHECK (octet_length(payload::text) <= 262144)
);

CREATE INDEX investigation_case_tenant_updated_idx
  ON investigator.investigation_case (tenant_id, updated_at DESC);
CREATE INDEX investigation_event_case_sequence_idx
  ON investigator.investigation_event (tenant_id, case_id, event_sequence);

ALTER TABLE investigator.investigation_case ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_case FORCE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_event FORCE ROW LEVEL SECURITY;

CREATE POLICY investigation_case_tenant_policy
  ON investigator.investigation_case
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE POLICY investigation_event_tenant_policy
  ON investigator.investigation_event
  FOR ALL
  TO olin_investigator_runtime, olin_investigator_owner
  USING (investigator.tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.tenant_access_allowed(tenant_id));

CREATE FUNCTION investigator.create_case(
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
  context_actor text;
  context_actor_type text;
  context_workload text;
  calculated_payload_digest text;
  existing_event investigator.investigation_event%ROWTYPE;
  existing_case investigator.investigation_case%ROWTYPE;
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login'
      USING ERRCODE = '42501';
  END IF;
  context_actor := nullif(current_setting('olin.actor_id', true), '');
  context_actor_type := nullif(current_setting('olin.actor_type', true), '');
  context_workload := nullif(current_setting('olin.workload_id', true), '');
  IF context_actor IS NULL THEN
    RAISE EXCEPTION 'actor context is required' USING ERRCODE = '42501';
  END IF;
  IF context_actor_type NOT IN ('bank_service', 'system') THEN
    RAISE EXCEPTION 'case creation requires bank_service or system actor context'
      USING ERRCODE = '42501';
  END IF;
  IF requested_payload <> '{}'::jsonb
     OR requested_payload_schema_version <> 1
     OR requested_integrity_metadata <> '{}'::jsonb THEN
    RAISE EXCEPTION 'CASE_CREATED Phase 0 payload/schema/metadata must be empty/v1'
      USING ERRCODE = '22023';
  END IF;
  calculated_payload_digest := encode(
    sha256(convert_to(requested_payload::text, 'UTF8')), 'hex'
  );
  IF requested_payload_digest <> calculated_payload_digest THEN
    RAISE EXCEPTION 'payload digest does not match canonical JSON payload'
      USING ERRCODE = '22000';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0)
  );

  SELECT * INTO existing_event
    FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id
      AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    SELECT * INTO existing_case
      FROM investigator.investigation_case
      WHERE tenant_id = requested_tenant_id AND case_id = existing_event.case_id;
    IF existing_event.case_id = requested_case_id
       AND existing_event.event_type = 'CASE_CREATED'
       AND existing_event.event_id = requested_event_id
       AND existing_event.occurred_at = requested_occurred_at
       AND existing_event.actor_type = context_actor_type
       AND existing_event.actor_id = context_actor
       AND existing_event.workload_id IS NOT DISTINCT FROM context_workload
       AND existing_event.payload = requested_payload
       AND existing_event.payload_schema_version = requested_payload_schema_version
       AND existing_event.payload_digest = calculated_payload_digest
       AND existing_event.integrity_metadata = requested_integrity_metadata
       AND existing_case.legacy_case_reference IS NOT DISTINCT FROM requested_legacy_reference
       AND existing_case.cohort_reference IS NOT DISTINCT FROM requested_cohort_reference THEN
      RETURN existing_event.case_id;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing event'
      USING ERRCODE = '23505';
  END IF;

  INSERT INTO investigator.investigation_case (
    case_id, tenant_id, legacy_case_reference, cohort_reference,
    case_version, created_by
  ) VALUES (
    requested_case_id, requested_tenant_id, requested_legacy_reference,
    requested_cohort_reference, 1, context_actor
  );

  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at,
    actor_type, actor_id, workload_id, payload, payload_schema_version,
    idempotency_key, payload_digest, integrity_metadata
  ) VALUES (
    requested_event_id, requested_tenant_id, requested_case_id, 1,
    'CASE_CREATED', requested_occurred_at, context_actor_type, context_actor,
    context_workload, requested_payload,
    requested_payload_schema_version, requested_idempotency_key,
    calculated_payload_digest, requested_integrity_metadata
  );
  RETURN requested_case_id;
END
$function$;

CREATE FUNCTION investigator.append_event(
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
  context_actor text;
  context_actor_type text;
  context_workload text;
  calculated_payload_digest text;
  current_version bigint;
  existing_event investigator.investigation_event%ROWTYPE;
  next_sequence bigint;
BEGIN
  IF NOT investigator.tenant_access_allowed(requested_tenant_id) THEN
    RAISE EXCEPTION 'tenant context is missing or not bound to this login'
      USING ERRCODE = '42501';
  END IF;
  context_actor := nullif(current_setting('olin.actor_id', true), '');
  context_actor_type := nullif(current_setting('olin.actor_type', true), '');
  context_workload := nullif(current_setting('olin.workload_id', true), '');
  IF context_actor IS NULL THEN
    RAISE EXCEPTION 'actor context is required' USING ERRCODE = '42501';
  END IF;
  IF context_actor_type NOT IN ('human', 'system') THEN
    RAISE EXCEPTION 'event append requires human or system actor context'
      USING ERRCODE = '42501';
  END IF;
  IF requested_event_type <> 'INVESTIGATION_EVENT_RECORDED' THEN
    RAISE EXCEPTION 'event type is not allowed in Investigator Phase 0'
      USING ERRCODE = '42501';
  END IF;
  IF requested_payload <> '{}'::jsonb
     OR requested_payload_schema_version <> 1
     OR requested_integrity_metadata <> '{}'::jsonb THEN
    RAISE EXCEPTION 'INVESTIGATION_EVENT_RECORDED Phase 0 payload/schema/metadata must be empty/v1'
      USING ERRCODE = '22023';
  END IF;
  calculated_payload_digest := encode(
    sha256(convert_to(requested_payload::text, 'UTF8')), 'hex'
  );
  IF requested_payload_digest <> calculated_payload_digest THEN
    RAISE EXCEPTION 'payload digest does not match canonical JSON payload'
      USING ERRCODE = '22000';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(requested_tenant_id::text || ':' || requested_idempotency_key, 0)
  );

  SELECT * INTO existing_event
    FROM investigator.investigation_event
    WHERE tenant_id = requested_tenant_id
      AND idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    IF existing_event.case_id = requested_case_id
       AND existing_event.event_type = requested_event_type
       AND existing_event.event_id = requested_event_id
       AND existing_event.occurred_at = requested_occurred_at
       AND existing_event.actor_type = context_actor_type
       AND existing_event.actor_id = context_actor
       AND existing_event.workload_id IS NOT DISTINCT FROM context_workload
       AND existing_event.payload = requested_payload
       AND existing_event.payload_schema_version = requested_payload_schema_version
       AND existing_event.parent_event_id IS NOT DISTINCT FROM requested_parent_event_id
       AND existing_event.causation_event_id IS NOT DISTINCT FROM requested_causation_event_id
       AND existing_event.payload_digest = calculated_payload_digest
       AND existing_event.integrity_metadata = requested_integrity_metadata THEN
      RETURN existing_event.event_sequence;
    END IF;
    RAISE EXCEPTION 'idempotency key conflicts with an existing event'
      USING ERRCODE = '23505';
  END IF;

  SELECT case_version INTO current_version
    FROM investigator.investigation_case
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id
    FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'investigation case not found' USING ERRCODE = 'P0002';
  END IF;
  IF current_version <> expected_case_version THEN
    RAISE EXCEPTION 'stale case version: expected %, current %',
      expected_case_version, current_version USING ERRCODE = '40001';
  END IF;
  next_sequence := current_version + 1;

  INSERT INTO investigator.investigation_event (
    event_id, tenant_id, case_id, event_sequence, event_type, occurred_at,
    actor_type, actor_id, workload_id, payload, payload_schema_version,
    idempotency_key, parent_event_id, causation_event_id, payload_digest,
    integrity_metadata
  ) VALUES (
    requested_event_id, requested_tenant_id, requested_case_id, next_sequence,
    requested_event_type, requested_occurred_at, context_actor_type,
    context_actor, context_workload,
    requested_payload, requested_payload_schema_version,
    requested_idempotency_key, requested_parent_event_id,
    requested_causation_event_id, calculated_payload_digest,
    requested_integrity_metadata
  );

  UPDATE investigator.investigation_case
    SET case_version = next_sequence, updated_at = statement_timestamp()
    WHERE tenant_id = requested_tenant_id AND case_id = requested_case_id;
  RETURN next_sequence;
END
$function$;

REVOKE ALL ON ALL TABLES IN SCHEMA investigator FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA investigator FROM olin_investigator_runtime;
REVOKE ALL ON FUNCTION investigator.create_case(
  uuid, uuid, text, text, uuid, timestamptz, jsonb, integer, text, text, jsonb
) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.append_event(
  uuid, uuid, bigint, uuid, text, timestamptz, jsonb, integer, text,
  text, uuid, uuid, jsonb
) FROM PUBLIC;

GRANT SELECT ON investigator.investigation_case TO olin_investigator_runtime;
GRANT SELECT ON investigator.investigation_event TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.create_case(
  uuid, uuid, text, text, uuid, timestamptz, jsonb, integer, text, text, jsonb
) TO olin_investigator_runtime;
GRANT EXECUTE ON FUNCTION investigator.append_event(
  uuid, uuid, bigint, uuid, text, timestamptz, jsonb, integer, text,
  text, uuid, uuid, jsonb
) TO olin_investigator_runtime;

COMMENT ON TABLE investigator.investigation_case IS
  'Mutable Investigator case projection; never a credit decision, facility, or money authority';
COMMENT ON TABLE investigator.investigation_event IS
  'Append-oriented Investigator history; runtime has no direct INSERT, UPDATE, DELETE, or TRUNCATE';

RESET ROLE;
COMMENT ON ROLE olin_investigator_runtime IS
  'NOLOGIN Phase 0 capability role: Investigator case/event read plus constrained append functions only';
COMMENT ON ROLE olin_investigator_owner IS
  'NOLOGIN non-bypass owner for Investigator schema, tables, policies, and SECURITY DEFINER functions';
DO $remove_owner_membership$
BEGIN
  EXECUTE format('REVOKE olin_investigator_owner FROM %I', current_user);
END
$remove_owner_membership$;
COMMIT;
