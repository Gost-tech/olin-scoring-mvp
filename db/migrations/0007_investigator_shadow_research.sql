-- Additive synthetic research only. No change to canonical or action authority.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper) THEN
    RAISE EXCEPTION 'controlled migration owner required';
  END IF;
END $$;
CREATE ROLE olin_investigator_research NOLOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
SET SESSION AUTHORIZATION olin_investigator_owner;

CREATE FUNCTION investigator.research_tenant_allowed(t uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT session_user = 'olin_research_t_' || replace(t::text,'-','')
 AND nullif(current_setting('olin.tenant_id',true),'')::uuid=t
$$;

CREATE FUNCTION investigator.require_research(t uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
BEGIN
 IF NOT investigator.research_tenant_allowed(t)
 OR NOT pg_has_role(session_user,'olin_investigator_research','member')
 OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND
   (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
 OR EXISTS(WITH RECURSIVE memberships(roleid) AS (
   SELECT m.roleid FROM pg_auth_members m JOIN pg_roles l ON l.oid=m.member WHERE l.rolname=session_user
   UNION SELECT m.roleid FROM pg_auth_members m JOIN memberships p ON m.member=p.roleid)
   SELECT 1 FROM memberships JOIN pg_roles g ON g.oid=roleid WHERE g.rolname<>'olin_investigator_research')
 THEN RAISE EXCEPTION 'isolated research custody required' USING ERRCODE='42501'; END IF;
END $$;

DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['investigator.investigation_case','investigator.case_snapshot',
 'investigator.case_snapshot_invalidation','investigator.investigation_action',
 'investigator.investigation_action_transition',
 'evidence_authority.investigator_evidence_projection_change'] LOOP
   EXECUTE format('CREATE POLICY shadow_read ON %s FOR SELECT TO olin_investigator_owner '
     'USING (session_user = ''olin_research_t_'' || replace(tenant_id::text,''-'','''') '
     'AND tenant_id = nullif(current_setting(''olin.tenant_id'',true),'''')::uuid)',tab);
 END LOOP;
END $$;

CREATE TABLE investigator.shadow_round (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, round_id uuid NOT NULL,
 analyst text NOT NULL CHECK (length(analyst) BETWEEN 1 AND 240),
 created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 binding jsonb NOT NULL, context jsonb NOT NULL, manifest jsonb NOT NULL,
 context_digest text NOT NULL, prompt_digest text NOT NULL, schema_digest text NOT NULL,
 PRIMARY KEY(tenant_id,round_id),
 FOREIGN KEY(tenant_id,case_id) REFERENCES investigator.investigation_case(tenant_id,case_id),
 CHECK (octet_length(context::text)<=32000),
 CHECK (context->>'schema_version'='shadow-context-1'),
 CHECK (context->>'synthetic_only'='true')
);
CREATE TABLE investigator.shadow_event (
 tenant_id uuid NOT NULL, round_id uuid NOT NULL, sequence bigint NOT NULL,
 kind text NOT NULL CHECK(kind IN ('HUMAN_SELECTED','STARTED','FINISHED','DISCLOSED','EXCLUDED','RATED')),
 payload jsonb NOT NULL CHECK(octet_length(payload::text)<=20000),
 actor text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 command_key text NOT NULL CHECK(length(command_key) BETWEEN 1 AND 200),
 PRIMARY KEY(tenant_id,round_id,sequence), UNIQUE(tenant_id,round_id,command_key),
 FOREIGN KEY(tenant_id,round_id) REFERENCES investigator.shadow_round(tenant_id,round_id)
);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['shadow_round','shadow_event'] LOOP
   EXECUTE format('ALTER TABLE investigator.%I ENABLE ROW LEVEL SECURITY',tab);
   EXECUTE format('ALTER TABLE investigator.%I FORCE ROW LEVEL SECURITY',tab);
   EXECUTE format('CREATE POLICY tenant_policy ON investigator.%I TO olin_investigator_owner '
     'USING(investigator.research_tenant_allowed(tenant_id)) '
     'WITH CHECK(investigator.research_tenant_allowed(tenant_id))',tab);
   EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON investigator.%I '
     'FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation()',tab);
   EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON investigator.%I '
     'FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation()',tab);
 END LOOP;
END $$;

CREATE FUNCTION investigator.shadow_assert_current(t uuid,c uuid,b jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE s investigator.case_snapshot%ROWTYPE; rev bigint; dig text;
BEGIN
 PERFORM investigator.require_research(t);
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':reasoning-currentness:'||c::text,0));
 SELECT * INTO s FROM investigator.case_snapshot WHERE tenant_id=t AND case_id=c
 AND snapshot_id=(b->>'snapshot_id')::uuid;
 IF NOT FOUND OR s.snapshot_schema_version<>2 OR s.canonical_digest IS DISTINCT FROM b->>'snapshot_digest'
 OR s.event_head_sequence IS DISTINCT FROM (SELECT case_version FROM investigator.investigation_case WHERE tenant_id=t AND case_id=c)
 OR EXISTS(SELECT 1 FROM investigator.case_snapshot_invalidation WHERE tenant_id=t AND snapshot_id=s.snapshot_id) THEN
   RAISE EXCEPTION 'stale research snapshot' USING ERRCODE='40001';
 END IF;
 SELECT authority_revision,authority_state_digest INTO rev,dig
 FROM evidence_authority.investigator_evidence_projection_change WHERE tenant_id=t AND case_id=c
 ORDER BY authority_revision DESC LIMIT 1;
 IF b->>'tenant_id' IS DISTINCT FROM t::text OR b->>'case_id' IS DISTINCT FROM c::text
 OR (b->>'authority_revision')::bigint IS DISTINCT FROM coalesce(rev,0)
 OR b->>'authority_digest' IS DISTINCT FROM coalesce(dig,repeat('0',64))
 OR s.canonical_snapshot_payload #>> '{evidence,evidence_state_digest}' IS DISTINCT FROM b->>'evidence_state_digest'
 THEN RAISE EXCEPTION 'stale research authority' USING ERRCODE='40001'; END IF;
