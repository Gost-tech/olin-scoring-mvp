from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from legal_review_system_import import workflow


class LegalReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contract = self.root / "draft.md"
        self.contract.write_text("DRAFT - DO NOT SIGN\n", encoding="utf-8")
        self.outbox = self.root / "outbox"
        self.outbox_patch = patch.object(workflow, "OUTBOX", self.outbox)
        self.outbox_patch.start()

    def tearDown(self):
        self.outbox_patch.stop()
        self.temp.cleanup()

    def prepare(self):
        workflow.prepare(argparse.Namespace(
            contract=str(self.contract), matter="OLIN-TEST-001",
            recipient_name="Counsel", recipient_email="counsel@example.mx",
            from_email="founder@example.com",
        ))

    def test_prepare_creates_preview_without_approval(self):
        self.prepare()
        target = self.outbox / "OLIN-TEST-001"
        self.assertTrue((target / "review-request.eml").is_file())
        self.assertFalse((target / "approval.json").exists())
        manifest = json.loads((target / "manifest.json").read_text())
        self.assertEqual("PREPARED_NOT_APPROVED", manifest["status"])

    def test_docx_attachment_uses_word_mime_type(self):
        self.contract = self.root / "draft.docx"
        self.contract.write_bytes(b"PK\x03\x04example")
        self.prepare()
        eml = (self.outbox / "OLIN-TEST-001" / "review-request.eml").read_text()
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            eml,
        )

    def test_send_is_blocked_without_approval(self):
        self.prepare()
        with self.assertRaises(workflow.WorkflowError):
            workflow.send(argparse.Namespace(matter="OLIN-TEST-001", confirm_send="SEND"))

    def test_contract_change_invalidates_approval(self):
        self.prepare()
        workflow.approve(argparse.Namespace(matter="OLIN-TEST-001", approved_by="Brice"))
        attachment = self.outbox / "OLIN-TEST-001" / "draft.md"
        attachment.write_text("CHANGED\n", encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "approval does not match"):
            workflow.send(argparse.Namespace(matter="OLIN-TEST-001", confirm_send="SEND"))

    def test_send_requires_literal_confirmation(self):
        self.prepare()
        workflow.approve(argparse.Namespace(matter="OLIN-TEST-001", approved_by="Brice"))
        with self.assertRaisesRegex(workflow.WorkflowError, "confirm-send"):
            workflow.send(argparse.Namespace(matter="OLIN-TEST-001", confirm_send="yes"))

    def test_reprepare_removes_stale_unapproved_attachment(self):
        self.prepare()
        target = self.outbox / "OLIN-TEST-001"
        stale = target / "old-draft.md"
        stale.write_text("old", encoding="utf-8")
        self.prepare()
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
