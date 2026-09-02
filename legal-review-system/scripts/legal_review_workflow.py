#!/usr/bin/env python3
"""Prepare, approve, and explicitly send an Olin legal-review package."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import default
import hashlib
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys


SYSTEM_ROOT = Path(__file__).resolve().parents[1]
OUTBOX = SYSTEM_ROOT / "outbox"
MATTER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,79}$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class WorkflowError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_matter(value: str) -> str:
    if not MATTER_RE.fullmatch(value):
        raise WorkflowError("matter must be 3-80 safe characters")
    return value


def validate_email(value: str) -> str:
    value = value.strip()
    if not EMAIL_RE.fullmatch(value):
        raise WorkflowError("recipient email is invalid")
    return value


def matter_dir(matter: str) -> Path:
    return OUTBOX / validate_matter(matter)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"missing workflow file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"invalid workflow file: {path.name}") from exc


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_message(manifest: dict, contract_bytes: bytes) -> EmailMessage:
    message = EmailMessage()
    message["From"] = manifest["from_email"]
    message["To"] = manifest["recipient_email"]
    message["Subject"] = f"Revisión legal solicitada — {manifest['matter']} — piloto sombra Olin"
    message.set_content(
        f"""Hola {manifest['recipient_name']},

Te comparto un borrador de acuerdo para un piloto sombra B2B de Olin con una institución financiera en México. El documento está marcado como no firmable y busca tu revisión, no una validación automática.

Por favor ayúdanos a confirmar o corregir:
1. el perímetro regulatorio exacto de Olin bajo estos hechos;
2. los roles de responsable/encargado y el anexo de datos;
3. aviso, autorización y evidencia para datos bancarios y Círculo;
4. seguridad, incidentes, retención, eliminación y subencargados;
5. responsabilidad, indemnidad, auditoría, firma y solución de controversias;
6. los cambios necesarios antes de cualquier fase con decisiones reales o dinero.

Te agradecería devolver comentarios o una versión con cambios y señalar cualquier supuesto que debamos resolver con la institución.

Matter: {manifest['matter']}
Hash SHA-256 del borrador: {manifest['contract_sha256']}

