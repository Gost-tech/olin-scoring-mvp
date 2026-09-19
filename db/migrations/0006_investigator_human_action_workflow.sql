-- Investigator V1 Phase 5A: human-selected action and append-only history.
-- Phase 3/4 reasoning outputs and canonical evidence bodies are never persisted here.
-- Apply after 0001 through 0005 with the controlled migration owner.

BEGIN;

DO $preflight$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
    RAISE EXCEPTION 'Phase 5A migration requires a controlled superuser migration principal';
  END IF;
  IF to_regclass('investigator.case_snapshot') IS NULL
     OR to_regclass('evidence_authority.investigator_evidence_projection_change') IS NULL
     OR to_regprocedure('investigator.is_snapshot_current(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'Investigator migrations 0001 through 0005 must be applied first';
  END IF;
END
$preflight$;

DO $role$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'olin_investigator_action_writer'
  ) THEN
    CREATE ROLE olin_investigator_action_writer
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
END
$role$;
ALTER ROLE olin_investigator_action_writer
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM olin_investigator_action_writer;

SET SESSION AUTHORIZATION olin_investigator_owner;

CREATE FUNCTION investigator.action_session_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
STABLE
AS $function$
DECLARE
  suffix text;
BEGIN
  IF session_user !~ '^olin_action_t_[0-9a-f]{32}$' THEN
    RETURN NULL;
  END IF;
  suffix := substring(session_user FROM length('olin_action_t_') + 1);
  RETURN (
    substring(suffix FROM 1 FOR 8) || '-' || substring(suffix FROM 9 FOR 4) || '-' ||
    substring(suffix FROM 13 FOR 4) || '-' || substring(suffix FROM 17 FOR 4) || '-' ||
    substring(suffix FROM 21 FOR 12)
  )::uuid;
END
$function$;

