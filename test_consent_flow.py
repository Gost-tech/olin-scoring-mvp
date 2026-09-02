from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from olin.consent_flow import (
    SyntheticOtpDispatcher,
    get_public_challenge,
    get_receipt,
    issue_challenge,
    register_intake_binding,
    register_policy,
    verify_challenge,
    withdraw_consent,
)
from olin.intakes import create_intake, create_link_session
from olin.operations import control_room
from olin.store import ScoringLog
from scripts.bank_acceptance_test import _request
from test_shadow_mvp import request, running_server


# Keep the fixture anchored to the test run. Public HTTP verification uses the
# service clock, so a fixed wall-clock value eventually makes a valid challenge
# appear expired even though the consent behavior has not changed.
NOW = datetime.now(timezone.utc).replace(microsecond=0)
PERSON = sha256(b"consent-person-001").hexdigest()
BUSINESS = sha256(b"consent-business-001").hexdigest()
TRUST_REGISTRY = json.dumps({
    "bank_kyc": {
        "status": "active",
        "evidence_types": [
            "government_identity_verified",
            "individual_business_ownership_verified",
            "legal_representative_authority_verified",
        ],
        "valid_until": "2099-12-31",
        "attestation_id": "bank-kyc-uat-control",
    }
})


def policy_values(purpose: str, provider: str = "", version: str = "uat-v1") -> dict:
    labels = {
        "credit_assessment": "evaluación controlada del expediente",
        "provider_access": f"acceso separado al proveedor {provider}",
        "credit_bureau": "autorización separada de buró para prueba sintética",
    }
    return {
        "policy_id": f"{purpose}-{provider or 'general'}-{version}",
        "purpose": purpose,
        "provider": provider,
        "policy_version": version,
        "notice_version": "privacy-uat-v1",
        "language": "es-MX",
        "text": (
            f"Texto exclusivamente sintético para UAT de {labels[purpose]}. "
            "No constituye autorización legal para consultar datos reales."
        ),
        "privacy_notice_url": "https://example.invalid/privacy-uat",
        "retention_summary": "Conservación sintética durante la prueba UAT y eliminación posterior.",
        "status": "synthetic_uat",
    }


class FailingDispatcher:
    expose_test_code = False

    def send(self, **_kwargs):
        raise RuntimeError("simulated OTP provider outage")


class ConsentFixture:
    def __init__(self, owner="bank_a"):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.directory.name) / "consent.db")
        self.owner = owner
        with ScoringLog(self.db_path):
            pass
        self.intake_id = create_intake(self.db_path, {
            "partner_case_reference": "CONSENT-UAT-001",
            "cohort_id": "consent_uat",
            "merchant_name": "Comercio Consentimiento Sintético",
        }, owner)["intake_id"]
        identity = register_intake_binding(
            self.db_path, intake_id=self.intake_id, owner_actor=owner,
            evidence_type="government_identity_verified", source_id="bank_kyc",
            source_reference="kyc-session-001:identity", subject_hash=PERSON,
            observed_at=(NOW - timedelta(days=1)).isoformat(),
            expires_at=(NOW + timedelta(days=30)).isoformat(),
            created_by="bank_kyc_adapter", now=NOW,
        )
        authority = register_intake_binding(
            self.db_path, intake_id=self.intake_id, owner_actor=owner,
            evidence_type="individual_business_ownership_verified", source_id="bank_kyc",
            source_reference="kyc-session-001:authority", subject_hash=BUSINESS,
            observed_at=(NOW - timedelta(days=1)).isoformat(),
            expires_at=(NOW + timedelta(days=30)).isoformat(),
            created_by="bank_kyc_adapter", now=NOW,
        )
        self.identity_binding_id = identity["binding_id"]
        self.authority_binding_id = authority["binding_id"]

    def close(self):
        self.directory.cleanup()

    def policy(self, purpose, provider="", version="uat-v1"):
        values = policy_values(purpose, provider, version)
        return register_policy(
            self.db_path, owner_actor=self.owner, created_by="uat_admin", **values,
        )["policy_id"]

    def accept(self, policy_id, at=NOW):
        challenge = issue_challenge(
            self.db_path, intake_id=self.intake_id, owner_actor=self.owner,
            policy_id=policy_id, channel="sms", destination="+525500000000",
            identity_binding_id=self.identity_binding_id,
            authority_binding_id=self.authority_binding_id,
            dispatcher=SyntheticOtpDispatcher(), now=at,
        )
        consent = verify_challenge(
            self.db_path, intake_id=self.intake_id,
            challenge_id=challenge["challenge_id"], otp=challenge["test_otp"],
            owner_actor=self.owner, now=at + timedelta(seconds=10),
        )
        return challenge, consent


class ConsentFlowTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "OLIN_MODE": "demo",
            "OLIN_CONSENT_OTP_SECRET": "consent-test-secret-with-32-characters",
            "OLIN_TRUSTED_SOURCE_REGISTRY": TRUST_REGISTRY,
            "OLIN_RATE_LIMIT_PER_MINUTE": "500",
        }, clear=True)
        self.env.start()
        self.fx = ConsentFixture()

    def tearDown(self):
        self.fx.close()
        self.env.stop()

    def test_three_purposes_create_three_receipts_and_provider_link_uses_its_consent(self):
        policies = [
            self.fx.policy("credit_assessment"),
            self.fx.policy("provider_access", "partner-bank-sandbox"),
            self.fx.policy("credit_bureau", "circulo_credito"),
        ]
        consents = [self.fx.accept(policy)[1] for policy in policies]
        self.assertEqual(len({item["consent_id"] for item in consents}), 3)
        self.assertEqual(
            {item["purpose"] for item in consents},
            {"credit_assessment", "provider_access", "credit_bureau"},
        )
        for consent in consents:
            receipt = get_receipt(
                self.fx.db_path, intake_id=self.fx.intake_id,
                consent_id=consent["consent_id"], owner_actor=self.fx.owner,
            )
            self.assertEqual(receipt["receipt_sha256"], consent["receipt_sha256"])
            self.assertEqual(receipt["current_status"], "active")
            self.assertNotIn("otp", json.dumps(receipt).lower())
        session = create_link_session(
            self.fx.db_path, self.fx.intake_id,
            "partner-bank-sandbox", self.fx.owner,
        )
        with ScoringLog(self.fx.db_path) as log:
            linked_consent = log.conn.execute(
                "SELECT consent_id FROM intake_link_session WHERE link_session_id=?",
                (session["link_session_id"],),
            ).fetchone()[0]
        provider_consent = next(c for c in consents if c["purpose"] == "provider_access")
        self.assertEqual(linked_consent, provider_consent["consent_id"])

    def test_http_challenge_verify_and_receipt_contract(self):
        policy_id = self.fx.policy("credit_assessment")
        # Demo auth resolves to analista_demo, so create a matching fixture for black-box API.
        second = ConsentFixture(owner="analista_demo")
        try:
            policy_id = second.policy("credit_assessment")
            with running_server(second.db_path) as base:
                status, policies = _request(base, "/api/v1/consent-policies")
                self.assertEqual(status, 200)
                self.assertEqual(len(policies["data"]), 1)
                status, challenge = _request(
                    base, f"/api/v1/intakes/{second.intake_id}/consent-challenges", "POST", {
                        "policy_id": policy_id,
                        "channel": "sms",
                        "destination": "+525500000000",
                        "identity_binding_id": second.identity_binding_id,
                        "authority_binding_id": second.authority_binding_id,
                    },
                )
                self.assertEqual(status, 201, challenge)
                data = challenge["data"]
                status, verified = _request(
                    base,
                    f"/api/v1/intakes/{second.intake_id}/consent-challenges/{data['challenge_id']}/verify",
                    "POST", {"otp": data["test_otp"]},
                )
                self.assertEqual(status, 201, verified)
                consent = verified["data"]
                status, receipt = _request(
                    base,
                    f"/api/v1/intakes/{second.intake_id}/consents/{consent['consent_id']}/receipt",
                )
                self.assertEqual(status, 200, receipt)
                self.assertEqual(receipt["data"]["receipt_sha256"], consent["receipt_sha256"])
        finally:
            second.close()

    def test_applicant_link_is_public_token_bound_and_never_needs_partner_credentials(self):
        policy_id = self.fx.policy("credit_assessment")
        challenge = issue_challenge(
            self.fx.db_path, intake_id=self.fx.intake_id, owner_actor=self.fx.owner,
            policy_id=policy_id, channel="sms", destination="+525500000000",
            identity_binding_id=self.fx.identity_binding_id,
            authority_binding_id=self.fx.authority_binding_id,
            dispatcher=SyntheticOtpDispatcher(), now=NOW,
        )
        fragment = parse_qs(urlparse(challenge["consent_path"]).fragment)
        access_token = fragment["token"][0]
        self.assertEqual(fragment["challenge"][0], challenge["challenge_id"])
        with ScoringLog(self.fx.db_path) as log:
            stored = log.conn.execute(
                "SELECT public_token_sha256 FROM consent_challenge WHERE challenge_id=?",
                (challenge["challenge_id"],),
            ).fetchone()[0]
        self.assertNotEqual(stored, access_token)
        self.assertNotIn(access_token, stored)
        with self.assertRaisesRegex(PermissionError, "invalid"):
            get_public_challenge(
                self.fx.db_path, challenge_id=challenge["challenge_id"],
                access_token="wrong-token-that-is-long-enough-to-test-000",
            )
        with running_server(self.fx.db_path) as base:
            page_status, page_body, _headers = request(base, "/consentir")
            view_status, view_body = _request(
                base,
                f"/api/v1/public/consent-challenges/{challenge['challenge_id']}/view",
                "POST", {"access_token": access_token},
            )
            unchecked_status, _unchecked_body = _request(
                base,
                f"/api/v1/public/consent-challenges/{challenge['challenge_id']}/verify",
                "POST", {"access_token": access_token, "otp": challenge["test_otp"],
                         "accepted": False},
            )
            verify_status, verify_body = _request(
                base,
                f"/api/v1/public/consent-challenges/{challenge['challenge_id']}/verify",
                "POST", {"access_token": access_token, "otp": challenge["test_otp"],
                         "accepted": True},
            )
        self.assertEqual(page_status, 200)
        page_text = page_body.decode("utf-8")
        self.assertIn("Autorizar esta finalidad", page_text)
        self.assertNotIn("partner-token", page_text)
        self.assertEqual(view_status, 200, view_body)
        self.assertEqual(unchecked_status, 403)
        view = view_body["data"]
        self.assertEqual(view["text_sha256"], sha256(view["text"].encode()).hexdigest())
        self.assertEqual(verify_status, 201, verify_body)
        self.assertEqual(verify_body["data"]["purpose"], "credit_assessment")
        receipt = get_receipt(
            self.fx.db_path, intake_id=self.fx.intake_id,
            consent_id=verify_body["data"]["consent_id"], owner_actor=self.fx.owner,
        )
        self.assertEqual(
            receipt["verification_method"], "active_checkbox_and_one_time_code"
        )

    def test_wrong_code_locks_after_five_attempts_and_code_cannot_be_reused(self):
        policy_id = self.fx.policy("credit_assessment")
        challenge = issue_challenge(
            self.fx.db_path, intake_id=self.fx.intake_id, owner_actor=self.fx.owner,
            policy_id=policy_id, channel="email", destination="uat@example.invalid",
            identity_binding_id=self.fx.identity_binding_id,
            authority_binding_id=self.fx.authority_binding_id,
            dispatcher=SyntheticOtpDispatcher(), now=NOW,
        )
        wrong_otp = "000000" if challenge["test_otp"] != "000000" else "000001"
        for _ in range(5):
            with self.assertRaisesRegex(PermissionError, "verification failed"):
                verify_challenge(
                    self.fx.db_path, intake_id=self.fx.intake_id,
                    challenge_id=challenge["challenge_id"], otp=wrong_otp,
                    owner_actor=self.fx.owner, now=NOW + timedelta(seconds=20),
                )
        with self.assertRaisesRegex(PermissionError, "not active"):
            verify_challenge(
                self.fx.db_path, intake_id=self.fx.intake_id,
                challenge_id=challenge["challenge_id"], otp=challenge["test_otp"],
                owner_actor=self.fx.owner, now=NOW + timedelta(seconds=30),
            )

        challenge, _consent = self.fx.accept(policy_id)
        with self.assertRaisesRegex(PermissionError, "not active"):
            verify_challenge(
                self.fx.db_path, intake_id=self.fx.intake_id,
                challenge_id=challenge["challenge_id"], otp=challenge["test_otp"],
                owner_actor=self.fx.owner, now=NOW + timedelta(seconds=30),
            )

    def test_expired_challenge_is_rejected(self):
        policy_id = self.fx.policy("credit_assessment")
        challenge = issue_challenge(
            self.fx.db_path, intake_id=self.fx.intake_id, owner_actor=self.fx.owner,
            policy_id=policy_id, channel="sms", destination="+525500000000",
            identity_binding_id=self.fx.identity_binding_id,
            authority_binding_id=self.fx.authority_binding_id,
            dispatcher=SyntheticOtpDispatcher(), ttl_minutes=2, now=NOW,
        )
        with self.assertRaisesRegex(PermissionError, "expired"):
            verify_challenge(
                self.fx.db_path, intake_id=self.fx.intake_id,
                challenge_id=challenge["challenge_id"], otp=challenge["test_otp"],
                owner_actor=self.fx.owner, now=NOW + timedelta(minutes=3),
            )

    def test_provider_failure_creates_no_consent_and_marks_challenge_failed(self):
        policy_id = self.fx.policy("credit_assessment")
        with self.assertRaisesRegex(RuntimeError, "provider outage"):
            issue_challenge(
                self.fx.db_path, intake_id=self.fx.intake_id, owner_actor=self.fx.owner,
                policy_id=policy_id, channel="sms", destination="+525500000000",
                identity_binding_id=self.fx.identity_binding_id,
                authority_binding_id=self.fx.authority_binding_id,
                dispatcher=FailingDispatcher(), now=NOW,
            )
        with ScoringLog(self.fx.db_path) as log:
            status = log.conn.execute(
                "SELECT status FROM consent_challenge ORDER BY issued_at DESC LIMIT 1"
            ).fetchone()[0]
            count = log.conn.execute("SELECT COUNT(*) FROM intake_consent").fetchone()[0]
        self.assertEqual(status, "dispatch_failed")
        self.assertEqual(count, 0)

    def test_new_policy_version_supersedes_only_same_purpose(self):
        assessment_v1 = self.fx.policy("credit_assessment", version="uat-v1")
        provider = self.fx.policy("provider_access", "partner-bank-sandbox")
        _challenge, first = self.fx.accept(assessment_v1)
        _challenge, provider_consent = self.fx.accept(provider)
        assessment_v2 = self.fx.policy("credit_assessment", version="uat-v2")
        _challenge, second = self.fx.accept(assessment_v2)
        with ScoringLog(self.fx.db_path) as log:
            rows = log.conn.execute(
                "SELECT consent_id,status FROM intake_consent WHERE intake_id=?",
                (self.fx.intake_id,),
            ).fetchall()
        statuses = dict(rows)
        self.assertEqual(statuses[first["consent_id"]], "superseded")
        self.assertEqual(statuses[second["consent_id"]], "active")
        self.assertEqual(statuses[provider_consent["consent_id"]], "active")

    def test_assessment_withdrawal_cascades_and_opens_operations_task(self):
        assessment = self.fx.accept(self.fx.policy("credit_assessment"))[1]
        provider = self.fx.accept(
            self.fx.policy("provider_access", "partner-bank-sandbox")
        )[1]
        self.fx.accept(self.fx.policy("credit_bureau", "circulo_credito"))
        session = create_link_session(
            self.fx.db_path, self.fx.intake_id,
            "partner-bank-sandbox", self.fx.owner,
        )
        result = withdraw_consent(
            self.fx.db_path, intake_id=self.fx.intake_id,
            consent_id=assessment["consent_id"], reason="Titular retiró autorización",
            owner_actor=self.fx.owner,
        )
        self.assertEqual(result["intake_status"], "created")
        receipt = get_receipt(
            self.fx.db_path, intake_id=self.fx.intake_id,
            consent_id=provider["consent_id"], owner_actor=self.fx.owner,
        )
        self.assertEqual(receipt["current_status"], "withdrawn")
        with ScoringLog(self.fx.db_path) as log:
            link_status = log.conn.execute(
                "SELECT status FROM intake_link_session WHERE link_session_id=?",
                (session["link_session_id"],),
            ).fetchone()[0]
            task = log.conn.execute(
                "SELECT status FROM consent_withdrawal_task WHERE task_id=?",
                (result["withdrawal_task_id"],),
            ).fetchone()[0]
        self.assertEqual(link_status, "cancelled")
        self.assertEqual(task, "open")
        queue = control_room(self.fx.db_path, now=NOW)
        withdrawal_items = [
            item for item in queue["items"]
            if item["kind"] == "consent_withdrawal"
        ]
        self.assertEqual(len(withdrawal_items), 1)
        self.assertEqual(withdrawal_items[0]["severity"], "critical")

    def test_cross_tenant_receipt_is_not_disclosed(self):
        consent = self.fx.accept(self.fx.policy("credit_assessment"))[1]
        users = json.dumps({
            "bank_a": {"token": "a" * 32, "role": "partner"},
            "bank_b": {"token": "b" * 32, "role": "partner"},
        })
        with patch.dict(os.environ, {"OLIN_MODE": "production", "OLIN_USERS": users}):
            with running_server(self.fx.db_path) as base:
                status, _ = _request(
                    base,
                    f"/api/v1/intakes/{self.fx.intake_id}/consents/{consent['consent_id']}/receipt",
                    token="b" * 32,
                )
        self.assertEqual(status, 404)

    def test_real_mode_blocks_direct_consent_and_unapproved_synthetic_policy(self):
        users = json.dumps({"bank_a": {"token": "a" * 32, "role": "partner"}})
        with patch.dict(os.environ, {"OLIN_MODE": "production", "OLIN_USERS": users}):
            with running_server(self.fx.db_path) as base:
                status, body = _request(
                    base, f"/api/v1/intakes/{self.fx.intake_id}/consents", "POST", {
                        "channel": "sms", "policy_version": "fake-v1",
                        "text": "Acepto todo lo presentado por el solicitante.",
                    }, token="a" * 32,
                )
            self.assertEqual(status, 403, body)
            with running_server(self.fx.db_path) as base:
                application_status, application_body = _request(
                    base, "/api/applications", "POST", {"consent": {
                        "channel": "sms",
                        "text": "Texto que no proviene de un recibo verificado.",
                    }}, token="a" * 32,
                )
            self.assertEqual(application_status, 403, application_body)
            with self.assertRaisesRegex(PermissionError, "Synthetic consent policies"):
                register_policy(
                    self.fx.db_path, owner_actor=self.fx.owner, created_by="bad_admin",
                    **policy_values("provider_access", "new-provider"),
                )

    def test_approved_policy_requires_all_approval_references_and_no_placeholders(self):
        values = policy_values("credit_assessment")
        values["status"] = "approved"
        with self.assertRaisesRegex(ValueError, "approval references"):
            register_policy(
                self.fx.db_path, owner_actor=self.fx.owner,
                created_by="admin", **values,
            )
        values["text"] = "[INSTITUCIÓN] autoriza este texto placeholder para datos reales."
        with self.assertRaisesRegex(ValueError, "draft placeholders"):
            register_policy(
                self.fx.db_path, owner_actor=self.fx.owner, created_by="admin",
                legal_approval_ref="LEGAL-1", privacy_approval_ref="PRIVACY-1",
                partner_approval_ref="BANK-1", **values,
            )

    def test_policy_snapshot_is_immutable(self):
        values = policy_values("credit_assessment")
        register_policy(
            self.fx.db_path, owner_actor=self.fx.owner, created_by="admin", **values,
        )
        values["text"] = values["text"] + " Alterado."
        with self.assertRaisesRegex(ValueError, "immutable"):
            register_policy(
                self.fx.db_path, owner_actor=self.fx.owner, created_by="admin", **values,
            )


if __name__ == "__main__":
    unittest.main()
