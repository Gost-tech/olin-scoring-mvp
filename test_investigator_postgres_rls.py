"""Real-PostgreSQL negative harness for the Investigator runtime role.

Set OLIN_INVESTIGATOR_TEST_ADMIN_DSN to a disposable PostgreSQL database. The
suite applies the real migration and connects as two actual tenant logins. It
never substitutes an owner connection for runtime assertions.
"""

from __future__ import annotations

import os
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from olin.investigator.canonical import canonical_json_bytes

ADMIN_DSN = os.getenv("OLIN_INVESTIGATOR_TEST_ADMIN_DSN", "").strip()
DISPOSABLE_CONFIRMED = os.getenv("OLIN_INVESTIGATOR_TEST_DISPOSABLE", "") == "YES"
REQUIRE_POSTGRES = os.getenv("OLIN_INVESTIGATOR_REQUIRE_POSTGRES_TESTS", "") == "1"

try:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
except ImportError:  # pragma: no cover - environment-gated integration suite
    psycopg = None
    sql = None
    conninfo_to_dict = None
    make_conninfo = None

POSTGRES_AVAILABLE = bool(ADMIN_DSN and DISPOSABLE_CONFIRMED and psycopg is not None)

if REQUIRE_POSTGRES and not POSTGRES_AVAILABLE:
    raise RuntimeError(
        "required Investigator PostgreSQL tests need psycopg and an explicitly disposable DSN"
    )


@unittest.skipUnless(
    POSTGRES_AVAILABLE, "explicitly disposable PostgreSQL DSN/psycopg required"
)
class InvestigatorMigrationFailureTests(unittest.TestCase):
    def test_dirty_authority_and_public_exposure_abort_atomically(self):
        root = Path(__file__).resolve().parent
        parsed_dsn = conninfo_to_dict(ADMIN_DSN)
        if not str(parsed_dsn.get("dbname", "")).endswith("_investigator_test"):
            raise RuntimeError(
                "PostgreSQL harness requires a database ending _investigator_test"
            )
        migration = (
            root / "db" / "migrations" / "0001_investigator_phase0.sql"
        ).read_text(encoding="utf-8")
        admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        try:
            admin.execute("CREATE ROLE olin_investigator_owner NOLOGIN")
            admin.execute("CREATE ROLE olin_investigator_runtime NOLOGIN")
            admin.execute("CREATE ROLE unexpected_investigator_grantee NOLOGIN")
            admin.execute(
                "GRANT olin_investigator_owner TO unexpected_investigator_grantee"
            )
            with self.assertRaises(psycopg.Error):
                admin.execute(migration)
            admin.execute("ROLLBACK")
            self.assertIsNone(
                admin.execute("SELECT to_regnamespace('investigator')").fetchone()[0]
            )
            admin.execute(
                "REVOKE olin_investigator_owner FROM unexpected_investigator_grantee"
            )
            admin.execute("DROP ROLE unexpected_investigator_grantee")
            admin.execute("DROP ROLE olin_investigator_runtime")
            admin.execute("DROP ROLE olin_investigator_owner")

            admin.execute("CREATE TABLE public.scoring_log (application_id text)")
            admin.execute("GRANT SELECT ON public.scoring_log TO PUBLIC")
            with self.assertRaises(psycopg.Error):
                admin.execute(migration)
            admin.execute("ROLLBACK")
            self.assertIsNone(
                admin.execute("SELECT to_regnamespace('investigator')").fetchone()[0]
            )
            admin.execute("REVOKE SELECT ON public.scoring_log FROM PUBLIC")
            admin.execute("DROP TABLE public.scoring_log")

            admin.execute(
                "CREATE FUNCTION public.legacy_money_routine() RETURNS void "
                "LANGUAGE plpgsql SECURITY DEFINER AS 'BEGIN NULL; END'"
            )
            with self.assertRaises(psycopg.Error):
                admin.execute(migration)
            admin.execute("ROLLBACK")
            self.assertIsNone(
                admin.execute("SELECT to_regnamespace('investigator')").fetchone()[0]
            )
            remaining_roles = admin.execute(
                "SELECT count(*) FROM pg_roles WHERE rolname IN "
                "('olin_investigator_owner','olin_investigator_runtime')"
            ).fetchone()[0]
            self.assertEqual(remaining_roles, 0)

            # Prove a failure after the Phase 1 authorization switch is atomic
            # and cannot strand the admin connection as the schema owner.
            admin.execute("DROP FUNCTION public.legacy_money_routine()")
            admin.execute(migration)
            phase1_migration = (
                root / "db" / "migrations" / "0002_investigator_case_event_snapshot.sql"
            ).read_text(encoding="utf-8")
            forced_failure_migration = phase1_migration.replace(
                "SET SESSION AUTHORIZATION olin_investigator_owner;",
                "SET SESSION AUTHORIZATION olin_investigator_owner;\nSELECT 1 / 0;",
                1,
            )
            authenticated_identity = admin.execute(
                "SELECT session_user, current_user"
            ).fetchone()
            with self.assertRaises(psycopg.errors.DivisionByZero):
                admin.execute(forced_failure_migration)
            admin.execute("ROLLBACK")
            self.assertEqual(
                admin.execute("SELECT session_user, current_user").fetchone(),
                authenticated_identity,
            )
            self.assertIsNone(
                admin.execute(
                    "SELECT to_regclass('investigator.case_snapshot')"
                ).fetchone()[0]
            )
            self.assertEqual(
                admin.execute(
                    "SELECT count(*) FROM pg_auth_members membership "
                    "JOIN pg_roles granted ON granted.oid=membership.roleid "
                    "WHERE granted.rolname='olin_investigator_owner'"
                ).fetchone()[0],
                0,
            )
            admin.execute("DROP SCHEMA investigator CASCADE")
            admin.execute("DROP ROLE olin_investigator_runtime")
            admin.execute("DROP ROLE olin_investigator_owner")
        finally:
            admin.execute("DROP FUNCTION IF EXISTS public.legacy_money_routine()")
            admin.execute("DROP TABLE IF EXISTS public.scoring_log")
            admin.execute("DROP SCHEMA IF EXISTS investigator CASCADE")
            admin.execute("DROP ROLE IF EXISTS unexpected_investigator_grantee")
            admin.execute("DROP ROLE IF EXISTS olin_investigator_runtime")
            admin.execute("DROP ROLE IF EXISTS olin_investigator_owner")
            admin.close()