CREATE FUNCTION investigator.action_tenant_access_allowed(requested_tenant_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
STABLE
AS $function$
  SELECT requested_tenant_id IS NOT NULL
    AND requested_tenant_id = investigator.action_session_tenant_id()
    AND requested_tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
$function$;

-- The action command must inspect the same tenant-bound current state as reasoning.
-- These additive policies do not grant table access to the login; only the sealed
-- SECURITY DEFINER commands below use them while owned by the non-login owner.
CREATE POLICY investigation_case_action_command_policy
  ON investigator.investigation_case
  FOR SELECT TO olin_investigator_owner
  USING (
    session_user ~ '^olin_action_t_[0-9a-f]{32}$'
    AND replace(tenant_id::text, '-', '') =
      substring(session_user FROM length('olin_action_t_') + 1)
    AND tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
  );
CREATE POLICY case_snapshot_action_command_policy
  ON investigator.case_snapshot
  FOR SELECT TO olin_investigator_owner
  USING (
    session_user ~ '^olin_action_t_[0-9a-f]{32}$'
    AND replace(tenant_id::text, '-', '') =
      substring(session_user FROM length('olin_action_t_') + 1)
    AND tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
  );
CREATE POLICY case_snapshot_invalidation_action_command_policy
  ON investigator.case_snapshot_invalidation
  FOR SELECT TO olin_investigator_owner
  USING (
    session_user ~ '^olin_action_t_[0-9a-f]{32}$'
    AND replace(tenant_id::text, '-', '') =
      substring(session_user FROM length('olin_action_t_') + 1)
    AND tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
  );
CREATE POLICY evidence_projection_action_command_policy
  ON evidence_authority.investigator_evidence_projection_change
  FOR SELECT TO olin_investigator_owner
  USING (
    session_user ~ '^olin_action_t_[0-9a-f]{32}$'
    AND replace(tenant_id::text, '-', '') =
      substring(session_user FROM length('olin_action_t_') + 1)
    AND tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
  );
CREATE POLICY evidence_reference_action_command_policy
  ON investigator.investigation_evidence_reference
  FOR SELECT TO olin_investigator_owner
  USING (
    session_user ~ '^olin_action_t_[0-9a-f]{32}$'
    AND replace(tenant_id::text, '-', '') =
      substring(session_user FROM length('olin_action_t_') + 1)
    AND tenant_id = nullif(current_setting('olin.tenant_id', true), '')::uuid
  );

CREATE TABLE investigator.investigation_action (
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL,
  action_id uuid NOT NULL,
  action_type text NOT NULL CHECK (action_type IN (
    'REQUEST_ACCOUNT_CHANNEL_RECORD',
    'CLARIFY_MERCHANT_ASSERTION_SCOPE'
  )),
  question_id text NOT NULL CHECK (octet_length(question_id) BETWEEN 1 AND 120),
  unresolved_question text NOT NULL CHECK (
    octet_length(unresolved_question) BETWEEN 1 AND 1000
  ),
  purpose text NOT NULL CHECK (octet_length(purpose) BETWEEN 1 AND 1000),
  permitted_data_scope text NOT NULL CHECK (
    octet_length(permitted_data_scope) BETWEEN 1 AND 1000
  ),
  requested_source text NOT NULL CHECK (
    octet_length(requested_source) BETWEEN 1 AND 1000
  ),
  prerequisites jsonb NOT NULL CHECK (
    jsonb_typeof(prerequisites) = 'array' AND jsonb_array_length(prerequisites) > 0
  ),
  resolution_criteria jsonb NOT NULL CHECK (
    jsonb_typeof(resolution_criteria) = 'array'
    AND jsonb_array_length(resolution_criteria) > 0
  ),
  relevant_finding_references jsonb NOT NULL CHECK (
    jsonb_typeof(relevant_finding_references) = 'array'
  ),
  analyst_rationale text NOT NULL CHECK (
    octet_length(analyst_rationale) BETWEEN 1 AND 1000
  ),
  selected_snapshot_id uuid NOT NULL,
  selected_snapshot_digest text NOT NULL CHECK (
    selected_snapshot_digest ~ '^[0-9a-f]{64}$'
  ),
  selected_authority_revision bigint NOT NULL CHECK (selected_authority_revision >= 0),
  selected_authority_digest text NOT NULL CHECK (
    selected_authority_digest ~ '^[0-9a-f]{64}$'
  ),
  selected_evidence_state_digest text NOT NULL CHECK (
    selected_evidence_state_digest ~ '^[0-9a-f]{64}$'
  ),
  selected_assessment_digest text NOT NULL CHECK (
    selected_assessment_digest ~ '^[0-9a-f]{64}$'
  ),
  phase3_rules_version text NOT NULL,
  phase3_schema_version text NOT NULL CHECK (octet_length(phase3_schema_version) > 0),
  phase4_rules_version text NOT NULL,
  phase4_schema_version text NOT NULL CHECK (octet_length(phase4_schema_version) > 0),
  catalogue_version text NOT NULL CHECK (
    catalogue_version = 'investigator-action-catalogue-1.0'
  ),
  action_schema_version integer NOT NULL CHECK (action_schema_version = 1),
  selected_by text NOT NULL,
  selected_by_analyst text NOT NULL CHECK (
    octet_length(selected_by_analyst) BETWEEN 1 AND 240
  ),
  selected_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  idempotency_key text NOT NULL CHECK (octet_length(idempotency_key) BETWEEN 1 AND 240),
  selection_digest text NOT NULL CHECK (selection_digest ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, action_id),
  UNIQUE (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, case_id)
    REFERENCES investigator.investigation_case (tenant_id, case_id),
  FOREIGN KEY (tenant_id, case_id, selected_snapshot_id)
    REFERENCES investigator.case_snapshot (tenant_id, case_id, snapshot_id)
);

CREATE TABLE investigator.investigation_action_transition (
  tenant_id uuid NOT NULL,
  action_id uuid NOT NULL,
  transition_sequence bigint NOT NULL CHECK (transition_sequence > 0),
  from_status text,
  to_status text NOT NULL CHECK (to_status IN (
    'SELECTED', 'REQUESTED', 'RESPONSE_RECEIVED', 'EVIDENCE_ACCEPTED',
    'COMPLETED_RESOLVED', 'COMPLETED_UNRESOLVED', 'STOPPED', 'ESCALATED'
  )),
  reason_code text CHECK (reason_code IS NULL OR reason_code IN (
    'EVIDENCE_UNAVAILABLE', 'PERMISSION_MISSING_OR_WITHDRAWN',
    'QUESTION_STILL_UNRESOLVED', 'FURTHER_INVESTIGATION_NOT_JUSTIFIED',
    'SYNTHETIC_DEMO_LIMIT_REACHED'
  )),
  reason_detail text CHECK (
    reason_detail IS NULL OR octet_length(reason_detail) BETWEEN 1 AND 1000
  ),
  evidence_references jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(evidence_references) = 'array'
  ),
  actual_effort_minutes integer CHECK (
    actual_effort_minutes IS NULL OR actual_effort_minutes BETWEEN 0 AND 100000
  ),
  actual_cost_amount numeric CHECK (
    actual_cost_amount IS NULL OR actual_cost_amount BETWEEN 0 AND 1000000000
  ),
  actual_cost_currency text CHECK (
    (actual_cost_amount IS NULL AND actual_cost_currency IS NULL)
    OR (actual_cost_amount IS NOT NULL AND actual_cost_currency IN ('MXN', 'USD'))
  ),
  transitioned_by text NOT NULL,
  transitioned_by_analyst text NOT NULL CHECK (
    octet_length(transitioned_by_analyst) BETWEEN 1 AND 240
  ),
  transitioned_at timestamptz NOT NULL DEFAULT statement_timestamp(),
  idempotency_key text NOT NULL CHECK (octet_length(idempotency_key) BETWEEN 1 AND 240),
  transition_digest text NOT NULL CHECK (transition_digest ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, action_id, transition_sequence),
  UNIQUE (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, action_id)
    REFERENCES investigator.investigation_action (tenant_id, action_id)
);

