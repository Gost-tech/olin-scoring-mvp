-- Synthetic annotations only; no evidence, research or lending authority.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper) THEN
 RAISE EXCEPTION 'controlled migration owner required'; END IF;
END $$;
CREATE ROLE olin_investigator_feedback NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE olin_investigator_cohort_operator NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
SET SESSION AUTHORIZATION olin_investigator_owner;

CREATE FUNCTION investigator.measurement_tenant_allowed(t uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT nullif(current_setting('olin.tenant_id',true),'')::uuid=t AND
 session_user IN ('olin_feedback_t_'||replace(t::text,'-',''), 'olin_cohort_t_'||replace(t::text,'-',''))
$$;
CREATE FUNCTION investigator.require_measurement(t uuid, operator_only boolean DEFAULT false) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE allowed text;
BEGIN
 allowed:=CASE WHEN session_user='olin_cohort_t_'||replace(t::text,'-','') THEN
 'olin_investigator_cohort_operator' ELSE 'olin_investigator_feedback' END;
 IF NOT coalesce(investigator.measurement_tenant_allowed(t),false)
 OR (operator_only AND allowed<>'olin_investigator_cohort_operator')
 OR NOT pg_has_role(session_user,allowed,'member')
 OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
 OR EXISTS(WITH RECURSIVE memberships(roleid) AS (
 SELECT m.roleid FROM pg_auth_members m JOIN pg_roles l ON l.oid=m.member WHERE l.rolname=session_user
 UNION SELECT m.roleid FROM pg_auth_members m JOIN memberships p ON m.member=p.roleid)
 SELECT 1 FROM memberships JOIN pg_roles g ON g.oid=roleid WHERE g.rolname<>allowed)
 THEN RAISE EXCEPTION 'isolated measurement custody required' USING ERRCODE='42501'; END IF;
END $$;
CREATE POLICY measurement_case_read ON investigator.investigation_case FOR SELECT TO olin_investigator_owner
 USING(investigator.measurement_tenant_allowed(tenant_id));

CREATE TABLE investigator.feedback_annotation (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, record_id uuid NOT NULL,
 stream_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), predecessor uuid,
 kind text NOT NULL CHECK(kind IN ('FEEDBACK','EXTERNAL_OUTCOME')),
 attribution text NOT NULL CHECK(attribution IN ('ANALYST_JUDGMENT','ANALYST_REPORTED_EXTERNAL')),
 actor text NOT NULL CHECK(length(actor) BETWEEN 1 AND 240),
 authenticated_organization text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 schema_version text NOT NULL CHECK(schema_version='investigator-feedback-1'),
 payload jsonb NOT NULL CHECK(octet_length(payload::text)<=16000),
 command_key text NOT NULL CHECK(length(command_key) BETWEEN 1 AND 240),
 request_digest text NOT NULL,
 PRIMARY KEY(tenant_id,record_id), UNIQUE(tenant_id,stream_id,version), UNIQUE(tenant_id,command_key),
 FOREIGN KEY(tenant_id,case_id) REFERENCES investigator.investigation_case(tenant_id,case_id),
 FOREIGN KEY(tenant_id,predecessor) REFERENCES investigator.feedback_annotation(tenant_id,record_id)
);
CREATE INDEX feedback_case_history ON investigator.feedback_annotation(tenant_id,case_id,recorded_at,record_id);
CREATE TABLE investigator.declared_cohort (
 tenant_id uuid NOT NULL, cohort_id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
 frozen_at timestamptz NOT NULL DEFAULT statement_timestamp(), operator text NOT NULL,
 definition jsonb NOT NULL CHECK(octet_length(definition::text)<=16000),
 command_key text NOT NULL CHECK(length(command_key) BETWEEN 1 AND 240),
 PRIMARY KEY(tenant_id,cohort_id,version), UNIQUE(tenant_id,command_key)
);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['feedback_annotation','declared_cohort'] LOOP
 EXECUTE format('ALTER TABLE investigator.%I ENABLE ROW LEVEL SECURITY',tab);
 EXECUTE format('ALTER TABLE investigator.%I FORCE ROW LEVEL SECURITY',tab);
 EXECUTE format('CREATE POLICY measurement_policy ON investigator.%I TO olin_investigator_owner USING(investigator.measurement_tenant_allowed(tenant_id)) WITH CHECK(investigator.measurement_tenant_allowed(tenant_id))',tab);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON investigator.%I FOR EACH ROW EXECUTE FUNCTION investigator.reject_history_mutation()',tab);
 EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON investigator.%I FOR EACH STATEMENT EXECUTE FUNCTION investigator.reject_history_mutation()',tab);
 END LOOP;