Gracias,
Brice Garnier
Olin
"""
    )
    filename = manifest["contract_filename"]
    if filename.lower().endswith(".docx"):
        maintype = "application"
        subtype = "vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        maintype = "text"
        subtype = "markdown"
    message.add_attachment(contract_bytes, maintype=maintype, subtype=subtype, filename=filename)
    return message


def prepare(args: argparse.Namespace) -> None:
    contract = Path(args.contract).expanduser().resolve()
    if not contract.is_file():
        raise WorkflowError("contract file does not exist")
    recipient_email = validate_email(args.recipient_email)
    target = matter_dir(args.matter)
    target.mkdir(parents=True, exist_ok=True)
    if (target / "sent.json").exists():
        raise WorkflowError("matter was already sent; create a new matter/version")
    for existing in target.iterdir():
        if not existing.is_file():
            raise WorkflowError("matter directory contains an unexpected subdirectory")
        existing.unlink()

    contract_bytes = contract.read_bytes()
    attachment = target / contract.name
    attachment.write_bytes(contract_bytes)
    manifest = {
        "schema_version": 1,
        "matter": args.matter,
        "status": "PREPARED_NOT_APPROVED",
        "prepared_at": utc_now(),
        "recipient_name": args.recipient_name.strip(),
        "recipient_email": recipient_email,
        "from_email": args.from_email.strip(),
        "contract_filename": contract.name,
        "contract_sha256": sha256(attachment),
        "legal_status": "DRAFT_FOR_MEXICAN_COUNSEL_NOT_FOR_SIGNATURE",
    }
    write_json(target / "manifest.json", manifest)
    message = build_message(manifest, contract_bytes)
    (target / "review-request.eml").write_bytes(message.as_bytes(policy=default))
    (target / "REVIEW_BEFORE_APPROVAL.txt").write_text(
        "Open review-request.eml and the attached contract. Confirm recipient, entity "
        "placeholders, scope, and questions. Approval covers only the recorded SHA-256.\n",
        encoding="utf-8",
    )
    print(f"PREPARED_NOT_APPROVED {target}")


def approve(args: argparse.Namespace) -> None:
    target = matter_dir(args.matter)
    manifest = load_json(target / "manifest.json")
    attachment = target / manifest["contract_filename"]
    current_hash = sha256(attachment)
    if current_hash != manifest["contract_sha256"]:
        raise WorkflowError("contract changed after preparation; prepare again")
    if (target / "sent.json").exists():
        raise WorkflowError("matter was already sent")
    approval = {
        "schema_version": 1,
        "matter": args.matter,
        "approved_at": utc_now(),
        "approved_by": args.approved_by.strip(),
        "contract_sha256": current_hash,
        "recipient_email": manifest["recipient_email"],
        "approval_scope": "SEND_TO_NAMED_MEXICAN_COUNSEL_FOR_REVIEW_ONLY",
    }
    write_json(target / "approval.json", approval)
    manifest["status"] = "APPROVED_TO_SEND"
    write_json(target / "manifest.json", manifest)
    print(f"APPROVED_TO_SEND {target}")


def smtp_settings() -> tuple[str, int, str, str, str]:
    host = os.getenv("OLIN_LEGAL_SMTP_HOST", "").strip()
    user = os.getenv("OLIN_LEGAL_SMTP_USER", "").strip()
    password = os.getenv("OLIN_LEGAL_SMTP_PASSWORD", "")
    from_email = os.getenv("OLIN_LEGAL_FROM_EMAIL", "").strip()
    try:
        port = int(os.getenv("OLIN_LEGAL_SMTP_PORT", "465"))
    except ValueError as exc:
        raise WorkflowError("OLIN_LEGAL_SMTP_PORT must be an integer") from exc
    if not all((host, user, password, from_email)):
        raise WorkflowError("SMTP environment is incomplete; nothing was sent")
    validate_email(from_email)
    return host, port, user, password, from_email


def send(args: argparse.Namespace) -> None:
    if args.confirm_send != "SEND":
        raise WorkflowError("send requires --confirm-send SEND")
    target = matter_dir(args.matter)
    manifest = load_json(target / "manifest.json")
    approval = load_json(target / "approval.json")
    if (target / "sent.json").exists():
        raise WorkflowError("matter was already sent")
    attachment = target / manifest["contract_filename"]
    current_hash = sha256(attachment)
    if not (
        current_hash == manifest["contract_sha256"] == approval["contract_sha256"]
        and manifest["recipient_email"] == approval["recipient_email"]
    ):
        raise WorkflowError("approval does not match the current package")
    host, port, user, password, from_email = smtp_settings()
    if from_email != manifest["from_email"]:
        raise WorkflowError("approved From address differs from SMTP From address")
    message = build_message(manifest, attachment.read_bytes())
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)
    receipt = {
        "schema_version": 1,
        "matter": args.matter,
        "sent_at": utc_now(),
        "recipient_email": manifest["recipient_email"],
        "contract_sha256": current_hash,
    }
    write_json(target / "sent.json", receipt)
    manifest["status"] = "SENT_FOR_COUNSEL_REVIEW"
    write_json(target / "manifest.json", manifest)
    print("SENT_FOR_COUNSEL_REVIEW")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    actions = root.add_subparsers(dest="action", required=True)
    prep = actions.add_parser("prepare", help="create a local review package and email preview")
    prep.add_argument("--contract", required=True)
    prep.add_argument("--matter", required=True)
    prep.add_argument("--recipient-name", required=True)
    prep.add_argument("--recipient-email", required=True)
    prep.add_argument("--from-email", default="garnierbrice.s213@gmail.com")
    prep.set_defaults(handler=prepare)
    approval = actions.add_parser("approve", help="approve the exact package hash")
    approval.add_argument("--matter", required=True)
    approval.add_argument("--approved-by", required=True)
    approval.set_defaults(handler=approve)
    sender = actions.add_parser("send", help="send one approved package through SMTP over TLS")
    sender.add_argument("--matter", required=True)
    sender.add_argument("--confirm-send", required=True)
    sender.set_defaults(handler=send)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.handler(args)
        return 0
    except WorkflowError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