ALTER TABLE investigator.investigation_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_action FORCE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_action_transition ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator.investigation_action_transition FORCE ROW LEVEL SECURITY;
CREATE POLICY investigation_action_tenant_policy
  ON investigator.investigation_action
  FOR ALL TO olin_investigator_owner
  USING (investigator.action_tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.action_tenant_access_allowed(tenant_id));
CREATE POLICY investigation_action_transition_tenant_policy
  ON investigator.investigation_action_transition
  FOR ALL TO olin_investigator_owner
  USING (investigator.action_tenant_access_allowed(tenant_id))
  WITH CHECK (investigator.action_tenant_access_allowed(tenant_id));

CREATE FUNCTION investigator.prevent_action_history_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
BEGIN
  RAISE EXCEPTION 'Investigator action history is append-only' USING ERRCODE = '55000';
END
$function$;
CREATE TRIGGER investigation_action_immutable
BEFORE UPDATE OR DELETE ON investigator.investigation_action
FOR EACH ROW EXECUTE FUNCTION investigator.prevent_action_history_mutation();
CREATE TRIGGER investigation_action_transition_immutable
BEFORE UPDATE OR DELETE ON investigator.investigation_action_transition
FOR EACH ROW EXECUTE FUNCTION investigator.prevent_action_history_mutation();

CREATE FUNCTION investigator.prevent_action_history_truncate()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
BEGIN
  RAISE EXCEPTION 'Investigator action history cannot be truncated' USING ERRCODE = '55000';
END
$function$;
CREATE TRIGGER investigation_action_no_truncate
BEFORE TRUNCATE ON investigator.investigation_action
FOR EACH STATEMENT EXECUTE FUNCTION investigator.prevent_action_history_truncate();
CREATE TRIGGER investigation_action_transition_no_truncate
BEFORE TRUNCATE ON investigator.investigation_action_transition
FOR EACH STATEMENT EXECUTE FUNCTION investigator.prevent_action_history_truncate();