@unittest.skipUnless(
    POSTGRES_AVAILABLE,
    "explicitly disposable PostgreSQL DSN/psycopg required",
)
class InvestigatorPostgresRLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent
        cls.tenant_a = uuid4()
        cls.tenant_b = uuid4()
        cls.case_a = uuid4()
        cls.case_b = uuid4()
        cls.role_a = "olin_inv_t_" + cls.tenant_a.hex
        cls.role_b = "olin_inv_t_" + cls.tenant_b.hex
        cls.password_a = secrets.token_urlsafe(24)
        cls.password_b = secrets.token_urlsafe(24)
        parsed_dsn = conninfo_to_dict(ADMIN_DSN)
        if not str(parsed_dsn.get("dbname", "")).endswith("_investigator_test"):
            raise RuntimeError(
                "PostgreSQL harness requires a database ending _investigator_test"
            )
        cls.admin = psycopg.connect(ADMIN_DSN, autocommit=True)

        # A trap table proves the migration revokes access to an existing legacy
        # money/decision table rather than merely testing a missing object.
        cls.created_legacy_trap = cls.admin.execute(
            "SELECT to_regclass('public.scoring_log') IS NULL"
        ).fetchone()[0]
        if cls.created_legacy_trap:
            cls.admin.execute("CREATE TABLE public.scoring_log (application_id text)")
        phase0_migration = (
            cls.root / "db" / "migrations" / "0001_investigator_phase0.sql"
        ).read_text(encoding="utf-8")
        cls.admin.execute(phase0_migration)
        phase0_counts = cls.admin.execute(
            "SELECT "
            "(SELECT count(*) FROM investigator.investigation_case), "
            "(SELECT count(*) FROM investigator.investigation_event)"
        ).fetchone()
        if phase0_counts != (0, 0):
            raise AssertionError(
                "fresh CI database must have zero Phase 0 cases and events before 0002; "
                f"found {phase0_counts!r}"
            )
        migration_identity = cls.admin.execute(
            "SELECT session_user, current_user"
        ).fetchone()
        phase1_migration = (
            cls.root / "db" / "migrations" / "0002_investigator_case_event_snapshot.sql"
        ).read_text(encoding="utf-8")
        cls.admin.execute(phase1_migration)
        restored_identity = cls.admin.execute(
            "SELECT session_user, current_user"
        ).fetchone()
        if restored_identity != migration_identity:
            raise AssertionError(
                "Phase 1 migration did not reset session authorization: "
                f"before={migration_identity!r}, after={restored_identity!r}"
            )
        for role, password in (
            (cls.role_a, cls.password_a),
            (cls.role_b, cls.password_b),
        ):
            cls.admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(role), sql.Literal(password)),
            )
            cls.admin.execute(
                sql.SQL("GRANT olin_investigator_runtime TO {}").format(
                    sql.Identifier(role)
                )
            )

        cls.conn_a = psycopg.connect(cls._tenant_dsn(cls.role_a, cls.password_a))
        cls.conn_b = psycopg.connect(cls._tenant_dsn(cls.role_b, cls.password_b))
        cls._create_case(
            cls.conn_a, cls.role_a, cls.tenant_a, cls.case_a, "case-a-create"
        )
        cls._create_case(
            cls.conn_b, cls.role_b, cls.tenant_b, cls.case_b, "case-b-create"
        )

    @classmethod
    def tearDownClass(cls):
        cls.conn_a.close()
        cls.conn_b.close()
        for role in (cls.role_a, cls.role_b):
            cls.admin.execute(
                sql.SQL("REVOKE olin_investigator_runtime FROM {}").format(
                    sql.Identifier(role)
                )
            )
            cls.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        cls.admin.execute("DROP SCHEMA investigator CASCADE")
        if cls.created_legacy_trap:
            cls.admin.execute("DROP TABLE public.scoring_log")
        cls.admin.execute("DROP ROLE olin_investigator_runtime")
        cls.admin.execute("DROP ROLE olin_investigator_owner")
        cls.admin.close()

    @classmethod
    def _tenant_dsn(cls, role, password):
        values = conninfo_to_dict(ADMIN_DSN)
        values.update(user=role, password=password)
        return make_conninfo(**values)

    @classmethod
    def _context(
        cls, conn, role, tenant, actor="phase0-test-actor", actor_type="human"
    ):
        conn.execute(
            sql.SQL("SET LOCAL ROLE {}").format(
                sql.Identifier("olin_investigator_runtime")
            )
        )
        conn.execute("SELECT set_config('olin.tenant_id', %s, true)", (str(tenant),))
        conn.execute("SELECT set_config('olin.actor_id', %s, true)", (actor,))
        conn.execute("SELECT set_config('olin.actor_type', %s, true)", (actor_type,))
        conn.execute(
            "SELECT set_config('olin.workload_id', %s, true)", ("phase0-tests",)
        )
        conn.execute(
            "SELECT set_config('olin.authentication_reference', %s, true)",
            ("postgres-test-login",),
        )
        conn.execute(
            "SELECT set_config('olin.authorization_source', %s, true)",
            ("postgres-runtime-harness",),
        )
        conn.execute(
            "SELECT set_config('olin.correlation_id', %s, true)",
            ("postgres-phase1-run",),
        )
        conn.execute(
            "SELECT set_config('olin.actor_context_created_at', %s, true)",
            ("2026-09-04T12:30:45.123456+00:00",),
        )

    @classmethod
    def _create_case(cls, conn, role, tenant, case_id, idempotency_key):
        with conn.transaction():
            cls._context(conn, role, tenant, actor_type="bank_service")
            conn.execute(
                """SELECT investigator.create_case(
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb
                )""",
                (
                    case_id,
                    tenant,
                    None,
                    "phase0",
                    uuid4(),
                    datetime.now(timezone.utc),
                    "{}",
                    1,
                    idempotency_key,
                    sha256(b"{}").hexdigest(),
                    "{}",
                ),
            ).fetchone()

    def test_runtime_role_is_unprivileged_and_tables_force_rls(self):
        for role_name in ("olin_investigator_runtime", "olin_investigator_owner"):
            role = self.admin.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolbypassrls, "
                "rolinherit, rolreplication "
                "FROM pg_roles WHERE rolname=%s",
                (role_name,),
            ).fetchone()
            self.assertEqual(role, (False, False, False, False, False, False, False))
        rows = self.admin.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid IN ('investigator.investigation_case'::regclass, "
            "'investigator.investigation_event'::regclass, "
            "'investigator.case_snapshot'::regclass, "
            "'investigator.case_snapshot_request'::regclass, "
            "'investigator.case_snapshot_invalidation'::regclass) ORDER BY relname"
        ).fetchall()
        self.assertEqual(
            rows,
            [
                ("case_snapshot", True, True),
                ("case_snapshot_invalidation", True, True),
                ("case_snapshot_request", True, True),
                ("investigation_case", True, True),
                ("investigation_event", True, True),
            ],
        )
        owners = self.admin.execute(
            "SELECT DISTINCT owner.rolname FROM pg_proc proc "
            "JOIN pg_namespace ns ON ns.oid=proc.pronamespace "
            "JOIN pg_roles owner ON owner.oid=proc.proowner "
            "WHERE ns.nspname='investigator'"
        ).fetchall()
        self.assertEqual(owners, [("olin_investigator_owner",)])
        table_owners = self.admin.execute(
            "SELECT DISTINCT owner.rolname FROM pg_class relation "
            "JOIN pg_namespace ns ON ns.oid=relation.relnamespace "
            "JOIN pg_roles owner ON owner.oid=relation.relowner "
            "WHERE ns.nspname='investigator' AND relation.relkind IN ('r','p')"
        ).fetchall()
        self.assertEqual(table_owners, [("olin_investigator_owner",)])
        privileged_memberships = self.admin.execute(
            "SELECT member.rolname, granted.rolname FROM pg_auth_members membership "
            "JOIN pg_roles member ON member.oid=membership.member "
            "JOIN pg_roles granted ON granted.oid=membership.roleid "
            "WHERE member.rolname IN ('olin_investigator_owner','olin_investigator_runtime')"
        ).fetchall()
        self.assertEqual(privileged_memberships, [])
        migration_owner_memberships = self.admin.execute(
            "SELECT count(*) FROM pg_auth_members membership "
            "JOIN pg_roles granted ON granted.oid=membership.roleid "
            "WHERE granted.rolname='olin_investigator_owner'"
        ).fetchone()[0]
        self.assertEqual(migration_owner_memberships, 0)
        tenant_memberships = self.admin.execute(
            "SELECT member.rolname, granted.rolname FROM pg_auth_members membership "
            "JOIN pg_roles member ON member.oid=membership.member "
            "JOIN pg_roles granted ON granted.oid=membership.roleid "
            "WHERE member.rolname IN (%s,%s) ORDER BY member.rolname, granted.rolname",
            (self.role_a, self.role_b),
        ).fetchall()
        self.assertEqual(
            tenant_memberships,
            sorted(
                [
                    (self.role_a, "olin_investigator_runtime"),
                    (self.role_b, "olin_investigator_runtime"),
                ]
            ),
        )

    def test_effective_grants_are_minimal(self):
        privileges = self.admin.execute(
            "SELECT "
            "has_schema_privilege('olin_investigator_runtime','investigator','USAGE'), "
            "has_schema_privilege('olin_investigator_runtime','public','CREATE'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_case','SELECT'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_case','INSERT,UPDATE,DELETE,TRUNCATE'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_event','SELECT'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_event','INSERT,UPDATE,DELETE,TRUNCATE'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot','SELECT'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot','INSERT,UPDATE,DELETE,TRUNCATE'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot_invalidation','SELECT'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot_invalidation','INSERT,UPDATE,DELETE,TRUNCATE'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot_request','SELECT'), "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.case_snapshot_request','INSERT,UPDATE,DELETE,TRUNCATE'), "
            "has_table_privilege('olin_investigator_runtime','public.scoring_log','SELECT'), "
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.create_case(uuid,uuid,text,text,uuid,timestamptz,jsonb,integer,text,text,jsonb)',"
            "'EXECUTE'), "
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.append_event(uuid,uuid,bigint,uuid,text,timestamptz,jsonb,integer,text,text,uuid,uuid,jsonb)',"
            "'EXECUTE')"
        ).fetchone()
        self.assertEqual(
            privileges,
            (
                True,
                False,
                True,
                False,
                True,
                False,
                True,
                False,
                True,
                False,
                False,
                False,
                False,
                True,
                True,
            ),
        )
        effective_functions = self.admin.execute(
            "SELECT proc.proname FROM pg_proc proc "
            "JOIN pg_namespace ns ON ns.oid=proc.pronamespace "
            "WHERE ns.nspname='investigator' "
            "AND has_function_privilege('olin_investigator_runtime',proc.oid,'EXECUTE') "
            "ORDER BY proc.proname"
        ).fetchall()
        self.assertEqual(
            effective_functions,
            [
                ("append_event",),
                ("context_tenant_id",),
                ("create_case",),
                ("create_snapshot",),
                ("invalidate_snapshot",),
                ("is_snapshot_current",),
                ("session_tenant_id",),
                ("tenant_access_allowed",),
            ],
        )
        exposed_legacy_relations = self.admin.execute(
            "SELECT count(*) FROM pg_class relation "
            "JOIN pg_namespace ns ON ns.oid=relation.relnamespace "
            "WHERE ns.nspname NOT IN ('investigator','pg_catalog','information_schema') "
            "AND ns.nspname !~ '^pg_(toast|temp)' "
            "AND relation.relkind IN ('r','p','v','m','S','f') "
            "AND has_table_privilege('olin_investigator_runtime',relation.oid,"
            "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
        ).fetchone()[0]
        self.assertEqual(exposed_legacy_relations, 0)
        exposed_legacy_routines = self.admin.execute(
            "SELECT count(*) FROM pg_proc routine "
            "JOIN pg_namespace ns ON ns.oid=routine.pronamespace "
            "WHERE ns.nspname NOT IN ('investigator','pg_catalog','information_schema') "
            "AND ns.nspname !~ '^pg_(toast|temp)' "
            "AND has_function_privilege('olin_investigator_runtime',routine.oid,'EXECUTE')"
        ).fetchone()[0]
        self.assertEqual(exposed_legacy_routines, 0)
        policies = self.admin.execute(
            "SELECT tablename, policyname, roles, qual IS NOT NULL, with_check IS NOT NULL "
            "FROM pg_policies WHERE schemaname='investigator' ORDER BY tablename, policyname"
        ).fetchall()
        self.assertEqual(len(policies), 5)
        for _table, _policy, roles, has_using, has_check in policies:
            self.assertEqual(
                set(roles), {"olin_investigator_owner", "olin_investigator_runtime"}
            )
            self.assertTrue(has_using)
            self.assertTrue(has_check)

    def test_event_semantics_digest_and_caller_trust_fail_closed(self):
        current_version = 1
        digest = sha256(b"{}").hexdigest()
        attempts = (
            ("CREDIT_APPROVED", "{}", digest, psycopg.errors.InvalidParameterValue),
            (
                "INVESTIGATION_EVENT_RECORDED",
                "{}",
                "f" * 64,
                psycopg.errors.DataException,
            ),
            (
                "INVESTIGATION_EVENT_RECORDED",
                '{"verified": true}',
                sha256(b'{"verified": true}').hexdigest(),
                psycopg.errors.InvalidParameterValue,
            ),
        )
        for index, (event_type, payload, payload_digest, error_type) in enumerate(
            attempts
        ):
            with (
                self.subTest(event_type=event_type, index=index),
                self.conn_b.transaction(),
            ):
                self._context(self.conn_b, self.role_b, self.tenant_b)
                with self.assertRaises(error_type):
                    self.conn_b.execute(
                        "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                        (
                            self.tenant_b,
                            self.case_b,
                            current_version,
                            uuid4(),
                            event_type,
                            datetime.now(timezone.utc),
                            payload,
                            1,
                            f"rejected-event-{index}",
                            payload_digest,
                        ),
                    )

    def test_actor_gucs_cannot_forge_server_derived_provenance(self):
        case_id = uuid4()
        with self.conn_a.transaction():
            self._context(
                self.conn_a,
                self.role_a,
                self.tenant_a,
                actor="forged-human",
                actor_type="bank_service",
            )
            self.conn_a.execute(
                "SELECT set_config('olin.authentication_reference', %s, true)",
                ("forged-authentication",),
            )
            self.conn_a.execute(
                "SELECT set_config('olin.authorization_source', %s, true)",
                ("forged-authorization",),
            )
            self.conn_a.execute(
                "SELECT investigator.create_case("
                "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                (
                    case_id,
                    self.tenant_a,
                    None,
                    "actor-forgery-test",
                    uuid4(),
                    datetime.now(timezone.utc),
                    "{}",
                    1,
                    "actor-forgery-case",
                    sha256(b"{}").hexdigest(),
                    "{}",
                ),
            )
            actor = self.conn_a.execute(
                "SELECT actor_type, actor_id, workload_id, authentication_reference, "
                "authorization_source, actor_case_id FROM investigator.investigation_event "
                "WHERE case_id=%s",
                (case_id,),
            ).fetchone()
            self.assertEqual(
                actor,
                (
                    "system",
                    self.role_a,
                    self.role_a,
                    f"postgres-login:{self.role_a}",
                    "investigator-tenant-role-binding",
                    case_id,
                ),
            )

    def test_login_has_no_table_access_before_narrow_runtime_role(self):
        with (
            self.conn_a.transaction(),
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
        ):
            self.conn_a.execute("SELECT * FROM investigator.investigation_case")
        with (
            self.conn_a.transaction(),
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
        ):
            self.conn_a.execute("SELECT investigator.session_tenant_id()")

    def test_cross_tenant_and_forged_context_are_denied(self):
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            own = self.conn_a.execute(
                "SELECT case_id FROM investigator.investigation_case ORDER BY case_id"
            ).fetchall()
            self.assertEqual(own, [(self.case_a,)])
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_b)
            forged = self.conn_a.execute(
                "SELECT case_id FROM investigator.investigation_case"
            ).fetchall()
            self.assertEqual(forged, [])
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn_a.execute(
                    "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                    (
                        self.tenant_b,
                        self.case_b,
                        1,
                        uuid4(),
                        "INVESTIGATION_EVENT_RECORDED",
                        datetime.now(timezone.utc),
                        "{}",
                        1,
                        "forged-tenant-event",
                        sha256(b"{}").hexdigest(),
                    ),
                )

    def test_missing_context_denies_reads_and_mutation(self):
        with self.conn_a.transaction():
            self.conn_a.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier("olin_investigator_runtime")
                )
            )
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.investigation_case WHERE case_id=%s",
                    (self.case_a,),
                ).fetchone()[0],
                0,
            )
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn_a.execute(
                    "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                    (
                        self.tenant_a,
                        self.case_a,
                        1,
                        uuid4(),
                        "INVESTIGATION_EVENT_RECORDED",
                        datetime.now(timezone.utc),
                        "{}",
                        1,
                        "missing-context-event",
                        sha256(b"{}").hexdigest(),
                    ),
                )

    def test_direct_dml_and_legacy_money_table_access_fail(self):
        direct_insert = (
            "INSERT INTO investigator.investigation_event "
            "(event_id,tenant_id,case_id,event_sequence,event_type,occurred_at,"
            "actor_type,actor_id,payload_schema_version,idempotency_key,payload_digest) "
            f"VALUES ('{uuid4()}','{self.tenant_a}','{self.case_a}',2,'INVESTIGATION_EVENT_RECORDED',"
            f"now(),'human','x',1,'direct-insert','{'3' * 64}')"
        )
        statements = (
            direct_insert,
            "UPDATE investigator.investigation_event SET event_type='ALTERED'",
            "DELETE FROM investigator.investigation_event",
            "TRUNCATE investigator.investigation_event",
            "UPDATE investigator.investigation_case SET case_version=99",
            "SELECT * FROM public.scoring_log",
        )
        for statement in statements:
            with (
                self.subTest(statement=statement.split()[0]),
                self.conn_a.transaction(),
            ):
                self._context(self.conn_a, self.role_a, self.tenant_a)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    self.conn_a.execute(statement)

    def test_privileged_history_rewrite_is_rejected_by_immutability_trigger(self):
        event_id = self.admin.execute(
            "SELECT event_id FROM investigator.investigation_event WHERE case_id=%s "
            "ORDER BY event_sequence LIMIT 1",
            (self.case_a,),
        ).fetchone()[0]
        with self.assertRaises(psycopg.Error):
            self.admin.execute(
                "UPDATE investigator.investigation_event SET actor_id='rewritten' "
                "WHERE event_id=%s",
                (event_id,),
            )
        preserved = self.admin.execute(
            "SELECT actor_id FROM investigator.investigation_event WHERE event_id=%s",
            (event_id,),
        ).fetchone()[0]
        self.assertEqual(preserved, self.role_a)

    def test_transaction_local_context_is_cleared_after_commit(self):
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.investigation_case"
                ).fetchone()[0],
                1,
            )
        with self.conn_a.transaction():
            self.conn_a.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier("olin_investigator_runtime")
                )
            )
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.investigation_case"
                ).fetchone()[0],
                0,
            )
        with self.assertRaises(RuntimeError), self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            raise RuntimeError("force rollback")
        with self.conn_a.transaction():
            self.conn_a.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier("olin_investigator_runtime")
                )
            )
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.investigation_case"
                ).fetchone()[0],
                0,
            )

    def test_append_is_idempotent_and_optimistically_versioned(self):
        event_id = uuid4()
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            parent_event_id = self.conn_a.execute(
                "SELECT event_id FROM investigator.investigation_event "
                "WHERE tenant_id=%s AND case_id=%s AND event_sequence=1",
                (self.tenant_a, self.case_a),
            ).fetchone()[0]
        params = (
            self.tenant_a,
            self.case_a,
            1,
            event_id,
            "INVESTIGATION_EVENT_RECORDED",
            datetime.now(timezone.utc),
            "{}",
            1,
            "append-idempotency",
            sha256(b"{}").hexdigest(),
            parent_event_id,
        )
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            sequence = self.conn_a.execute(
                "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                params,
            ).fetchone()[0]
            self.assertEqual(sequence, 2)
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            replay = self.conn_a.execute(
                "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                params,
            ).fetchone()[0]
            self.assertEqual(replay, 2)
            with self.assertRaises(psycopg.errors.SerializationFailure):
                self.conn_a.execute(
                    "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                    (
                        self.tenant_a,
                        self.case_a,
                        1,
                        uuid4(),
                        "INVESTIGATION_EVENT_RECORDED",
                        datetime.now(timezone.utc),
                        "{}",
                        1,
                        "stale-version-event",
                        sha256(b"{}").hexdigest(),
                        event_id,
                    ),
                )

    def test_snapshot_creation_is_deterministic_immutable_and_stale_after_event(self):
        case_id = uuid4()
        self._create_case(
            self.conn_a, self.role_a, self.tenant_a, case_id, "snapshot-case-create"
        )
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            first = self.conn_a.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_a, case_id, 1, "snapshot-create-primary"),
            ).fetchone()
            replay = self.conn_a.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_a, case_id, 1, "snapshot-create-primary"),
            ).fetchone()
            converged = self.conn_a.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_a, case_id, 1, "snapshot-create-secondary"),
            ).fetchone()
            self.assertEqual(first, replay)
            self.assertEqual(first, converged)
            stored = self.conn_a.execute(
                "SELECT canonical_snapshot_bytes, canonical_digest, "
                "encode(sha256(canonical_snapshot_bytes),'hex') "
                ", canonical_snapshot_payload "
                "FROM investigator.case_snapshot WHERE snapshot_id=%s",
                (first[0],),
            ).fetchone()
            self.assertEqual(stored[1], first[1])
            self.assertEqual(stored[1], stored[2])
            self.assertEqual(bytes(stored[0]), canonical_json_bytes(stored[3]))
            self.assertTrue(
                self.conn_a.execute(
                    "SELECT investigator.is_snapshot_current(%s,%s)",
                    (self.tenant_a, first[0]),
                ).fetchone()[0]
            )

        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn_a.execute(
                    "UPDATE investigator.case_snapshot SET canonical_digest=%s "
                    "WHERE snapshot_id=%s",
                    ("0" * 64, first[0]),
                )

        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            parent = self.conn_a.execute(
                "SELECT event_id FROM investigator.investigation_event "
                "WHERE tenant_id=%s AND case_id=%s AND event_sequence=1",
                (self.tenant_a, case_id),
            ).fetchone()[0]
            self.conn_a.execute(
                "SELECT investigator.append_event(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (
                    self.tenant_a,
                    case_id,
                    1,
                    uuid4(),
                    "INVESTIGATION_EVENT_RECORDED",
                    datetime.now(timezone.utc),
                    "{}",
                    1,
                    "snapshot-staling-event",
                    sha256(b"{}").hexdigest(),
                    parent,
                ),
            )
            self.assertFalse(
                self.conn_a.execute(
                    "SELECT investigator.is_snapshot_current(%s,%s)",
                    (self.tenant_a, first[0]),
                ).fetchone()[0]
            )
            newer = self.conn_a.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_a, case_id, 2, "snapshot-after-event"),
            ).fetchone()
            self.assertNotEqual(first[1], newer[1])
            secondary_replay = self.conn_a.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_a, case_id, 1, "snapshot-create-secondary"),
            ).fetchone()
            self.assertEqual(first, secondary_replay)
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.case_snapshot WHERE case_id=%s",
                    (case_id,),
                ).fetchone()[0],
                2,
            )

    def test_actual_runtime_two_writer_conflict_and_snapshot_convergence(self):
        case_id = uuid4()
        self._create_case(
            self.conn_a, self.role_a, self.tenant_a, case_id, "race-case-create"
        )
        parent = self.admin.execute(
            "SELECT event_id FROM investigator.investigation_event "
            "WHERE tenant_id=%s AND case_id=%s AND event_sequence=1",
            (self.tenant_a, case_id),
        ).fetchone()[0]
        barrier = threading.Barrier(2)

        def append_worker(index):
            conn = psycopg.connect(self._tenant_dsn(self.role_a, self.password_a))
            try:
                with conn.transaction():
                    self._context(conn, self.role_a, self.tenant_a)
                    barrier.wait(timeout=10)
                    return conn.execute(
                        "SELECT investigator.append_event("
                        "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                        (
                            self.tenant_a,
                            case_id,
                            1,
                            uuid4(),
                            "INVESTIGATION_EVENT_RECORDED",
                            datetime(2026, 9, 4, 13, index, tzinfo=timezone.utc),
                            "{}",
                            1,
                            f"race-event-{index}",
                            sha256(b"{}").hexdigest(),
                            parent,
                        ),
                    ).fetchone()[0]
            except psycopg.errors.SerializationFailure:
                return "version-conflict"
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            event_results = list(executor.map(append_worker, (1, 2)))
        self.assertCountEqual(event_results, (2, "version-conflict"))

        snapshot_barrier = threading.Barrier(2)

        def snapshot_worker(index):
            conn = psycopg.connect(self._tenant_dsn(self.role_a, self.password_a))
            try:
                with conn.transaction():
                    self._context(conn, self.role_a, self.tenant_a)
                    snapshot_barrier.wait(timeout=10)
                    return conn.execute(
                        "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                        (self.tenant_a, case_id, 2, f"race-snapshot-{index}"),
                    ).fetchone()
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            snapshot_results = list(executor.map(snapshot_worker, (1, 2)))
        self.assertEqual(snapshot_results[0], snapshot_results[1])
        self.assertEqual(
            self.admin.execute(
                "SELECT count(*) FROM investigator.case_snapshot_request "
                "WHERE tenant_id=%s AND case_id=%s AND expected_case_version=2",
                (self.tenant_a, case_id),
            ).fetchone()[0],
            2,
        )

    def test_snapshot_invalidation_is_audited_without_rewriting_snapshot(self):
        case_id = uuid4()
        self._create_case(
            self.conn_b, self.role_b, self.tenant_b, case_id, "invalidation-case-create"
        )
        with self.conn_b.transaction():
            self._context(self.conn_b, self.role_b, self.tenant_b)
            snapshot = self.conn_b.execute(
                "SELECT * FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant_b, case_id, 1, "snapshot-to-invalidate"),
            ).fetchone()
            before = self.conn_b.execute(
                "SELECT canonical_snapshot_bytes FROM investigator.case_snapshot "
                "WHERE snapshot_id=%s",
                (snapshot[0],),
            ).fetchone()[0]
            occurred_at = datetime.now(timezone.utc)
            invalidation = self.conn_b.execute(
                "SELECT investigator.invalidate_snapshot(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.tenant_b,
                    case_id,
                    snapshot[0],
                    1,
                    "DIGEST_MISMATCH",
                    "integrity-review-42",
                    occurred_at,
                    "snapshot-invalidation-key",
                ),
            ).fetchone()[0]
            self.assertIsNotNone(invalidation)
            after = self.conn_b.execute(
                "SELECT canonical_snapshot_bytes FROM investigator.case_snapshot "
                "WHERE snapshot_id=%s",
                (snapshot[0],),
            ).fetchone()[0]
            self.assertEqual(before, after)
            self.assertFalse(
                self.conn_b.execute(
                    "SELECT investigator.is_snapshot_current(%s,%s)",
                    (self.tenant_b, snapshot[0]),
                ).fetchone()[0]
            )
            audit = self.conn_b.execute(
                "SELECT event_type, payload->>'reason_reference', authentication_reference "
                "FROM investigator.investigation_event WHERE case_id=%s AND event_sequence=2",
                (case_id,),
            ).fetchone()
            self.assertEqual(
                audit,
                (
                    "CASE_SNAPSHOT_INVALIDATED",
                    "integrity-review-42",
                    f"postgres-login:{self.role_b}",
                ),
            )
            replay = self.conn_b.execute(
                "SELECT investigator.invalidate_snapshot(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.tenant_b,
                    case_id,
                    snapshot[0],
                    1,
                    "DIGEST_MISMATCH",
                    " integrity-review-42 ",
                    occurred_at,
                    "snapshot-invalidation-key",
                ),
            ).fetchone()[0]
            self.assertEqual(replay, invalidation)

        with self.conn_b.transaction():
            self._context(self.conn_b, self.role_b, self.tenant_b)
            with self.assertRaises(psycopg.errors.UniqueViolation):
                self.conn_b.execute(
                    "SELECT investigator.invalidate_snapshot(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        self.tenant_b,
                        case_id,
                        snapshot[0],
                        1,
                        "PROVENANCE_FAILURE",
                        "integrity-review-42",
                        occurred_at,
                        "snapshot-invalidation-key",
                    ),
                )
        self.assertEqual(
            self.admin.execute(
                "SELECT count(*) FROM investigator.case_snapshot_invalidation "
                "WHERE case_id=%s",
                (case_id,),
            ).fetchone()[0],
            1,
        )

    def test_cross_tenant_snapshot_and_missing_tenant_context_are_denied(self):
        with self.conn_a.transaction():
            self._context(self.conn_a, self.role_a, self.tenant_a)
            self.assertEqual(
                self.conn_a.execute(
                    "SELECT count(*) FROM investigator.case_snapshot WHERE tenant_id=%s",
                    (self.tenant_b,),
                ).fetchone()[0],
                0,
            )
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn_a.execute(
                    "SELECT investigator.create_snapshot(%s,%s,%s,%s)",
                    (self.tenant_b, self.case_b, 1, "forged-tenant-snapshot"),
                )
        with self.conn_a.transaction():
            self.conn_a.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier("olin_investigator_runtime")
                )
            )
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn_a.execute(
                    "SELECT investigator.create_snapshot(%s,%s,%s,%s)",
                    (self.tenant_a, self.case_a, 2, "missing-actor-snapshot"),
                )


if __name__ == "__main__":
    unittest.main()