END $$;

CREATE FUNCTION investigator.shadow_read(t uuid,c uuid,r uuid,a text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE result jsonb;
BEGIN
 PERFORM investigator.require_research(t);
 SELECT to_jsonb(s) || jsonb_build_object('events',coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY sequence)
 FROM investigator.shadow_event e WHERE e.tenant_id=t AND e.round_id=s.round_id),'[]'::jsonb))
 INTO result FROM investigator.shadow_round s WHERE s.tenant_id=t AND s.case_id=c AND (r IS NULL OR s.round_id=r) AND s.analyst=a;
 RETURN result;
END $$;

CREATE FUNCTION investigator.shadow_command(t uuid,c uuid,r uuid,a text,op text,p jsonb,k text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE stored investigator.shadow_round%ROWTYPE; prior investigator.shadow_event%ROWTYPE;
 human investigator.investigation_action%ROWTYPE; seq bigint; started timestamptz;
BEGIN
 PERFORM investigator.require_research(t);
 IF NOT investigator.research_tenant_allowed(t) OR length(a) NOT BETWEEN 1 AND 240 THEN
 RAISE EXCEPTION 'research principal denied' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':shadow:'||r::text,0));
 SELECT * INTO stored FROM investigator.shadow_round WHERE tenant_id=t AND round_id=r;
 IF op='CREATE' THEN
   IF FOUND THEN
     IF stored.case_id<>c OR stored.analyst<>a THEN RAISE EXCEPTION 'round conflict'; END IF;
     RETURN investigator.shadow_read(t,c,r,a);
   END IF;
   PERFORM investigator.shadow_assert_current(t,c,p->'binding');
   IF EXISTS(SELECT 1 FROM investigator.shadow_round WHERE tenant_id=t AND case_id=c AND analyst=a) THEN
     RAISE EXCEPTION 'one blinded round per analyst/case in bounded V1';
   END IF;
   IF (SELECT count(*) FROM jsonb_object_keys(p))<>6
   OR NOT p ?& ARRAY['binding','context','manifest','context_digest','prompt_digest','schema_digest'] THEN
     RAISE EXCEPTION 'invalid round shape';
   END IF;
   INSERT INTO investigator.shadow_round VALUES(t,c,r,a,statement_timestamp(),p->'binding',p->'context',p->'manifest',
     encode(sha256(convert_to(investigator.canonical_json(p->'context'),'UTF8')),'hex'),p->>'prompt_digest',p->>'schema_digest');
   RETURN investigator.shadow_read(t,c,r,a);
 END IF;
 IF stored.round_id IS NULL OR stored.case_id<>c OR stored.analyst<>a THEN RAISE EXCEPTION 'round denied' USING ERRCODE='42501'; END IF;
 IF op='DISCLOSED' THEN PERFORM investigator.shadow_assert_current(t,c,stored.binding); END IF;
 SELECT * INTO prior FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND command_key=k;
 IF FOUND THEN
   IF prior.kind<>op OR prior.payload<>p THEN RAISE EXCEPTION 'research replay conflict' USING ERRCODE='23505'; END IF;
   RETURN investigator.shadow_read(t,c,r,a);
 END IF;
 IF op='HUMAN_SELECTED' THEN
   PERFORM investigator.shadow_assert_current(t,c,stored.binding);
   SELECT * INTO human FROM investigator.investigation_action WHERE tenant_id=t AND case_id=c AND action_id=(p->>'action_id')::uuid;
   IF NOT FOUND OR human.selected_by_analyst<>a OR human.selected_at<stored.created_at
   OR human.selected_snapshot_id::text<>stored.binding->>'snapshot_id'
   OR human.selected_authority_digest<>stored.binding->>'authority_digest'
   OR EXISTS(SELECT 1 FROM investigator.investigation_action earlier
     WHERE earlier.tenant_id=t AND earlier.case_id=c AND earlier.selected_by_analyst=a
     AND earlier.selected_at>=stored.created_at AND earlier.selected_at<human.selected_at)
   OR EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind IN ('HUMAN_SELECTED','DISCLOSED')) THEN
     RAISE EXCEPTION 'invalid blinded human baseline';
   END IF;
 ELSIF op='STARTED' THEN
   PERFORM investigator.shadow_assert_current(t,c,stored.binding);
   IF EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='STARTED') THEN RAISE EXCEPTION 'one attempt only'; END IF;
 ELSIF op='FINISHED' THEN
   SELECT recorded_at INTO started FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='STARTED';
   IF started IS NULL OR EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='FINISHED') THEN RAISE EXCEPTION 'invalid attempt completion'; END IF;
   IF p->>'status' NOT IN ('VALID','ABSTAINED','TIMEOUT','REFUSAL','INVALID_OUTPUT','FAILED','AMBIGUOUS') THEN RAISE EXCEPTION 'invalid completion status'; END IF;
   IF p->>'status'='AMBIGUOUS' AND statement_timestamp()<started+interval '65 seconds' THEN RAISE EXCEPTION 'attempt still in flight'; END IF;
 ELSIF op='DISCLOSED' THEN
   PERFORM investigator.shadow_assert_current(t,c,stored.binding);
   IF NOT EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='HUMAN_SELECTED')
   OR NOT EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='FINISHED')
   OR EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind IN ('DISCLOSED','EXCLUDED')) THEN RAISE EXCEPTION 'disclosure denied'; END IF;
 ELSIF op='RATED' THEN
   IF NOT EXISTS(SELECT 1 FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r AND kind='DISCLOSED')
   OR p->>'usefulness' NOT IN ('USEFUL','NOT_USEFUL','UNCERTAIN')
   OR length(p->>'reason') NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'invalid accountable rating'; END IF;
 ELSIF op='EXCLUDED' THEN
   IF p->>'reason'<>'STALE_OR_UNUSABLE_CONTEXT' THEN RAISE EXCEPTION 'invalid exclusion'; END IF;
 ELSE RAISE EXCEPTION 'unsupported research command'; END IF;
 SELECT coalesce(max(sequence),0)+1 INTO seq FROM investigator.shadow_event WHERE tenant_id=t AND round_id=r;
 INSERT INTO investigator.shadow_event VALUES(t,r,seq,op,p,a,statement_timestamp(),k);
 RETURN investigator.shadow_read(t,c,r,a);
END $$;

REVOKE ALL ON FUNCTION investigator.require_research(uuid),investigator.research_tenant_allowed(uuid),investigator.shadow_assert_current(uuid,uuid,jsonb),
 investigator.shadow_read(uuid,uuid,uuid,text),investigator.shadow_command(uuid,uuid,uuid,text,text,jsonb,text) FROM PUBLIC;
GRANT USAGE ON SCHEMA investigator TO olin_investigator_research;
GRANT EXECUTE ON FUNCTION investigator.shadow_read(uuid,uuid,uuid,text),
 investigator.shadow_command(uuid,uuid,uuid,text,text,jsonb,text) TO olin_investigator_research;
RESET SESSION AUTHORIZATION;
COMMIT;