CREATE FUNCTION investigator.require_action_writer(requested_tenant_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
BEGIN
  IF NOT pg_has_role(session_user, 'olin_investigator_action_writer', 'member')
     OR pg_has_role(session_user, 'olin_investigator_runtime', 'member')
     OR pg_has_role(session_user, 'olin_investigator_evidence_authority', 'member')
     OR pg_has_role(session_user, 'olin_investigator_owner', 'member')
     OR NOT investigator.action_tenant_access_allowed(requested_tenant_id)
     OR EXISTS (
       SELECT 1 FROM pg_roles login WHERE login.rolname = session_user
       AND (login.rolsuper OR login.rolcreaterole OR login.rolcreatedb
            OR login.rolreplication OR login.rolbypassrls)
     )
     OR EXISTS (
       WITH RECURSIVE memberships(roleid) AS (
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN pg_roles login ON login.oid = membership.member
         WHERE login.rolname = session_user UNION
         SELECT membership.roleid FROM pg_auth_members membership
         JOIN memberships prior ON membership.member = prior.roleid
       )
       SELECT 1 FROM memberships JOIN pg_roles granted
       ON granted.oid = memberships.roleid
       WHERE granted.rolname <> 'olin_investigator_action_writer'
     ) THEN
    RAISE EXCEPTION 'isolated tenant-bound action writer is required'
      USING ERRCODE = '42501';
  END IF;
END
$function$;

CREATE FUNCTION investigator.select_investigation_action(
  requested_tenant_id uuid,
  requested_case_id uuid,
  requested_action_id uuid,
  requested_snapshot_id uuid,
  requested_snapshot_digest text,
  requested_authority_revision bigint,
  requested_authority_digest text,
  requested_evidence_state_digest text,
  requested_assessment_digest text,
  requested_phase3_rules_version text,
  requested_phase3_schema_version text,
  requested_phase4_rules_version text,
  requested_phase4_schema_version text,
  requested_action_type text,
  requested_question_id text,
  requested_unresolved_question text,
  requested_purpose text,
  requested_permitted_data_scope text,
  requested_source text,
  requested_prerequisites jsonb,
  requested_resolution_criteria jsonb,
  requested_finding_references jsonb,
  requested_rationale text,
  requested_analyst_name text,
  requested_idempotency_key text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator, evidence_authority
AS $function$
DECLARE
  snapshot investigator.case_snapshot%ROWTYPE;
  current_revision bigint;
  current_digest text;
  request_digest text;
  existing investigator.investigation_action%ROWTYPE;
BEGIN
  PERFORM investigator.require_action_writer(requested_tenant_id);
  PERFORM pg_advisory_xact_lock(hashtextextended(
    requested_tenant_id::text || ':reasoning-currentness:' || requested_case_id::text, 0
  ));
  request_digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'action_id', requested_action_id::text, 'action_type', requested_action_type,
    'assessment_digest', requested_assessment_digest,
    'authority_digest', requested_authority_digest,
    'authority_revision', requested_authority_revision,
    'case_id', requested_case_id::text,
    'evidence_state_digest', requested_evidence_state_digest,
    'finding_references', requested_finding_references,
    'permitted_data_scope', requested_permitted_data_scope,
    'phase3_rules_version', requested_phase3_rules_version,
    'phase3_schema_version', requested_phase3_schema_version,
    'phase4_rules_version', requested_phase4_rules_version,
    'phase4_schema_version', requested_phase4_schema_version,
    'prerequisites', requested_prerequisites, 'purpose', requested_purpose,
    'question_id', requested_question_id, 'rationale', requested_rationale,
    'analyst_name', requested_analyst_name,
    'requested_source', requested_source,
    'resolution_criteria', requested_resolution_criteria,
    'snapshot_digest', requested_snapshot_digest,
    'snapshot_id', requested_snapshot_id::text,
    'tenant_id', requested_tenant_id::text,
    'unresolved_question', requested_unresolved_question
  )), 'UTF8')), 'hex');
  SELECT action.* INTO existing FROM investigator.investigation_action action
  WHERE action.tenant_id = requested_tenant_id
    AND action.idempotency_key = requested_idempotency_key;
  IF FOUND THEN
    IF existing.selection_digest = request_digest THEN RETURN existing.action_id; END IF;
    RAISE EXCEPTION 'action idempotency key conflicts with history' USING ERRCODE='23505';
  END IF;
  SELECT stored.* INTO snapshot FROM investigator.case_snapshot stored
  WHERE stored.tenant_id=requested_tenant_id AND stored.case_id=requested_case_id
    AND stored.snapshot_id=requested_snapshot_id AND stored.snapshot_schema_version=2;
  IF NOT FOUND OR snapshot.canonical_digest <> requested_snapshot_digest
     OR snapshot.event_head_sequence IS DISTINCT FROM (
       SELECT stored_case.case_version FROM investigator.investigation_case stored_case
       WHERE stored_case.tenant_id=requested_tenant_id
         AND stored_case.case_id=requested_case_id
     ) OR EXISTS (
       SELECT 1 FROM investigator.case_snapshot_invalidation invalidation
       WHERE invalidation.tenant_id=requested_tenant_id
         AND invalidation.case_id=requested_case_id
         AND invalidation.snapshot_id=requested_snapshot_id
     ) THEN
    RAISE EXCEPTION 'selected snapshot is stale or mismatched' USING ERRCODE='40001';
  END IF;
  SELECT change.authority_revision, change.authority_state_digest
    INTO current_revision, current_digest
  FROM evidence_authority.investigator_evidence_projection_change change
  WHERE change.tenant_id=requested_tenant_id AND change.case_id=requested_case_id
  ORDER BY change.authority_revision DESC LIMIT 1;
  current_revision := coalesce(current_revision, 0);
  current_digest := coalesce(current_digest, repeat('0',64));
  IF requested_authority_revision IS DISTINCT FROM current_revision
     OR requested_authority_digest IS DISTINCT FROM current_digest
     OR snapshot.canonical_snapshot_payload #>> '{canonical_authority,authority_revision}'
        IS DISTINCT FROM current_revision::text
     OR snapshot.canonical_snapshot_payload #>> '{canonical_authority,authority_state_digest}'
        IS DISTINCT FROM current_digest
     OR snapshot.canonical_snapshot_payload #>> '{evidence,evidence_state_digest}'
        IS DISTINCT FROM requested_evidence_state_digest THEN
    RAISE EXCEPTION 'selected authority or evidence state is stale' USING ERRCODE='40001';
  END IF;
  IF requested_action_type NOT IN (
       'REQUEST_ACCOUNT_CHANNEL_RECORD', 'CLARIFY_MERCHANT_ASSERTION_SCOPE')
     OR requested_phase3_rules_version = '' OR requested_phase4_rules_version = ''
     OR requested_phase3_schema_version = '' OR requested_phase4_schema_version = ''
     OR octet_length(btrim(requested_analyst_name)) NOT BETWEEN 1 AND 240
     OR requested_analyst_name <> btrim(requested_analyst_name)
     OR octet_length(btrim(requested_rationale)) NOT BETWEEN 1 AND 1000
     OR requested_rationale <> btrim(requested_rationale)
     OR jsonb_typeof(requested_prerequisites) <> 'array'
     OR jsonb_typeof(requested_resolution_criteria) <> 'array'
     OR jsonb_typeof(requested_finding_references) <> 'array' THEN
    RAISE EXCEPTION 'action selection payload is invalid' USING ERRCODE='22023';
  END IF;
  INSERT INTO investigator.investigation_action (
    tenant_id,case_id,action_id,action_type,question_id,unresolved_question,
    purpose,permitted_data_scope,requested_source,prerequisites,resolution_criteria,
    relevant_finding_references,analyst_rationale,selected_snapshot_id,
    selected_snapshot_digest,selected_authority_revision,selected_authority_digest,
    selected_evidence_state_digest,selected_assessment_digest,phase3_rules_version,
    phase3_schema_version,phase4_rules_version,phase4_schema_version,catalogue_version,
    action_schema_version,selected_by,selected_by_analyst,idempotency_key,
    selection_digest
  ) VALUES (
    requested_tenant_id,requested_case_id,requested_action_id,requested_action_type,
    requested_question_id,requested_unresolved_question,requested_purpose,
    requested_permitted_data_scope,requested_source,requested_prerequisites,
    requested_resolution_criteria,requested_finding_references,requested_rationale,
    requested_snapshot_id,requested_snapshot_digest,requested_authority_revision,
    requested_authority_digest,requested_evidence_state_digest,
    requested_assessment_digest,requested_phase3_rules_version,
    requested_phase3_schema_version,requested_phase4_rules_version,
    requested_phase4_schema_version,'investigator-action-catalogue-1.0',1,
    session_user,requested_analyst_name,requested_idempotency_key,request_digest
  );
  INSERT INTO investigator.investigation_action_transition (
    tenant_id,action_id,transition_sequence,from_status,to_status,transitioned_by,
    transitioned_by_analyst,idempotency_key,transition_digest
  ) VALUES (
    requested_tenant_id,requested_action_id,1,NULL,'SELECTED',session_user,
    requested_analyst_name,requested_idempotency_key || ':selected',encode(sha256(convert_to(
      request_digest || ':SELECTED','UTF8')),'hex')
  );
  RETURN requested_action_id;
