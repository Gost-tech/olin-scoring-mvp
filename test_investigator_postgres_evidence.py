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

from olin.investigator.authority import (
    AuthorityDenied,
    assert_evidence_authority_database_custody,
    assert_runtime_database_custody,
    establish_runtime_database_custody,
)
from olin.investigator.canonical import (
    canonical_digest,
    canonical_json_bytes,
    normalize_timestamp,
)
from olin.investigator.evidence import (
    EVIDENCE_RESOLVER_CONTRACT_VERSION,
    EvidenceAuthorityResolution,
    EvidenceBoundaryError,
    EvidenceReference,
    EvidenceUsability,
)
from olin.investigator.evidence_boundary import PostgresReasoningSnapshotGate
from olin.investigator_evidence_adapter import PostgresCanonicalEvidenceReadPort

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
    _CANONICAL_REFERENCE_FIELDS = (
        "tenant_id",
        "case_id",
        "subject_id",
        "subject_digest",
        "evidence_namespace",
        "evidence_id",
        "evidence_version",
        "artifact_digest",
        "authority_digest",
        "evidence_class",
        "lifecycle",
        "verification_status",
        "proposition_type",
        "proposition_schema_version",
        "proposition_value",
        "proposition_unit",
        "verification_method",
        "period_start",
        "period_end",
        "observed_at",
        "evidence_expires_at",
        "source_id",
        "issuer_id",
        "acquisition_method",
        "source_class",
        "source_attestation_id",
        "source_attestation_version",
        "source_registry_digest",
        "source_valid_until",
        "production_qualified_source",
        "source_allows_proposition",
        "consent_namespace",
        "consent_id",
        "consent_version",
        "consent_purpose",
        "consent_data_class",
        "consent_use_scope",
        "consent_status",
        "consent_expires_at",
        "retention_until",
        "integrity_valid",
        "integrity_reference",
        "resolver_version",
    )

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
        cls.admin.execute("DROP SCHEMA IF EXISTS evidence_authority CASCADE")
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
        semantic_independence = changes.pop("_semantic_independence", None)
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

            authority_record = {
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
                    "proposition_schema_version": values["proposition_schema_version"],
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
            if semantic_independence is not None:
                authority_record["semantic_independence"] = semantic_independence
            values["authority_digest"] = canonical_digest(authority_record)
        return values

    @classmethod
    def _canonical_projection(cls, reference, semantics):
        canonical_reference = {
            field: reference[field] for field in cls._CANONICAL_REFERENCE_FIELDS
        }
        return {
            "projection_version": "canonical-evidence-projection-1",
            "authority_digest": reference["authority_digest"],
            "canonical_reference": canonical_reference,
            **canonical_reference,
            "reference_id": reference["reference_id"],
            "accepted_at": reference["accepted_at"],
            "supersedes_reference_id": reference["supersedes_reference_id"],
            "semantic_independence_schema_version": semantics[
                "semantic_schema_version"
            ],
            "semantic_lineage_id": semantics["semantic_lineage_id"],
            "lineage_relation": semantics["lineage_relation"],
            "derived_from_evidence_namespace": semantics[
                "derived_from_evidence_namespace"
            ],
            "derived_from_evidence_id": semantics["derived_from_evidence_id"],
            "derived_from_evidence_version": semantics["derived_from_evidence_version"],
            "economic_event_id": semantics["economic_event_id"],
            "upstream_issuer_id": semantics["upstream_issuer_id"],
            "independence_status": semantics["independence_status"],
            "independence_attestation_id": semantics["independence_attestation_id"],
            "independence_attestation_version": semantics[
                "independence_attestation_version"
            ],
            "usability": "USABLE",
            "unusable_reason": None,
        }

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
            semantic_independence_schema_version=None,
            semantic_lineage_id="legacy-phase2-lineage",
            lineage_relation="UNKNOWN",
            derived_from_evidence_namespace=None,
            derived_from_evidence_id=None,
            derived_from_evidence_version=None,
            economic_event_id=None,
            upstream_issuer_id=values["issuer_id"],
            independence_status="INDEPENDENCE_UNKNOWN",
            independence_attestation_id=None,
            independence_attestation_version=None,
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
            assert_evidence_authority_database_custody(self.authority)
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

    def test_z_phase25_semantic_lineage_and_credential_custody(self):
        identity = self.admin.execute("SELECT session_user,current_user").fetchone()
        upgrade_case_id = uuid4()
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            self.runtime.execute(
                "SELECT investigator.create_case("
                "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                (
                    upgrade_case_id,
                    self.tenant,
                    None,
                    "phase2-upgrade-path",
                    uuid4(),
                    datetime.now(timezone.utc),
                    "{}",
                    1,
                    "phase2-upgrade-case",
                    sha256(b"{}").hexdigest(),
                    "{}",
                ),
            )
            upgrade_initial_snapshot = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot(%s,%s,%s,%s)",
                (self.tenant, upgrade_case_id, 1, "phase2-upgrade-initial"),
            ).fetchone()[0]
        legacy_root = self._reference(
            case_id=str(upgrade_case_id),
            evidence_id="phase2-upgrade-evidence",
            evidence_version="1",
        )
        legacy_root_event = uuid4()
        with self.authority.transaction():
            self._authority_context(self.authority)
            accepted_root = self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(legacy_root),
                    upgrade_initial_snapshot,
                    1,
                    legacy_root_event,
                    "phase2-upgrade-root",
                ),
            ).fetchone()[0]
            replayed_root = self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(legacy_root),
                    upgrade_initial_snapshot,
                    1,
                    legacy_root_event,
                    "phase2-upgrade-root",
                ),
            ).fetchone()[0]
        self.assertEqual(replayed_root, accepted_root)
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            upgrade_after_root = self.runtime.execute(
                "SELECT snapshot_id FROM investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, upgrade_case_id, 2, "phase2-upgrade-after-root"),
            ).fetchone()[0]
        legacy_correction = self._reference(
            case_id=str(upgrade_case_id),
            evidence_id=legacy_root["evidence_id"],
            evidence_version="2",
            artifact_digest=legacy_root["artifact_digest"],
            supersedes_reference_id=legacy_root["reference_id"],
        )
        with self.authority.transaction():
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference(%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(legacy_correction),
                    upgrade_after_root,
                    2,
                    uuid4(),
                    "phase2-upgrade-correction",
                ),
            )
        legacy_history_before = self.admin.execute(
            "SELECT reference_id,tenant_id,case_id,evidence_namespace,evidence_id,"
            "evidence_version,artifact_digest,authority_digest,"
            "supersedes_reference_id,acceptance_event_id,acceptance_request_digest "
            "FROM investigator.investigation_evidence_reference "
            "WHERE tenant_id=%s AND case_id=%s ORDER BY evidence_version",
            (self.tenant, upgrade_case_id),
        ).fetchall()
        self.assertEqual(len(legacy_history_before), 2)
        migration = (
            self.root
            / "db"
            / "migrations"
            / "0004_investigator_evidence_reasoning_readiness.sql"
        ).read_text(encoding="utf-8")
        self.admin.execute(migration)
        self.assertEqual(
            self.admin.execute("SELECT session_user,current_user").fetchone(), identity
        )
        self.assertEqual(
            self.admin.execute(
                "SELECT reference_id,tenant_id,case_id,evidence_namespace,evidence_id,"
                "evidence_version,artifact_digest,authority_digest,"
                "supersedes_reference_id,acceptance_event_id,"
                "acceptance_request_digest "
                "FROM investigator.investigation_evidence_reference "
                "WHERE tenant_id=%s AND case_id=%s ORDER BY evidence_version",
                (self.tenant, upgrade_case_id),
            ).fetchall(),
            legacy_history_before,
        )
        self.assertFalse(
            self.admin.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM investigator.investigation_evidence_reference ref "
                "LEFT JOIN investigator.investigation_evidence_semantics sem "
                "USING (tenant_id,case_id,reference_id) "
                "WHERE sem.reference_id IS NULL)"
            ).fetchone()[0]
        )
        migrated_semantics = self.admin.execute(
            "SELECT ref.reference_id,ref.evidence_version,"
            "ref.supersedes_reference_id,sem.tenant_id,sem.case_id,"
            "sem.semantic_schema_version,sem.semantic_lineage_id,"
            "sem.lineage_relation,sem.derived_from_evidence_namespace,"
            "sem.derived_from_evidence_id,sem.derived_from_evidence_version,"
            "sem.economic_event_id,sem.independence_status,"
            "sem.independence_attestation_id,"
            "sem.independence_attestation_version "
            "FROM investigator.investigation_evidence_reference ref "
            "JOIN investigator.investigation_evidence_semantics sem "
            "USING (tenant_id,case_id,reference_id) "
            "WHERE ref.tenant_id=%s AND ref.case_id=%s "
            "ORDER BY ref.evidence_version",
            (self.tenant, upgrade_case_id),
        ).fetchall()
        self.assertEqual(len(migrated_semantics), 2)
        root_semantics, correction_semantics = migrated_semantics
        self.assertEqual(root_semantics[0], UUID(legacy_root["reference_id"]))
        self.assertEqual(root_semantics[2], None)
        self.assertEqual(root_semantics[3:6], (self.tenant, upgrade_case_id, 0))
        self.assertEqual(root_semantics[7:11], ("UNKNOWN", None, None, None))
        self.assertEqual(
            root_semantics[11:], (None, "INDEPENDENCE_UNKNOWN", None, None)
        )
        self.assertEqual(
            correction_semantics[0], UUID(legacy_correction["reference_id"])
        )
        self.assertEqual(correction_semantics[2], UUID(legacy_root["reference_id"]))
        self.assertEqual(correction_semantics[3:6], (self.tenant, upgrade_case_id, 0))
        self.assertEqual(correction_semantics[6], root_semantics[6])
        self.assertEqual(
            correction_semantics[7:11],
            (
                "CORRECTION",
                legacy_root["evidence_namespace"],
                legacy_root["evidence_id"],
                legacy_root["evidence_version"],
            ),
        )
        self.assertEqual(
            correction_semantics[11:],
            (None, "INDEPENDENCE_UNKNOWN", None, None),
        )
        self.assertEqual(
            self.admin.execute(
                "SELECT count(*) FROM investigator.investigation_evidence_semantics "
                "WHERE semantic_schema_version=0 "
                "AND independence_status='INDEPENDENT_VERIFIED'"
            ).fetchone()[0],
            0,
        )

        semantics = {
            "semantic_schema_version": 1,
            "semantic_lineage_id": "lineage-bank-event-1",
            "lineage_relation": "ORIGINAL",
            "derived_from_evidence_namespace": None,
            "derived_from_evidence_id": None,
            "derived_from_evidence_version": None,
            "economic_event_id": None,
            "upstream_issuer_id": "bank-issuer",
            "independence_status": "INDEPENDENCE_UNKNOWN",
            "independence_attestation_id": None,
            "independence_attestation_version": None,
        }
        authority_semantics = {
            "schema_version": semantics["semantic_schema_version"],
            "derived_from": None,
            "economic_event_id": semantics["economic_event_id"],
            "independence_attestation_id": semantics["independence_attestation_id"],
            "independence_attestation_version": semantics[
                "independence_attestation_version"
            ],
            "independence_status": semantics["independence_status"],
            "lineage_relation": semantics["lineage_relation"],
            "semantic_lineage_id": semantics["semantic_lineage_id"],
            "upstream_issuer_id": semantics["upstream_issuer_id"],
        }
        reference = self._reference(_semantic_independence=authority_semantics)
        canonical_record = self._canonical_projection(reference, semantics)
        self.assertNotIn("semantic_schema_version", canonical_record)
        self.assertEqual(
            canonical_record["semantic_independence_schema_version"],
            semantics["semantic_schema_version"],
        )
        for leaked_field in ("semantic_schema_version", "future_semantic_field"):
            with (
                self.subTest(leaked_field=leaked_field),
                self.assertRaises(psycopg.errors.InvalidParameterValue),
                self.authority.transaction(),
            ):
                self._authority_context(self.authority)
                self.authority.execute(
                    "SELECT authority_revision FROM evidence_authority."
                    "commit_investigator_evidence_projection(%s::jsonb,%s,%s)",
                    (
                        json.dumps({**canonical_record, leaked_field: 1}),
                        0,
                        "EVIDENCE_PROJECTED",
                    ),
                )
        with self.authority.transaction():
            self._authority_context(self.authority)
            revision = self.authority.execute(
                "SELECT authority_revision,authority_state_digest FROM "
                "evidence_authority.commit_investigator_evidence_projection("
                "%s::jsonb,%s,%s)",
                (json.dumps(canonical_record), 0, "EVIDENCE_PROJECTED"),
            ).fetchone()
        self.assertEqual(revision[0], 1)
        expected_revision_digest = sha256(
            ("0" * 64 + ":1:EVIDENCE_PROJECTED:").encode()
            + canonical_json_bytes(canonical_record)
        ).hexdigest()
        self.assertEqual(revision[1], expected_revision_digest)
        tampered_reference = {**reference, "artifact_digest": "f" * 64}
        with (
            self.assertRaises(psycopg.errors.InvalidParameterValue),
            self.authority.transaction(),
        ):
            self._authority_context(self.authority)
            self.authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(tampered_reference),
                    json.dumps(semantics),
                    self.initial_snapshot_id,
                    1,
                    uuid4(),
                    "phase25-canonical-substitution",
                ),
            )
        event_id = uuid4()
        with self.authority.transaction():
            self._authority_context(self.authority)
            accepted = self.authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(reference),
                    json.dumps(semantics),
                    self.initial_snapshot_id,
                    1,
                    event_id,
                    "phase25-semantic-accept",
                ),
            ).fetchone()[0]
            self.assertEqual(accepted, UUID(reference["reference_id"]))
            replay = self.authority.execute(
                "SELECT investigator.accept_evidence_reference_v2("
                "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                (
                    json.dumps(reference),
                    json.dumps(semantics),
                    self.initial_snapshot_id,
                    1,
                    event_id,
                    "phase25-semantic-accept",
                ),
            ).fetchone()[0]
            self.assertEqual(replay, accepted)
        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            current_snapshot, current_snapshot_digest = self.runtime.execute(
                "SELECT snapshot_id,canonical_digest FROM "
                "investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 2, "phase25-parent-tests"),
            ).fetchone()
            converged = self.runtime.execute(
                "SELECT snapshot_id,canonical_digest FROM "
                "investigator.create_snapshot_v2(%s,%s,%s,%s)",
                (self.tenant, self.case_id, 2, "phase25-parent-tests-second-key"),
            ).fetchone()
            self.assertEqual(converged, (current_snapshot, current_snapshot_digest))
            snapshot_semantics = self.runtime.execute(
                "SELECT canonical_snapshot_payload #>> "
                "'{applicable_versions,semantic_independence}', "
                "canonical_snapshot_payload #>> "
                "'{evidence,accepted_evidence_refs,0,semantic_independence,semantic_lineage_id}' "
                "FROM investigator.case_snapshot WHERE snapshot_id=%s",
                (current_snapshot,),
            ).fetchone()
            self.assertEqual(
                snapshot_semantics,
                ("investigator-evidence-semantics-1", "lineage-bank-event-1"),
            )

        barrier = threading.Barrier(2)

        def snapshot_once():
            connection = psycopg.connect(
                self._dsn(self.runtime_role, self.passwords[self.runtime_role])
            )
            try:
                with connection.transaction():
                    self._runtime_context(connection)
                    barrier.wait(timeout=5)
                    return connection.execute(
                        "SELECT snapshot_id,canonical_digest FROM "
                        "investigator.create_snapshot_v2(%s,%s,%s,%s)",
                        (
                            self.tenant,
                            self.case_id,
                            2,
                            "phase25-concurrent-snapshot-replay",
                        ),
                    ).fetchone()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_snapshots = tuple(
                executor.map(lambda _: snapshot_once(), range(2))
            )
        self.assertEqual(
            concurrent_snapshots,
            (
                (current_snapshot, current_snapshot_digest),
                (current_snapshot, current_snapshot_digest),
            ),
        )
        orphan_reference = self._reference()
        orphan_semantics = {
            **semantics,
            "semantic_lineage_id": "orphan-lineage",
            "lineage_relation": "DERIVED_COPY",
            "derived_from_evidence_namespace": "evidence_passport",
            "derived_from_evidence_id": "fictional-parent",
            "derived_from_evidence_version": "1",
        }
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference_v2("
                    "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(orphan_reference),
                        json.dumps(orphan_semantics),
                        current_snapshot,
                        2,
                        uuid4(),
                        "phase25-orphan-copy",
                    ),
                )
        correction_reference = self._reference(
            evidence_namespace=reference["evidence_namespace"],
            evidence_id=reference["evidence_id"],
            evidence_version="2",
        )
        correction_semantics = {
            **semantics,
            "lineage_relation": "CORRECTION",
            "derived_from_evidence_namespace": reference["evidence_namespace"],
            "derived_from_evidence_id": reference["evidence_id"],
            "derived_from_evidence_version": reference["evidence_version"],
        }
        with self.authority.transaction():
            self._authority_context(self.authority)
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference_v2("
                    "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(correction_reference),
                        json.dumps(correction_semantics),
                        current_snapshot,
                        2,
                        uuid4(),
                        "phase25-correction-without-parent",
                    ),
                )
        promoted_replay = {
            **semantics,
            "independence_status": "INDEPENDENT_VERIFIED",
            "independence_attestation_id": "independence-attestation-1",
            "independence_attestation_version": "1",
        }
        with self.authority.transaction():
            self._authority_context(self.authority)
            # The canonical digest covers semantic independence, so an exact
            # replay cannot be promoted even before immutable replay checks.
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                self.authority.execute(
                    "SELECT investigator.accept_evidence_reference_v2("
                    "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                    (
                        json.dumps(reference),
                        json.dumps(promoted_replay),
                        self.initial_snapshot_id,
                        1,
                        event_id,
                        "phase25-semantic-accept",
                    ),
                )
        unsafe_role = "phase25_unsafe_authority"
        self.admin.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(unsafe_role))
        )
        self.admin.execute(
            sql.SQL("GRANT {} TO olin_investigator_evidence_authority").format(
                sql.Identifier(unsafe_role)
            )
        )
        try:
            with self.authority.transaction():
                self._authority_context(self.authority)
                with self.assertRaises(AuthorityDenied):
                    assert_evidence_authority_database_custody(self.authority)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    self.authority.execute(
                        "SELECT investigator.accept_evidence_reference_v2("
                        "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                        (
                            json.dumps(reference),
                            json.dumps(semantics),
                            self.initial_snapshot_id,
                            1,
                            event_id,
                            "phase25-semantic-accept",
                        ),
                    )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    self.authority.execute(
                        "SELECT authority_revision FROM evidence_authority."
                        "commit_investigator_evidence_projection("
                        "%s::jsonb,%s,%s)",
                        (json.dumps(canonical_record), 1, "EVIDENCE_PROJECTED"),
                    )
        finally:
            self.admin.execute(
                sql.SQL("REVOKE {} FROM olin_investigator_evidence_authority").format(
                    sql.Identifier(unsafe_role)
                )
            )
        with self.authority.transaction():
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
                        "old-authority-path-denied",
                    ),
                )

        with self.runtime.transaction():
            self._runtime_context(self.runtime)
            assert_runtime_database_custody(self.runtime)
            row = self.runtime.execute(
                "SELECT semantic_lineage_id,independence_status "
                "FROM investigator.investigation_evidence_semantics "
                "WHERE reference_id=%s",
                (accepted,),
            ).fetchone()
            self.assertEqual(row, ("lineage-bank-event-1", "INDEPENDENCE_UNKNOWN"))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.runtime.execute(
                    "SET LOCAL ROLE olin_investigator_evidence_authority"
                )
        self.admin.execute(
            sql.SQL("GRANT {} TO olin_investigator_runtime").format(
                sql.Identifier(unsafe_role)
            )
        )
        try:
            with self.runtime.transaction():
                self._runtime_context(self.runtime)
                with self.assertRaises(AuthorityDenied):
                    assert_runtime_database_custody(self.runtime)
        finally:
            self.admin.execute(
                sql.SQL("REVOKE {} FROM olin_investigator_runtime").format(
                    sql.Identifier(unsafe_role)
                )
            )
        self.admin.execute(
            sql.SQL(
                "GRANT SELECT ON "
                "evidence_authority.investigator_evidence_projection_change TO {}"
            ).format(sql.Identifier(self.runtime_role))
        )
        try:
            with self.runtime.transaction():
                self._runtime_context(self.runtime)
                with self.assertRaises(AuthorityDenied):
                    assert_runtime_database_custody(self.runtime)
        finally:
            self.admin.execute(
                sql.SQL(
                    "REVOKE SELECT ON "
                    "evidence_authority.investigator_evidence_projection_change FROM {}"
                ).format(sql.Identifier(self.runtime_role))
            )

        controls = self.admin.execute(
            "SELECT relrowsecurity,relforcerowsecurity,"
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_evidence_semantics','SELECT'),"
            "has_table_privilege('olin_investigator_runtime',"
            "'investigator.investigation_evidence_semantics',"
            "'INSERT,UPDATE,DELETE,TRUNCATE'),"
            "has_table_privilege('olin_investigator_evidence_authority',"
            "'investigator.investigation_evidence_semantics',"
            "'INSERT,UPDATE,DELETE,TRUNCATE'),"
            "has_function_privilege('olin_investigator_runtime',"
            "'investigator.accept_evidence_reference_v2("
            "jsonb,jsonb,uuid,bigint,uuid,text)','EXECUTE'),"
            "pg_has_role(%s,'olin_investigator_evidence_authority','member'),"
            "pg_has_role(%s,'olin_investigator_runtime','member'),"
            "pg_has_role(%s,'olin_investigator_owner','member') "
            "FROM pg_class WHERE oid="
            "'investigator.investigation_evidence_semantics'::regclass",
            (self.runtime_role, self.authority_role, self.authority_role),
        ).fetchone()
        self.assertEqual(
            controls,
            (True, True, True, False, False, False, False, False, False),
        )

        self.assertNotIn(
            "investigator.",
            self.admin.execute(
                "SELECT pg_get_viewdef("
                "'evidence_authority.investigator_evidence_v1'::regclass,true)"
            ).fetchone()[0],
        )
        reader_group = "olin_investigator_evidence_reader"
        self.admin.execute(
            sql.SQL(
                "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS"
            ).format(sql.Identifier(reader_group))
        )
        with self.assertRaisesRegex(EvidenceBoundaryError, "custody"):
            PostgresCanonicalEvidenceReadPort(self.admin, tenant_id=self.tenant)
        reader_role = "olin_canonical_t_" + self.tenant.hex
        reader_password = secrets.token_urlsafe(24)
        self.admin.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} INHERIT NOSUPERUSER "
                "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(reader_role), sql.Literal(reader_password))
        )
        self.admin.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(reader_group), sql.Identifier(reader_role)
            )
        )
        self.admin.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                sql.Identifier(reader_role)
            )
        )
        self.admin.execute(
            sql.SQL("GRANT USAGE ON SCHEMA evidence_authority TO {}").format(
                sql.Identifier(reader_group)
            )
        )
        self.admin.execute(
            sql.SQL(
                "GRANT SELECT ON evidence_authority.investigator_evidence_v1 TO {}"
            ).format(sql.Identifier(reader_group))
        )
        projection_privileges = self.admin.execute(
            "SELECT "
            "has_table_privilege('olin_investigator_runtime',"
            "'evidence_authority.investigator_evidence_projection_change',"
            "'INSERT,UPDATE,DELETE,TRUNCATE'),"
            "has_table_privilege('olin_investigator_evidence_authority',"
            "'evidence_authority.investigator_evidence_projection_change',"
            "'INSERT,UPDATE,DELETE,TRUNCATE'),"
            "EXISTS (SELECT 1 FROM information_schema.table_privileges "
            "WHERE table_schema='evidence_authority' "
            "AND table_name='investigator_evidence_projection_change' "
            "AND grantee='PUBLIC' AND privilege_type IN "
            "('INSERT','UPDATE','DELETE','TRUNCATE')),"
            "has_function_privilege('olin_investigator_runtime',"
            "'evidence_authority.commit_investigator_evidence_projection("
            "jsonb,bigint,text)','EXECUTE'),"
            "has_function_privilege('olin_investigator_evidence_authority',"
            "'evidence_authority.commit_investigator_evidence_projection("
            "jsonb,bigint,text)','EXECUTE')"
        ).fetchone()
        self.assertEqual(projection_privileges, (False, False, False, False, True))
        reader = psycopg.connect(self._dsn(reader_role, reader_password))
        try:
            port = PostgresCanonicalEvidenceReadPort(reader, tenant_id=self.tenant)
            resolved = port.resolve(
                tenant_id=self.tenant,
                case_id=self.case_id,
                evidence_namespace=reference["evidence_namespace"],
                evidence_id=reference["evidence_id"],
                purpose=reference["consent_purpose"],
                as_of=datetime.now(timezone.utc),
            )
            self.assertEqual(resolved.semantic_lineage_id, "lineage-bank-event-1")
            self.assertEqual(resolved.evidence_id, reference["evidence_id"])
            with self.runtime.transaction():
                self._runtime_context(self.runtime)
                runtime_custody = establish_runtime_database_custody(self.runtime)
            gate = PostgresReasoningSnapshotGate(
                runtime_connection=self.runtime,
                evidence_authority=port,
                runtime_custody=runtime_custody,
            )
            with self.runtime.transaction():
                self.runtime.execute(
                    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
                )
                self._runtime_context(self.runtime)
                escaped_after_commit = gate.require_snapshot_current_for_reasoning(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    snapshot_id=current_snapshot,
                    as_of=datetime.now(timezone.utc),
                )
            with self.assertRaisesRegex(EvidenceBoundaryError, "escaped"):
                escaped_after_commit.consume(lambda ready: ready.snapshot_id)
            with self.runtime.transaction():
                self.runtime.execute(
                    "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY"
                )
                self._runtime_context(self.runtime)
                with self.assertRaisesRegex(EvidenceBoundaryError, "does not match"):
                    escaped_after_commit.consume(lambda ready: ready.snapshot_id)

            timed_out = []

            def exceed_statement_timeout(ready):
                timed_out.append(ready)
                self.runtime.execute("SELECT pg_sleep(6)")

            with self.assertRaises(psycopg.errors.QueryCanceled):
                gate.consume_snapshot_current_for_reasoning(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    snapshot_id=current_snapshot,
                    as_of=datetime.now(timezone.utc),
                    consumer=exceed_statement_timeout,
                )
            with self.assertRaisesRegex(EvidenceBoundaryError, "already consumed"):
                timed_out[0].consume(lambda ready: ready.snapshot_id)

            withdrawn_record = {**canonical_record, "consent_status": "WITHDRAWN"}
            writer_started = threading.Event()
            escaped = []

            def withdraw_concurrently():
                writer = psycopg.connect(
                    self._dsn(self.authority_role, self.passwords[self.authority_role])
                )
                try:
                    with writer.transaction():
                        self._authority_context(writer)
                        writer_started.set()
                        return writer.execute(
                            "SELECT authority_revision FROM "
                            "evidence_authority."
                            "commit_investigator_evidence_projection("
                            "%s::jsonb,%s,%s)",
                            (json.dumps(withdrawn_record), 1, "CONSENT_CHANGED"),
                        ).fetchone()[0]
                finally:
                    writer.close()

            with ThreadPoolExecutor(max_workers=1) as pool:
                writer_future = None

                def consume(ready):
                    nonlocal writer_future
                    escaped.append(ready)
                    writer_future = pool.submit(withdraw_concurrently)
                    self.assertTrue(writer_started.wait(timeout=2))
                    self.assertFalse(writer_future.done())
                    return ready.authority_revision

                observed_revision = gate.consume_snapshot_current_for_reasoning(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    snapshot_id=current_snapshot,
                    as_of=datetime.now(timezone.utc),
                    consumer=consume,
                )
                self.assertEqual(observed_revision, 1)
                self.assertEqual(writer_future.result(timeout=5), 2)
            with self.assertRaisesRegex(EvidenceBoundaryError, "already consumed"):
                escaped[0].consume(lambda ready: ready.snapshot_id)
            with self.assertRaisesRegex(EvidenceBoundaryError, "revision is stale"):
                gate.consume_snapshot_current_for_reasoning(
                    tenant_id=self.tenant,
                    case_id=self.case_id,
                    snapshot_id=current_snapshot,
                    as_of=datetime.now(timezone.utc),
                    consumer=lambda ready: ready.snapshot_id,
                )

            def prepare_ready_case(label):
                case_id = uuid4()
                with self.runtime.transaction():
                    self._runtime_context(self.runtime)
                    self.runtime.execute(
                        "SELECT investigator.create_case("
                        "%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                        (
                            case_id,
                            self.tenant,
                            None,
                            f"phase25-fence-{label}",
                            uuid4(),
                            datetime.now(timezone.utc),
                            "{}",
                            1,
                            f"phase25-fence-case-{label}",
                            sha256(b"{}").hexdigest(),
                            "{}",
                        ),
                    )
                    initial = self.runtime.execute(
                        "SELECT snapshot_id FROM investigator.create_snapshot("
                        "%s,%s,%s,%s)",
                        (self.tenant, case_id, 1, f"phase25-fence-initial-{label}"),
                    ).fetchone()[0]
                case_semantics = {
                    **semantics,
                    "semantic_lineage_id": f"lineage-{label}",
                    "upstream_issuer_id": f"issuer-{label}",
                }
                case_authority_semantics = {
                    **authority_semantics,
                    "semantic_lineage_id": f"lineage-{label}",
                    "upstream_issuer_id": f"issuer-{label}",
                }
                case_reference = self._reference(
                    case_id=str(case_id),
                    evidence_id=f"artifact-{label}",
                    source_attestation_id=f"attestation-{label}",
                    issuer_id=f"issuer-{label}",
                    _semantic_independence=case_authority_semantics,
                )
                case_record = self._canonical_projection(case_reference, case_semantics)
                with self.authority.transaction():
                    self._authority_context(self.authority)
                    self.authority.execute(
                        "SELECT authority_revision FROM evidence_authority."
                        "commit_investigator_evidence_projection("
                        "%s::jsonb,%s,%s)",
                        (json.dumps(case_record), 0, "EVIDENCE_PROJECTED"),
                    )
                    self.authority.execute(
                        "SELECT investigator.accept_evidence_reference_v2("
                        "%s::jsonb,%s::jsonb,%s,%s,%s,%s)",
                        (
                            json.dumps(case_reference),
                            json.dumps(case_semantics),
                            initial,
                            1,
                            uuid4(),
                            f"phase25-fence-accept-{label}",
                        ),
                    )
                with self.runtime.transaction():
                    self._runtime_context(self.runtime)
                    snapshot = self.runtime.execute(
                        "SELECT snapshot_id FROM investigator.create_snapshot_v2("
                        "%s,%s,%s,%s)",
                        (self.tenant, case_id, 2, f"phase25-fence-ready-{label}"),
                    ).fetchone()[0]
                return case_id, snapshot, case_record

            def assert_fenced_change(label, change_kind, changes):
                case_id, snapshot, base_record = prepare_ready_case(label)
                changed_record = {**base_record, **changes}
                writer_started = threading.Event()

                def mutate():
                    writer = psycopg.connect(
                        self._dsn(
                            self.authority_role, self.passwords[self.authority_role]
                        )
                    )
                    try:
                        with writer.transaction():
                            self._authority_context(writer)
                            writer_started.set()
                            return writer.execute(
                                "SELECT authority_revision FROM evidence_authority."
                                "commit_investigator_evidence_projection("
                                "%s::jsonb,%s,%s)",
                                (json.dumps(changed_record), 1, change_kind),
                            ).fetchone()[0]
                    finally:
                        writer.close()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    writer_future = None

                    def consume(ready):
                        nonlocal writer_future
                        writer_future = pool.submit(mutate)
                        self.assertTrue(writer_started.wait(timeout=2))
                        self.assertFalse(writer_future.done())
                        return ready.authority_revision

                    case_gate = PostgresReasoningSnapshotGate(
                        runtime_connection=self.runtime,
                        evidence_authority=port,
                        runtime_custody=runtime_custody,
                    )
                    self.assertEqual(
                        case_gate.consume_snapshot_current_for_reasoning(
                            tenant_id=self.tenant,
                            case_id=case_id,
                            snapshot_id=snapshot,
                            as_of=datetime.now(timezone.utc),
                            consumer=consume,
                        ),
                        1,
                    )
                    self.assertEqual(writer_future.result(timeout=5), 2)

            assert_fenced_change(
                "evidence-revocation",
                "EVIDENCE_REVOKED",
                {
                    "lifecycle": "REVOKED",
                    "usability": "UNUSABLE",
                    "unusable_reason": "EVIDENCE_REVOKED",
                },
            )
            assert_fenced_change(
                "source-change",
                "SOURCE_ATTESTATION_CHANGED",
                {"source_attestation_version": "2"},
            )
            dual_case, dual_snapshot, _ = prepare_ready_case("dual-readiness")

            def issue_readiness():
                runtime = psycopg.connect(
                    self._dsn(self.runtime_role, self.passwords[self.runtime_role])
                )
                canonical = psycopg.connect(self._dsn(reader_role, reader_password))
                try:
                    with runtime.transaction():
                        self._runtime_context(runtime)
                        custody = establish_runtime_database_custody(runtime)
                    dual_gate = PostgresReasoningSnapshotGate(
                        runtime_connection=runtime,
                        evidence_authority=PostgresCanonicalEvidenceReadPort(
                            canonical, tenant_id=self.tenant
                        ),
                        runtime_custody=custody,
                    )
                    return dual_gate.consume_snapshot_current_for_reasoning(
                        tenant_id=self.tenant,
                        case_id=dual_case,
                        snapshot_id=dual_snapshot,
                        as_of=datetime.now(timezone.utc),
                        consumer=lambda ready: (
                            ready.authority_revision,
                            ready.authority_state_digest,
                        ),
                    )
                finally:
                    canonical.close()
                    runtime.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                converged = list(pool.map(lambda _: issue_readiness(), range(2)))
            self.assertEqual(converged[0], converged[1])
            self.admin.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(unsafe_role), sql.Identifier(reader_group)
                )
            )
            try:
                with self.assertRaisesRegex(EvidenceBoundaryError, "custody"):
                    port.revalidate(
                        self._python_reference(reference),
                        as_of=datetime.now(timezone.utc),
                    )
            finally:
                self.admin.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(unsafe_role), sql.Identifier(reader_group)
                    )
                )
            withdrawn = port.revalidate(
                self._python_reference(reference), as_of=datetime.now(timezone.utc)
            )
            self.assertEqual(
                withdrawn.current_usability(as_of=datetime.now(timezone.utc))[1].value,
                "CONSENT_WITHDRAWN",
            )
            rollback_record = {
                **withdrawn_record,
                "lifecycle": "REVOKED",
                "usability": "UNUSABLE",
                "unusable_reason": "EVIDENCE_REVOKED",
            }
            rollback_writer = psycopg.connect(
                self._dsn(self.authority_role, self.passwords[self.authority_role])
            )
            try:
                with (
                    self.assertRaisesRegex(RuntimeError, "force rollback"),
                    rollback_writer.transaction(),
                ):
                    self._authority_context(rollback_writer)
                    rollback_writer.execute(
                        "SELECT authority_revision FROM evidence_authority."
                        "commit_investigator_evidence_projection("
                        "%s::jsonb,%s,%s)",
                        (json.dumps(rollback_record), 2, "EVIDENCE_REVOKED"),
                    )
                    raise RuntimeError("force rollback")
            finally:
                rollback_writer.close()
            latest_revision = self.admin.execute(
                "SELECT max(authority_revision) FROM evidence_authority."
                "investigator_evidence_projection_change "
                "WHERE tenant_id=%s AND case_id=%s",
                (self.tenant, self.case_id),
            ).fetchone()[0]
            self.assertEqual(latest_revision, 2)
            with self.authority.transaction():
                self._authority_context(self.authority)
                committed_revision = self.authority.execute(
                    "SELECT authority_revision FROM evidence_authority."
                    "commit_investigator_evidence_projection("
                    "%s::jsonb,%s,%s)",
                    (json.dumps(rollback_record), 2, "EVIDENCE_REVOKED"),
                ).fetchone()[0]
            self.assertEqual(committed_revision, 3)
        finally:
            reader.close()
            self.admin.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(reader_group), sql.Identifier(reader_role)
                )
            )
            self.admin.execute(
                sql.SQL(
                    "REVOKE SELECT ON "
                    "evidence_authority.investigator_evidence_v1 FROM {}"
                ).format(sql.Identifier(reader_group))
            )
            self.admin.execute(
                sql.SQL("REVOKE USAGE ON SCHEMA evidence_authority FROM {}").format(
                    sql.Identifier(reader_group)
                )
            )
            self.admin.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(reader_role))
            )
            self.admin.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(reader_group))
            )
            self.admin.execute(
                sql.SQL("DROP ROLE {}").format(sql.Identifier(unsafe_role))
            )


if __name__ == "__main__":
    unittest.main()
