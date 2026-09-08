"""Real PostgreSQL Phase 2 evidence-reference boundary tests.

The suite requires the same explicitly disposable PostgreSQL 16 database as
the accepted Phase 1 boundary suite. Runtime and evidence-authority assertions
use distinct tenant-bound login roles; owner/admin connections are never used
as a runtime substitute.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from olin.investigator.canonical import canonical_digest, normalize_timestamp
from olin.investigator.evidence import (
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    EvidenceAuthorityResolution,
    EvidenceReference,
    EvidenceUsability,
)

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
class InvestigatorPhase2MigrationFailureTests(unittest.TestCase):
    def test_dirty_authority_and_public_function_exposure_abort_atomically(self):
        root = Path(__file__).resolve().parent
        admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        phase2 = (
            root
            / "db"
            / "migrations"
            / "0003_investigator_evidence_consent_passport.sql"
        ).read_text(encoding="utf-8")
        try:
            for migration_name in (
                "0001_investigator_phase0.sql",
                "0002_investigator_case_event_snapshot.sql",
            ):
                admin.execute(
                    (root / "db" / "migrations" / migration_name).read_text(
                        encoding="utf-8"
                    )
                )
            admin.execute(
                "CREATE ROLE olin_investigator_evidence_authority NOLOGIN NOINHERIT"
            )
            admin.execute("CREATE ROLE unexpected_evidence_grantee NOLOGIN")
            admin.execute(
                "GRANT olin_investigator_evidence_authority "
                "TO unexpected_evidence_grantee"
            )
            with self.assertRaises(psycopg.Error):
                admin.execute(phase2)
            admin.execute("ROLLBACK")
            self.assertIsNone(
                admin.execute(
                    "SELECT to_regclass('investigator.investigation_evidence_reference')"
                ).fetchone()[0]
            )
            admin.execute(
                "REVOKE olin_investigator_evidence_authority "
                "FROM unexpected_evidence_grantee"
            )
            admin.execute("DROP ROLE unexpected_evidence_grantee")
            admin.execute("DROP ROLE olin_investigator_evidence_authority")
            admin.execute(
                "CREATE FUNCTION public.legacy_provider_call() RETURNS void "
                "LANGUAGE plpgsql AS 'BEGIN NULL; END'"
            )
            with self.assertRaises(psycopg.Error):
                admin.execute(phase2)
            admin.execute("ROLLBACK")
            self.assertIsNone(
                admin.execute(
                    "SELECT to_regclass('investigator.investigation_evidence_reference')"
                ).fetchone()[0]
            )
            self.assertIsNone(
                admin.execute(
                    "SELECT 1 FROM pg_roles "
                    "WHERE rolname='olin_investigator_evidence_authority'"
                ).fetchone()
            )
        finally:
            admin.execute("DROP FUNCTION IF EXISTS public.legacy_provider_call()")
            admin.execute("DROP SCHEMA IF EXISTS investigator CASCADE")
            admin.execute("DROP ROLE IF EXISTS unexpected_evidence_grantee")
            admin.execute("DROP ROLE IF EXISTS olin_investigator_evidence_authority")
            admin.execute("DROP ROLE IF EXISTS olin_investigator_runtime")
            admin.execute("DROP ROLE IF EXISTS olin_investigator_owner")
            admin.close()


@unittest.skipUnless(
    POSTGRES_AVAILABLE, "explicitly disposable PostgreSQL DSN/psycopg required"
)
class InvestigatorPostgresEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent
        parsed = conninfo_to_dict(ADMIN_DSN)
        if not str(parsed.get("dbname", "")).endswith("_investigator_test"):
            raise RuntimeError(
                "PostgreSQL harness requires a database ending _investigator_test"
            )
        cls.tenant = uuid4()
        cls.other_tenant = uuid4()
        cls.runtime_role = "olin_inv_t_" + cls.tenant.hex
        cls.authority_role = "olin_evidence_t_" + cls.tenant.hex
        cls.other_authority_role = "olin_evidence_t_" + cls.other_tenant.hex
        cls.passwords = {
            role: secrets.token_urlsafe(24)
            for role in (
                cls.runtime_role,
                cls.authority_role,
                cls.other_authority_role,
            )
        }
        cls.admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        identity = cls.admin.execute("SELECT session_user,current_user").fetchone()
        for migration_name in (
            "0001_investigator_phase0.sql",
            "0002_investigator_case_event_snapshot.sql",
            "0003_investigator_evidence_consent_passport.sql",
        ):
            migration = (cls.root / "db" / "migrations" / migration_name).read_text(
                encoding="utf-8"
            )
            cls.admin.execute(migration)
            if (
                cls.admin.execute("SELECT session_user,current_user").fetchone()
                != identity
            ):
                raise AssertionError(
                    f"{migration_name} did not restore session authorization"
                )
        for role, password in cls.passwords.items():
            cls.admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
        cls.admin.execute(
            sql.SQL("GRANT olin_investigator_runtime TO {}").format(
                sql.Identifier(cls.runtime_role)
            )
        )
        for role in (cls.authority_role, cls.other_authority_role):
            cls.admin.execute(
                sql.SQL("GRANT olin_investigator_evidence_authority TO {}").format(
                    sql.Identifier(role)
                )
            )
        cls.runtime = psycopg.connect(
            cls._dsn(cls.runtime_role, cls.passwords[cls.runtime_role])
        )
        cls.authority = psycopg.connect(
            cls._dsn(cls.authority_role, cls.passwords[cls.authority_role])
        )
        cls.other_authority = psycopg.connect(
            cls._dsn(
                cls.other_authority_role,
                cls.passwords[cls.other_authority_role],
            )
        )

    def setUp(self):
        self.case_id = uuid4()
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            self.runtime.execute(
                "SELECT investigator.create_case("
                "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                (
                    self.case_id,
                    self.tenant,
                    None,
                    "phase2-postgres",
                    uuid4(),
                    datetime.now(timezone.utc),
                    "{}",
                    1,
                    f"phase2-case-{self._testMethodName}",
                    sha256(b"{}").hexdigest(),
                    "{}",
                ),
            )
            self.initial_snapshot_id = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (
                    self.tenant,
                    self.case_id,
                    1,
                    f"phase2-snapshot-{self._testMethodName}",
                ),
            ).fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        cls.authority.close()
        cls.other_authority.close()
        cls.admin.execute(
            sql.SQL("REVOKE olin_investigator_runtime FROM {}").format(
                sql.Identifier(cls.runtime_role)
            )
        )
        for role in (cls.authority_role, cls.other_authority_role):
            cls.admin.execute(
                sql.SQL("REVOKE olin_investigator_evidence_authority FROM {}").format(
                    sql.Identifier(role)
                )
            )
        for role in cls.passwords:
            cls.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        cls.admin.execute("DROP SCHEMA investigator CASCADE")
        cls.admin.execute("DROP ROLE olin_investigator_evidence_authority")
        cls.admin.execute("DROP ROLE olin_investigator_runtime")
        cls.admin.execute("DROP ROLE olin_investigator_owner")
        cls.admin.close()

    @classmethod
    def _dsn(cls, role, password):
        values = conninfo_to_dict(ADMIN_DSN)
        values.update(user=role, password=password)
        return make_conninfo(**values)

    @classmethod
    def _runtime_context(cls, connection):
        connection.execute("SET LOCAL ROLE olin_investigator_runtime")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)", (str(cls.tenant),)
        )

    @classmethod
    def _authority_context(cls, connection, tenant=None):
        connection.execute("SET LOCAL ROLE olin_investigator_evidence_authority")
        connection.execute(
            "SELECT set_config('olin.tenant_id',%s,true)",
            (str(tenant or cls.tenant),),
        )

    def _reference(self, **changes):
        current = datetime.now(timezone.utc)
        values = {
            "tenant_id": str(self.tenant),
            "case_id": str(self.case_id),
            "reference_id": str(uuid4()),
            "subject_id": "canonical-business-1",
            "subject_digest": "1" * 64,
            "evidence_namespace": "evidence_passport",
            "evidence_id": "artifact-" + uuid4().hex,
            "evidence_version": "1",
            "artifact_digest": sha256(uuid4().bytes).hexdigest(),
            "authority_digest": "0" * 64,
            "evidence_class": "VERIFIED_FACT",
            "lifecycle": "ACCEPTED",
            "verification_status": "VERIFIED_FOR_PROPOSITION",
            "proposition_type": "bank_reported_transaction",
            "proposition_schema_version": 1,
            "proposition_value": "opaque-event-1",
            "proposition_unit": "event",
            "verification_method": "signed_provider_record_match",
            "period_start": (current - timedelta(days=1)).isoformat(),
            "period_end": (current - timedelta(days=1)).isoformat(),
            "observed_at": (current - timedelta(days=1)).isoformat(),
            "evidence_expires_at": (current + timedelta(days=30)).isoformat(),
            "source_id": "bank_api",
            "issuer_id": "bank-issuer",
            "acquisition_method": "signed_webhook",
            "source_class": "regulated_financial_institution",
            "source_attestation_id": "attestation-1",
            "source_attestation_version": "1",
            "source_registry_digest": "3" * 64,
            "source_valid_until": (current + timedelta(days=90)).isoformat(),
            "production_qualified_source": True,
            "source_allows_proposition": True,
            "consent_namespace": "intake_consent",
            "consent_id": "consent-1",
            "consent_version": "receipt-1",
            "consent_purpose": "investigator_analysis",
            "consent_data_class": "bank_transaction_metadata",
            "consent_use_scope": "case_evidence_analysis",
            "consent_status": "ACTIVE",
            "consent_expires_at": (current + timedelta(days=30)).isoformat(),
            "retention_until": (current + timedelta(days=60)).isoformat(),
            "integrity_valid": True,
            "integrity_reference": "passport-integrity-1",
            "resolver_version": "investigator-evidence-resolver-1.0",
            "accepted_at": current.isoformat(),
            "supersedes_reference_id": None,
        }
        values.update(changes)
        if "authority_digest" not in changes:

            def timestamp(name):
                return (
                    normalize_timestamp(datetime.fromisoformat(values[name]))
                    if values[name] is not None
                    else None
                )

            values["authority_digest"] = canonical_digest(
                {
                    "artifact": {
                        "artifact_digest": values["artifact_digest"],
                        "evidence_class": values["evidence_class"],
                        "evidence_id": values["evidence_id"],
                        "evidence_namespace": values["evidence_namespace"],
                        "evidence_version": values["evidence_version"],
                        "expires_at": timestamp("evidence_expires_at"),
                        "lifecycle": values["lifecycle"],
                        "observed_at": timestamp("observed_at"),
                        "period_end": timestamp("period_end"),
                        "period_start": timestamp("period_start"),
                    },
                    "consent": {
                        "consent_data_class": values["consent_data_class"],
                        "consent_id": values["consent_id"],
                        "consent_namespace": values["consent_namespace"],
                        "consent_purpose": values["consent_purpose"],
                        "consent_use_scope": values["consent_use_scope"],
                        "consent_version": values["consent_version"],
                        "expires_at": timestamp("consent_expires_at"),
                        "retention_until": timestamp("retention_until"),
                        "status": values["consent_status"],
                    },
                    "integrity": {
                        "integrity_reference": values["integrity_reference"],
                        "integrity_valid": values["integrity_valid"],
                    },
                    "proposition_verification": {
                        "proposition_schema_version": values[
                            "proposition_schema_version"
                        ],
                        "proposition_type": values["proposition_type"],
                        "proposition_unit": values["proposition_unit"],
                        "proposition_value": values["proposition_value"],
                        "verification_method": values["verification_method"],
                        "status": values["verification_status"],
                    },
                    "resolver_version": values["resolver_version"],
                    "source_attestation": {
                        "acquisition_method": values["acquisition_method"],
                        "attestation_id": values["source_attestation_id"],
                        "attestation_version": values["source_attestation_version"],
                        "issuer_id": values["issuer_id"],
                        "production_qualified": values["production_qualified_source"],
                        "proposition_allowed": values["source_allows_proposition"],
                        "registry_digest": values["source_registry_digest"],
                        "source_class": values["source_class"],
                        "source_id": values["source_id"],
                        "valid_until": timestamp("source_valid_until"),
                    },
                    "subject": {
                        "subject_digest": values["subject_digest"],
                        "subject_id": values["subject_id"],
                    },
                    "tenant_case": {
                        "case_id": values["case_id"],
                        "tenant_id": values["tenant_id"],
                    },
                }
            )
        return values

    @staticmethod
    def _python_reference(values):
        def parsed(name):
            return (
                datetime.fromisoformat(values[name])
                if values[name] is not None
                else None
            )

        resolution = EvidenceAuthorityResolution._from_authoritative_adapter(
            tenant_id=UUID(values["tenant_id"]),
            case_id=UUID(values["case_id"]),
            subject_id=values["subject_id"],
            subject_digest=values["subject_digest"],
            evidence_namespace=values["evidence_namespace"],
            evidence_id=values["evidence_id"],
            evidence_version=values["evidence_version"],
            artifact_digest=values["artifact_digest"],
            evidence_class=values["evidence_class"],
            lifecycle=values["lifecycle"],
            verification_status=values["verification_status"],
            proposition_type=values["proposition_type"],
            proposition_schema_version=values["proposition_schema_version"],
            proposition_value=values["proposition_value"],
            proposition_unit=values["proposition_unit"],
            verification_method=values["verification_method"],
            period_start=parsed("period_start"),
            period_end=parsed("period_end"),
            observed_at=parsed("observed_at"),
            evidence_expires_at=parsed("evidence_expires_at"),
            source_id=values["source_id"],
            issuer_id=values["issuer_id"],
            acquisition_method=values["acquisition_method"],
            source_class=values["source_class"],
            source_attestation_id=values["source_attestation_id"],
            source_attestation_version=values["source_attestation_version"],
            source_registry_digest=values["source_registry_digest"],
            source_valid_until=parsed("source_valid_until"),
            production_qualified_source=values["production_qualified_source"],
            source_allows_proposition=values["source_allows_proposition"],
            consent_namespace=values["consent_namespace"],
            consent_id=values["consent_id"],
            consent_version=values["consent_version"],
            consent_purpose=values["consent_purpose"],
            consent_data_class=values["consent_data_class"],
            consent_use_scope=values["consent_use_scope"],
            consent_status=values["consent_status"],
            consent_expires_at=parsed("consent_expires_at"),
            retention_until=parsed("retention_until"),
            integrity_reference=values["integrity_reference"],
            integrity_valid=values["integrity_valid"],
            usability=EvidenceUsability.USABLE,
            unusable_reason=None,
            resolver_version=EVIDENCE_RESOLVER_CONTRACT_VERSION,
            resolved_at=parsed("accepted_at"),
        )
        if resolution.authority_digest() != values["authority_digest"]:
            raise AssertionError("test authority digest does not match resolution")
        return EvidenceReference.from_resolution(
            reference_id=UUID(values["reference_id"]),
            resolution=resolution,
            supersedes_reference_id=UUID(values["supersedes_reference_id"])
            if values["supersedes_reference_id"]
            else None,
            accepted_at=parsed("accepted_at"),
        )

    def test_roles_rls_and_privileges_remain_separated(self):
        roles = self.admin.execute(
            "SELECT rolname,rolsuper,rolcreaterole,rolbypassrls,rolcanlogin "
            "FROM pg_roles WHERE rolname IN ("
            "'olin_investigator_runtime','olin_investigator_owner',"
            "'olin_investigator_evidence_authority') ORDER BY rolname"
        ).fetchall()
        roles = [
            (
                row[0].decode("ascii") if isinstance(row[0], bytes) else row[0],
                *row[1:],
            )
            for row in roles
        ]
        self.assertEqual(
            roles,
            [
                ("olin_investigator_evidence_authority", False, False, False, False),
                ("olin_investigator_owner", False, False, False, False),
                ("olin_investigator_runtime", False, False, False, False),
            ],
        )
        table = self.admin.execute(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
            "WHERE oid='investigator.investigation_evidence_reference'::regclass"
        ).fetchone()
        self.assertEqual(table, (True, True))
        privileges = self.admin.execute(
            "SELECT "
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_evidence_reference','SELECT'),"
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_evidence_reference','INSERT,UPDATE,DELETE,TRUNCATE'),"
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.accept_evidence_reference(jsonb,uuid,bigint,uuid,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.create_snapshot_v2(uuid,uuid,bigint,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.is_snapshot_structurally_current_v2(uuid,uuid)','EXECUTE'),"
            "has_table_privilege('olin_investigator_evidence_authority',"
            "'investigator.investigation_evidence_reference','SELECT'),"
            "has_table_privilege('olin_investigator_evidence_authority',"
            "'investigator.investigation_evidence_reference','INSERT,UPDATE,DELETE,TRUNCATE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'investigator.accept_evidence_reference(jsonb,uuid,bigint,uuid,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'investigator.append_evidence_authority_event(uuid,uuid,bigint,uuid,text,jsonb,timestamptz,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'investigator.mark_evidence_unusable(uuid,uuid,uuid,uuid,bigint,uuid,text,text,timestamptz,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'investigator.is_snapshot_structurally_current_v2(uuid,uuid)','EXECUTE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'investigator.create_snapshot_v2(uuid,uuid,bigint,text)','EXECUTE')"
        ).fetchone()
        self.assertEqual(
            privileges,
            (
                True,
                False,
                False,
                True,
                False,
                False,
                False,
                True,
                False,
                True,
                True,
                False,
            ),
        )

    def test_runtime_cannot_promote_or_directly_mutate_evidence(self):
        reference = self._reference()
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.runtime.execute(
                    "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(reference),
                        self.initial_snapshot_id,
                        1,
                        uuid4(),
                        "runtime-promotion-denied",
                    ),
                )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.runtime.execute(
                    "INSERT INTO investigator.investigation_evidence_reference "
                    "(reference_id) VALUES (%s)",
                    (uuid4(),),
                )

    def test_authority_acceptance_is_idempotent_and_caller_labels_fail(self):
        reference = self._reference()
        event_id = uuid4()
        key = "authority-acceptance-1"
        with self.authority.transaction():
            self._authority_context(self.authority)
            accepted = self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (json.dumps(reference), self.initial_snapshot_id, 1, event_id, key),
            ).fetchone()[0]
            replay = self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (json.dumps(reference), self.initial_snapshot_id, 1, event_id, key),
            ).fetchone()[0]
        self.assertEqual(accepted, replay)
        stale_reference = self._reference()
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.SerializationFailure):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(stale_reference),
                        self.initial_snapshot_id,
                        2,
                        uuid4(),
                        "stale-snapshot-new-evidence",
                    ),
                )
        forged = self._reference(verified=True)
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(forged),
                        self.initial_snapshot_id,
                        1,
                        uuid4(),
                        "caller-label-denied",
                    ),
                )

    def test_cross_tenant_authority_is_denied(self):
        reference = self._reference()
        with self.other_authority.transaction():
            self._authority_context(self.other_authority, self.other_tenant)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.other_authority.execute(
                    "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(reference),
                        self.initial_snapshot_id,
                        1,
                        uuid4(),
                        "cross-tenant-denied",
                    ),
                )

    def test_future_unbounded_or_collusive_evidence_is_denied(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        attempts = (
            {"observed_at": future.isoformat()},
            {"period_end": future.isoformat()},
            {"evidence_expires_at": None},
            {"source_class": "merchant_controlled"},
            {
                "accepted_at": future.isoformat(),
                "observed_at": future.isoformat(),
                "period_start": future.isoformat(),
                "period_end": future.isoformat(),
                "evidence_expires_at": (future + timedelta(days=30)).isoformat(),
            },
        )
        for index, changes in enumerate(attempts):
            reference = self._reference(**changes)
            with (
                self.subTest(changes=changes),
                self.authority.transaction(),
            ):
                self._authority_context(self.authority)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    self.authority.execute(
                        "SELECT investigator.accept_evidence_reference("
                        "%s::jsonb,%s,%s,%s,%s)",
                        (
                            json.dumps(reference),
                            self.initial_snapshot_id,
                            1,
                            uuid4(),
                            f"temporal-source-denied-{index}",
                        ),
                    )

    def test_concurrent_identical_acceptance_converges(self):
        reference = self._reference()
        event_id = uuid4()
        barrier = threading.Barrier(2)

        def accept_once():
            connection = psycopg.connect(
                self._dsn(self.authority_role, self.passwords[self.authority_role])
            )
            try:
                with connection.transaction():
                    self._authority_context(connection)
                    barrier.wait(timeout=5)
                    return connection.execute(
                        "SELECT investigator.accept_evidence_reference("
                        "%s::jsonb,%s,%s,%s,%s)",
                        (
                            json.dumps(reference),
                            self.initial_snapshot_id,
                            1,
                            event_id,
                            "concurrent-identical-acceptance",
                        ),
                    ).fetchone()[0]
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _: accept_once(), range(2)))
        self.assertEqual(results, (results[0], results[0]))

    def test_correction_lineage_is_preserved_and_old_reference_becomes_unusable(self):
        first = self._reference(evidence_id="corrected-evidence", evidence_version="1")
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(first),
                    self.initial_snapshot_id,
                    1,
                    uuid4(),
                    "correction-first",
                ),
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            current = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 2, "snapshot-before-correction"),
            ).fetchone()[0]
        second = self._reference(
            evidence_id="corrected-evidence",
            evidence_version="2",
            artifact_digest=first["artifact_digest"],
            supersedes_reference_id=first["reference_id"],
        )
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(second),
                    current,
                    2,
                    uuid4(),
                    "correction-second",
                ),
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            replacement = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 3, "snapshot-after-correction"),
            ).fetchone()[0]
            evidence = self.runtime.execute(
                "SELECT canonical_snapshot_payload->'evidence' "
                "FROM investigator.case_snapshot WHERE snapshot_id=%s",
                (replacement,),
            ).fetchone()[0]
        self.assertEqual(len(evidence["accepted_evidence_refs"]), 1)
        self.assertEqual(len(evidence["unusable_evidence_refs"]), 1)
        self.assertEqual(
            evidence["accepted_evidence_refs"][0]["acceptance"][
                "supersedes_reference_id"
            ],
            first["reference_id"],
        )
        self.assertEqual(
            evidence["unusable_evidence_refs"][0]["unusable_reason"],
            "EVIDENCE_SUPERSEDED",
        )

    def test_successor_cannot_launder_another_lineage_artifact_digest(self):
        first = self._reference(evidence_id="lineage-a", evidence_version="1")
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(first),
                    self.initial_snapshot_id,
                    1,
                    uuid4(),
                    "lineage-a-root",
                ),
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            after_first = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 2, "snapshot-after-lineage-a"),
            ).fetchone()[0]
        second = self._reference(evidence_id="lineage-b", evidence_version="1")
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(second),
                    after_first,
                    2,
                    uuid4(),
                    "lineage-b-root",
                ),
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            after_second = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 3, "snapshot-after-lineage-b"),
            ).fetchone()[0]
        laundering = self._reference(
            evidence_id="lineage-a",
            evidence_version="2",
            artifact_digest=second["artifact_digest"],
            supersedes_reference_id=first["reference_id"],
        )
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.UniqueViolation):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference("
                    "%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(laundering),
                        after_second,
                        3,
                        uuid4(),
                        "cross-lineage-digest-denied",
                    ),
                )

    def test_snapshot_v2_is_current_then_state_change_preserves_history(self):
        reference = self._reference()
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(reference),
                    self.initial_snapshot_id,
                    1,
                    uuid4(),
                    "snapshot-test-acceptance",
                ),
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            snapshot = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 2, "phase2-current-snapshot"),
            ).fetchone()[0]
            initial_evidence = self.runtime.execute(
                "SELECT canonical_snapshot_payload->'evidence' "
                "FROM investigator.case_snapshot WHERE snapshot_id=%s",
                (snapshot,),
            ).fetchone()[0]
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.assertTrue(
                self.authority.execute(
                    "SELECT investigator.is_snapshot_structurally_current_v2(%s,%s)",
                    (self.tenant, snapshot),
                ).fetchone()[0]
            )
        python_record = self._python_reference(reference).canonical_record()
        self.assertEqual(initial_evidence["accepted_evidence_refs"], [python_record])
        self.assertEqual(initial_evidence["unusable_evidence_refs"], [])
        self.assertEqual(
            initial_evidence["evidence_state_digest"],
            canonical_digest(
                {
                    "accepted_reference_ids": [reference["reference_id"]],
                    "unusable_references": [],
                    "evidence_state_version": 1,
                    "references": [python_record],
                }
            ),
        )
        reference_id = self.admin.execute(
            "SELECT reference_id FROM investigator.investigation_evidence_reference "
            "WHERE case_id=%s",
            (self.case_id,),
        ).fetchone()[0]
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.mark_evidence_unusable("
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        self.tenant,
                        self.case_id,
                        snapshot,
                        reference_id,
                        2,
                        uuid4(),
                        "EVIDENCE_REVOKED",
                        "future-state-event",
                        datetime.now(timezone.utc) + timedelta(days=1),
                        "future-state-event-denied",
                    ),
                )
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.mark_evidence_unusable("
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self.tenant,
                    self.case_id,
                    snapshot,
                    reference_id,
                    2,
                    uuid4(),
                    "EVIDENCE_REVOKED",
                    "canonical-revocation-1",
                    datetime.now(timezone.utc),
                    "evidence-revoked-event",
                ),
            )
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.assertFalse(
                self.authority.execute(
                    "SELECT investigator.is_snapshot_structurally_current_v2(%s,%s)",
                    (self.tenant, snapshot),
                ).fetchone()[0]
            )
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            replacement = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 3, "phase2-unusable-snapshot"),
            ).fetchone()[0]
            evidence = self.runtime.execute(
                "SELECT canonical_snapshot_payload->'evidence' "
                "FROM investigator.case_snapshot WHERE snapshot_id=%s",
                (replacement,),
            ).fetchone()[0]
        self.assertEqual(len(evidence["accepted_evidence_refs"]), 0)
        self.assertEqual(len(evidence["unusable_evidence_refs"]), 1)
        unusable = evidence["unusable_evidence_refs"][0]
        self.assertEqual(unusable["unusable_reason"], "EVIDENCE_REVOKED")
        self.assertEqual(unusable["artifact"]["evidence_class"], "VERIFIED_FACT")
        self.assertEqual(
            unusable["proposition_verification"]["proposition_value"],
            "opaque-event-1",
        )
        self.assertEqual(
            unusable["acceptance"]["authority_digest"],
            reference["authority_digest"],
        )
        self.assertEqual(
            self.admin.execute(
                "SELECT count(*) FROM investigator.investigation_evidence_reference"
                " WHERE case_id=%s",
                (self.case_id,),
            ).fetchone()[0],
            1,
        )

    def test_authority_cannot_append_orphan_state_events_or_unbounded_references(self):
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.authority.execute(
                    "SELECT investigator.append_evidence_authority_event("
                    "%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
                    (
                        self.tenant,
                        self.case_id,
                        1,
                        uuid4(),
                        "EVIDENCE_ACCEPTED",
                        json.dumps(
                            {
                                "reference_id": str(uuid4()),
                                "evidence_state_version": 1,
                            }
                        ),
                        datetime.now(timezone.utc),
                        "orphan-direct-appender",
                    ),
                )
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.NoDataFound):
                self.authority.execute(
                    "SELECT investigator.mark_evidence_unusable("
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        self.tenant,
                        self.case_id,
                        self.initial_snapshot_id,
                        uuid4(),
                        1,
                        uuid4(),
                        "EVIDENCE_REVOKED",
                        "missing-reference",
                        datetime.now(timezone.utc),
                        "orphan-dedicated-command",
                    ),
                )
        oversized = self._reference(proposition_value="x" * 513)
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(oversized),
                        self.initial_snapshot_id,
                        1,
                        uuid4(),
                        "oversized-reference-denied",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