END
$function$;

CREATE FUNCTION investigator.transition_investigation_action(
  requested_tenant_id uuid,
  requested_action_id uuid,
  expected_transition_sequence bigint,
  requested_to_status text,
  requested_reason_code text,
  requested_reason_detail text,
  requested_evidence_references jsonb,
  requested_actual_effort_minutes integer,
  requested_actual_cost_amount numeric,
  requested_actual_cost_currency text,
  requested_analyst_name text,
  requested_idempotency_key text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
AS $function$
DECLARE
  current_transition investigator.investigation_action_transition%ROWTYPE;
  existing investigator.investigation_action_transition%ROWTYPE;
  next_sequence bigint;
  digest text;
  allowed boolean := false;
BEGIN
  PERFORM investigator.require_action_writer(requested_tenant_id);
  PERFORM pg_advisory_xact_lock(hashtextextended(
    requested_tenant_id::text || ':action:' || requested_action_id::text, 0
  ));
  digest := encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object(
    'action_id',requested_action_id::text,'cost_amount',requested_actual_cost_amount,
    'cost_currency',requested_actual_cost_currency,'effort_minutes',requested_actual_effort_minutes,
    'evidence_references',requested_evidence_references,'expected_sequence',expected_transition_sequence,
    'reason_code',requested_reason_code,'reason_detail',requested_reason_detail,
    'analyst_name',requested_analyst_name,
    'tenant_id',requested_tenant_id::text,'to_status',requested_to_status
  )),'UTF8')),'hex');
  SELECT item.* INTO existing FROM investigator.investigation_action_transition item
  WHERE item.tenant_id=requested_tenant_id AND item.idempotency_key=requested_idempotency_key;
  IF FOUND THEN
    IF existing.transition_digest=digest THEN RETURN existing.transition_sequence; END IF;
    RAISE EXCEPTION 'transition idempotency key conflicts with history' USING ERRCODE='23505';
  END IF;
  SELECT item.* INTO current_transition
  FROM investigator.investigation_action_transition item
  WHERE item.tenant_id=requested_tenant_id AND item.action_id=requested_action_id
  ORDER BY item.transition_sequence DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'investigation action not found' USING ERRCODE='P0002'; END IF;
  IF current_transition.transition_sequence <> expected_transition_sequence THEN
    RAISE EXCEPTION 'stale action transition sequence' USING ERRCODE='40001';
  END IF;
  allowed := CASE current_transition.to_status
    WHEN 'SELECTED' THEN requested_to_status IN ('REQUESTED','STOPPED','ESCALATED')
    WHEN 'REQUESTED' THEN requested_to_status IN ('RESPONSE_RECEIVED','STOPPED','ESCALATED')
    WHEN 'RESPONSE_RECEIVED' THEN requested_to_status IN ('EVIDENCE_ACCEPTED','COMPLETED_UNRESOLVED','STOPPED','ESCALATED')
    WHEN 'EVIDENCE_ACCEPTED' THEN requested_to_status IN ('COMPLETED_UNRESOLVED','ESCALATED')
    ELSE false END;
  IF NOT allowed THEN RAISE EXCEPTION 'invalid action status transition' USING ERRCODE='22023'; END IF;
  IF requested_to_status IN ('STOPPED','ESCALATED','COMPLETED_UNRESOLVED') THEN
    IF requested_reason_code NOT IN (
      'EVIDENCE_UNAVAILABLE','PERMISSION_MISSING_OR_WITHDRAWN','QUESTION_STILL_UNRESOLVED',
      'FURTHER_INVESTIGATION_NOT_JUSTIFIED','SYNTHETIC_DEMO_LIMIT_REACHED') THEN
      RAISE EXCEPTION 'terminal unresolved transition requires a closed reason' USING ERRCODE='22023';
    END IF;
  ELSIF requested_reason_code IS NOT NULL THEN
    RAISE EXCEPTION 'this transition does not accept a stop reason' USING ERRCODE='22023';
  END IF;
  IF jsonb_typeof(requested_evidence_references) <> 'array'
     OR octet_length(btrim(requested_analyst_name)) NOT BETWEEN 1 AND 240
     OR requested_analyst_name <> btrim(requested_analyst_name)
     OR (requested_actual_cost_amount IS NULL) <> (requested_actual_cost_currency IS NULL) THEN
    RAISE EXCEPTION 'transition metadata is invalid' USING ERRCODE='22023';
  END IF;
  next_sequence := expected_transition_sequence + 1;
  IF requested_to_status = 'EVIDENCE_ACCEPTED' AND (
    jsonb_array_length(requested_evidence_references) = 0 OR EXISTS (
      SELECT 1 FROM jsonb_array_elements_text(requested_evidence_references) reference
      WHERE reference.value !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         OR NOT EXISTS (
           SELECT 1 FROM investigator.investigation_action action
           JOIN investigator.investigation_evidence_reference accepted
             ON accepted.tenant_id=action.tenant_id
            AND accepted.case_id=action.case_id
           JOIN investigator.investigation_case stored_case
             ON stored_case.tenant_id=accepted.tenant_id
            AND stored_case.case_id=accepted.case_id
           JOIN investigator.case_snapshot snapshot
             ON snapshot.tenant_id=stored_case.tenant_id
            AND snapshot.case_id=stored_case.case_id
            AND snapshot.event_head_sequence=stored_case.case_version
            AND snapshot.snapshot_schema_version=2
           JOIN investigator.case_snapshot selected_snapshot
             ON selected_snapshot.tenant_id=action.tenant_id
            AND selected_snapshot.case_id=action.case_id
            AND selected_snapshot.snapshot_id=action.selected_snapshot_id
           WHERE action.tenant_id=requested_tenant_id
             AND action.action_id=requested_action_id
             AND action.action_type='REQUEST_ACCOUNT_CHANNEL_RECORD'
             AND accepted.reference_id=reference.value::uuid
             AND accepted.proposition_type='bank_account_coverage'
             AND accepted.evidence_id='fixture-account-coverage-' || action.action_id::text
             AND EXISTS (
               SELECT 1 FROM jsonb_array_elements(
                 snapshot.canonical_snapshot_payload #> '{evidence,accepted_evidence_refs}'
               ) snapshot_reference
               WHERE snapshot_reference ->> 'reference_id' = reference.value
             )
             AND NOT EXISTS (
               SELECT 1 FROM jsonb_array_elements(
                 selected_snapshot.canonical_snapshot_payload #> '{evidence,accepted_evidence_refs}'
               ) selected_reference
               WHERE selected_reference ->> 'reference_id' = reference.value
             )
             AND NOT EXISTS (
               SELECT 1 FROM investigator.case_snapshot_invalidation invalidation
               WHERE invalidation.tenant_id=snapshot.tenant_id
                 AND invalidation.case_id=snapshot.case_id
                 AND invalidation.snapshot_id=snapshot.snapshot_id
             )
         )
    )
  ) THEN
    RAISE EXCEPTION 'accepted evidence must be an action-bound canonical snapshot delta'
      USING ERRCODE='42501';
  END IF;
  INSERT INTO investigator.investigation_action_transition (
    tenant_id,action_id,transition_sequence,from_status,to_status,reason_code,
    reason_detail,evidence_references,actual_effort_minutes,actual_cost_amount,
    actual_cost_currency,transitioned_by,transitioned_by_analyst,idempotency_key,
    transition_digest
  ) VALUES (
    requested_tenant_id,requested_action_id,next_sequence,current_transition.to_status,
    requested_to_status,requested_reason_code,requested_reason_detail,
    requested_evidence_references,requested_actual_effort_minutes,
    requested_actual_cost_amount,requested_actual_cost_currency,session_user,
    requested_analyst_name,requested_idempotency_key,digest
  );
  RETURN next_sequence;