END $$;

CREATE FUNCTION investigator.read_measurements(t uuid,c uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
BEGIN
 PERFORM investigator.require_measurement(t);
 IF c IS NOT NULL AND NOT EXISTS(SELECT 1 FROM investigator.investigation_case WHERE tenant_id=t AND case_id=c) THEN
 RAISE EXCEPTION 'case access denied' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('as_of',statement_timestamp(),
 'annotations',coalesce((SELECT jsonb_agg(to_jsonb(f) - 'request_digest' - 'command_key' ORDER BY recorded_at,record_id)
 FROM investigator.feedback_annotation f WHERE tenant_id=t AND (c IS NULL OR case_id=c)),'[]'::jsonb),
 'cohort_versions',coalesce((SELECT jsonb_agg(to_jsonb(d) - 'command_key' ORDER BY cohort_id,version)
 FROM investigator.declared_cohort d WHERE tenant_id=t),'[]'::jsonb));
END $$;

CREATE FUNCTION investigator.append_feedback(t uuid,c uuid,a text,kind_value text,p jsonb,k text,previous uuid,expected integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE old investigator.feedback_annotation%ROWTYPE; prior investigator.feedback_annotation%ROWTYPE;
 r uuid:=gen_random_uuid(); stream uuid; v integer; d text; attribution_value text;
BEGIN
 PERFORM investigator.require_measurement(t);
 IF session_user<>'olin_feedback_t_'||replace(t::text,'-','') THEN RAISE EXCEPTION 'feedback writer required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM investigator.investigation_case WHERE tenant_id=t AND case_id=c) THEN RAISE EXCEPTION 'case denied' USING ERRCODE='42501'; END IF;
 IF a IS NULL OR length(a) NOT BETWEEN 1 AND 240 OR k IS NULL OR length(k) NOT BETWEEN 1 AND 240
 OR kind_value IS NULL OR kind_value NOT IN ('FEEDBACK','EXTERNAL_OUTCOME') OR expected IS NULL OR expected<0
 OR p IS NULL OR jsonb_typeof(p)<>'object' OR octet_length(p::text)>16000
 OR (SELECT count(*) FROM jsonb_object_keys(p))<>9
 OR NOT p ?& ARRAY['observation_status','judgment','explanation','source_description','source_reference','occurred_at','report_binding','action_id','correction_reason']
 THEN RAISE EXCEPTION 'invalid annotation shape'; END IF;
 IF p->>'observation_status' IS NULL OR p->>'observation_status' NOT IN ('PENDING','UNKNOWN','UNAVAILABLE','OBSERVED','NOT_APPLICABLE','WINDOW_INCOMPLETE')
 OR jsonb_typeof(p->'explanation')<>'string' OR length(p->>'explanation') NOT BETWEEN 1 AND 1000
 OR jsonb_typeof(p->'report_binding')<>'object' OR p#>>'{report_binding,tenant_id}' IS DISTINCT FROM t::text
 OR p#>>'{report_binding,case_id}' IS DISTINCT FROM c::text
 OR coalesce(p#>>'{report_binding,report_input_digest}','') !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(p->'action_id') NOT IN ('string','null')
 THEN RAISE EXCEPTION 'invalid annotation content'; END IF;
 IF p->'occurred_at'<>'null'::jsonb AND (jsonb_typeof(p->'occurred_at')<>'string' OR (p->>'occurred_at')::timestamptz>statement_timestamp()) THEN RAISE EXCEPTION 'invalid occurrence time'; END IF;
 IF kind_value='FEEDBACK' THEN
 attribution_value:='ANALYST_JUDGMENT';
 IF p->'source_description'<>'null'::jsonb OR p->'source_reference'<>'null'::jsonb
 OR (p->>'observation_status'='OBSERVED' AND (p->>'judgment' IS NULL OR p->>'judgment' NOT IN ('USEFUL','NOT_USEFUL','UNCERTAIN')))
 THEN RAISE EXCEPTION 'invalid analyst judgment'; END IF;
 ELSE
 attribution_value:='ANALYST_REPORTED_EXTERNAL';
 IF p->'judgment'<>'null'::jsonb OR jsonb_typeof(p->'source_description')<>'string'
 OR length(p->>'source_description') NOT BETWEEN 1 AND 500 OR jsonb_typeof(p->'source_reference')<>'string'
 OR length(p->>'source_reference') NOT BETWEEN 1 AND 240 THEN RAISE EXCEPTION 'external attribution required'; END IF;
 END IF;
 IF p->>'observation_status'<>'OBSERVED' AND p->'judgment'<>'null'::jsonb THEN RAISE EXCEPTION 'missing observation is not a rating'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':feedback',0));
 d:=encode(sha256(convert_to(investigator.canonical_json(jsonb_build_object('case',c,'actor',a,'kind',kind_value,'payload',p,'previous',previous,'expected',expected)),'UTF8')),'hex');
 SELECT * INTO prior FROM investigator.feedback_annotation WHERE tenant_id=t AND command_key=k;
 IF FOUND THEN
 IF prior.request_digest<>d THEN RAISE EXCEPTION 'changed replay content' USING ERRCODE='23505'; END IF;
 RETURN to_jsonb(prior)-'request_digest'-'command_key'; END IF;
 IF previous IS NULL THEN
 IF expected<>0 OR p->'correction_reason'<>'null'::jsonb THEN RAISE EXCEPTION 'invalid initial version'; END IF;
 stream:=r; v:=1;
 ELSE
 SELECT * INTO old FROM investigator.feedback_annotation WHERE tenant_id=t AND record_id=previous;
 IF NOT FOUND OR old.case_id<>c OR old.kind<>kind_value OR old.version<>expected
 OR EXISTS(SELECT 1 FROM investigator.feedback_annotation WHERE tenant_id=t AND stream_id=old.stream_id AND version>expected)
 OR jsonb_typeof(p->'correction_reason')<>'string' OR length(p->>'correction_reason') NOT BETWEEN 1 AND 500
 OR p->'report_binding'<>old.payload->'report_binding' OR p->'action_id'<>old.payload->'action_id'
 THEN RAISE EXCEPTION 'stale or invalid correction' USING ERRCODE='40001'; END IF;
 stream:=old.stream_id; v:=expected+1;
 END IF;
 INSERT INTO investigator.feedback_annotation VALUES(t,c,r,stream,v,previous,kind_value,attribution_value,a,
 'tenant:'||t::text,statement_timestamp(),'investigator-feedback-1',p,k,d) RETURNING * INTO prior;
 RETURN to_jsonb(prior)-'request_digest'-'command_key';
END $$;

CREATE FUNCTION investigator.freeze_cohort(t uuid,id uuid,expected integer,p jsonb,k text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,investigator AS $$
DECLARE prior investigator.declared_cohort%ROWTYPE; latest investigator.declared_cohort%ROWTYPE; member jsonb;
BEGIN
 PERFORM investigator.require_measurement(t,true);
 IF expected IS NULL OR expected<0 OR p IS NULL OR jsonb_typeof(p)<>'object'
 OR (SELECT count(*) FROM jsonb_object_keys(p))<>5 OR NOT p ?& ARRAY['source_reference','eligibility_version','synthetic_only','members','amendment_reason']
 OR p->'synthetic_only'<>'true'::jsonb OR jsonb_typeof(p->'members')<>'array'
 OR jsonb_array_length(p->'members') NOT BETWEEN 1 AND 10
 OR jsonb_typeof(p->'source_reference')<>'string' OR jsonb_typeof(p->'eligibility_version')<>'string'
 OR jsonb_typeof(p->'amendment_reason')<>'string'
 OR length(p->>'source_reference') NOT BETWEEN 1 AND 240 OR length(p->>'eligibility_version') NOT BETWEEN 1 AND 100
 OR length(p->>'amendment_reason') NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'invalid synthetic cohort'; END IF;
 FOR member IN SELECT value FROM jsonb_array_elements(p->'members') LOOP
 IF jsonb_typeof(member)<>'object' OR (SELECT count(*) FROM jsonb_object_keys(member))<>3
 OR NOT member ?& ARRAY['case_id','eligible','reason'] OR jsonb_typeof(member->'eligible')<>'boolean'
 OR jsonb_typeof(member->'reason')<>'string' OR jsonb_typeof(member->'case_id')<>'string'
 OR length(member->>'reason') NOT BETWEEN 1 AND 500
 OR NOT EXISTS(SELECT 1 FROM investigator.investigation_case WHERE tenant_id=t AND case_id=(member->>'case_id')::uuid)
 THEN RAISE EXCEPTION 'invalid cohort member'; END IF;
 END LOOP;
 IF (SELECT count(DISTINCT value->>'case_id') FROM jsonb_array_elements(p->'members'))<>jsonb_array_length(p->'members') THEN RAISE EXCEPTION 'duplicate member'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(t::text||':cohort',0));
 SELECT * INTO prior FROM investigator.declared_cohort WHERE tenant_id=t AND command_key=k;
 IF FOUND THEN
 IF prior.cohort_id<>id OR prior.version<>expected+1 OR prior.definition<>p THEN RAISE EXCEPTION 'cohort replay conflict'; END IF;
 RETURN to_jsonb(prior)-'command_key'; END IF;
 SELECT * INTO latest FROM investigator.declared_cohort WHERE tenant_id=t AND cohort_id=id ORDER BY version DESC LIMIT 1;
 IF coalesce(latest.version,0)<>expected THEN RAISE EXCEPTION 'stale cohort version' USING ERRCODE='40001'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(coalesce(latest.definition->'members','[]'::jsonb)) old
 WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p->'members') new WHERE new->>'case_id'=old->>'case_id'))
 THEN RAISE EXCEPTION 'declared members cannot disappear'; END IF;
 INSERT INTO investigator.declared_cohort VALUES(t,id,expected+1,statement_timestamp(),session_user,p,k) RETURNING * INTO prior;
 RETURN to_jsonb(prior)-'command_key';
END $$;
REVOKE ALL ON FUNCTION investigator.measurement_tenant_allowed(uuid),investigator.require_measurement(uuid,boolean),
 investigator.read_measurements(uuid,uuid),investigator.append_feedback(uuid,uuid,text,text,jsonb,text,uuid,integer),
 investigator.freeze_cohort(uuid,uuid,integer,jsonb,text) FROM PUBLIC;
GRANT USAGE ON SCHEMA investigator TO olin_investigator_feedback,olin_investigator_cohort_operator;
GRANT EXECUTE ON FUNCTION investigator.read_measurements(uuid,uuid),investigator.append_feedback(uuid,uuid,text,text,jsonb,text,uuid,integer) TO olin_investigator_feedback;
GRANT EXECUTE ON FUNCTION investigator.freeze_cohort(uuid,uuid,integer,jsonb,text) TO olin_investigator_cohort_operator;
RESET SESSION AUTHORIZATION;
COMMIT;