END
$function$;

CREATE FUNCTION investigator.read_investigation_actions(
  requested_tenant_id uuid, requested_case_id uuid
)
RETURNS TABLE(action jsonb, transitions jsonb)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, investigator
STABLE
AS $function$
BEGIN
  PERFORM investigator.require_action_writer(requested_tenant_id);
  RETURN QUERY
  SELECT to_jsonb(item), coalesce((
    SELECT jsonb_agg(to_jsonb(history) ORDER BY history.transition_sequence)
    FROM investigator.investigation_action_transition history
    WHERE history.tenant_id=item.tenant_id AND history.action_id=item.action_id
  ), '[]'::jsonb)
  FROM investigator.investigation_action item
  WHERE item.tenant_id=requested_tenant_id AND item.case_id=requested_case_id
  ORDER BY item.selected_at, item.action_id;
END
$function$;

REVOKE ALL ON TABLE investigator.investigation_action FROM PUBLIC;
REVOKE ALL ON TABLE investigator.investigation_action_transition FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.action_session_tenant_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.action_tenant_access_allowed(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.require_action_writer(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.select_investigation_action(
  uuid,uuid,uuid,uuid,text,bigint,text,text,text,text,text,text,text,text,text,
  text,text,text,text,jsonb,jsonb,jsonb,text,text,text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.transition_investigation_action(
  uuid,uuid,bigint,text,text,text,jsonb,integer,numeric,text,text,text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION investigator.read_investigation_actions(uuid,uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA investigator TO olin_investigator_action_writer;
GRANT EXECUTE ON FUNCTION investigator.action_session_tenant_id()
  TO olin_investigator_action_writer;
GRANT EXECUTE ON FUNCTION investigator.action_tenant_access_allowed(uuid)
  TO olin_investigator_action_writer;
GRANT EXECUTE ON FUNCTION investigator.select_investigation_action(
  uuid,uuid,uuid,uuid,text,bigint,text,text,text,text,text,text,text,text,text,
  text,text,text,text,jsonb,jsonb,jsonb,text,text,text
) TO olin_investigator_action_writer;
GRANT EXECUTE ON FUNCTION investigator.transition_investigation_action(
  uuid,uuid,bigint,text,text,text,jsonb,integer,numeric,text,text,text
) TO olin_investigator_action_writer;
GRANT EXECUTE ON FUNCTION investigator.read_investigation_actions(uuid,uuid)
  TO olin_investigator_action_writer;

RESET SESSION AUTHORIZATION;
COMMIT;
