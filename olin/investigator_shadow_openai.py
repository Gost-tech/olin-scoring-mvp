"""shadow-hosted-1: bounded OpenAI transport, usable only with explicit custody.

No ambient credential lookup, SDK retries, tools, or database imports.
"""

from __future__ import annotations

import http.client
import json
import os
import stat
from decimal import Decimal

from .investigator_shadow import OUTPUT_SCHEMA, PROMPT, canonical, validate_output

AMENDMENT = "shadow-hosted-1"
MODEL = "gpt-5.4-mini-2026-03-17"
ENDPOINT = "https://api.openai.com/v1/responses"
# Standard USD rates checked 2026-09-19; no cache discount assumed.
INPUT_RATE = Decimal("0.75")
OUTPUT_RATE = Decimal("4.50")
# Reserve the entire documented context window, not an uncertain framing estimate.
REQUEST_RESERVE_USD = (400000 * INPUT_RATE + 1024 * OUTPUT_RATE) / 1000000


class HostedFailure(Exception):
    def __init__(self, status):
        super().__init__(status)  # Closed status only, never provider bodies.
        self.status = status


def validate_config(config):
    required = {
        "mode",
        "endpoint",
        "model",
        "synthetic_only",
        "approval_reference",
        "transmission_approval_reference",
        "synthetic_transmission_approved",
        "max_requests",
        "max_input_tokens",
        "max_output_tokens",
        "timeout_seconds",
        "total_budget_usd",
        "authority_amendment",
    }
    if set(config) != required or (
        config["mode"] != "openai"
        or config["endpoint"] != ENDPOINT
        or config["model"] != MODEL
        or config["authority_amendment"] != AMENDMENT
        or config["synthetic_only"] is not True
        or config["synthetic_transmission_approved"] is not True
    ):
        raise ValueError("explicit hosted synthetic authorization required")
    for field in ("approval_reference", "transmission_approval_reference"):
        if (
            not isinstance(config[field], str)
            or not 1 <= len(config[field].strip()) <= 200
        ):
            raise ValueError("accountable approval reference required")
    for field, low, high in (
        ("max_requests", 1, 3),
        ("max_input_tokens", 16384, 16384),
        ("max_output_tokens", 1024, 1024),
        ("timeout_seconds", 30, 30),
    ):
        if type(config[field]) is not int or not low <= config[field] <= high:
            raise ValueError("frozen finite hosted limits required")
    budget = config["total_budget_usd"]
    if not isinstance(budget, str) or len(budget) > 16:
        raise ValueError("explicit decimal USD budget required")
    try:
        amount = Decimal(budget)
    except Exception as exc:
        raise ValueError("invalid USD budget") from exc
    if not amount.is_finite() or not (
        config["max_requests"] * REQUEST_RESERVE_USD <= amount <= Decimal("1.00")
    ):
        raise ValueError("budget must cover full reservation and be at most one USD")


def read_dedicated_credential(path):
    """Called only inside the isolated worker, never by the coordinator."""
    if not path or not os.path.isabs(path):
        raise ValueError("absolute dedicated credential file required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or not 1 <= info.st_size <= 1024
        ):
            raise ValueError("private owned dedicated credential file required")
        value = stream.read(1025).decode("ascii").strip()
    if not 16 <= len(value) <= 1024 or any(c.isspace() for c in value):
        raise ValueError("invalid dedicated credential")
    return value


def generate(config, context, credential_loader, observer):
    """Exactly one HTTPS request; no redirects, retries, fallback or polling."""
    if credential_loader is None:
        raise ValueError("dedicated isolated credential custody required")
    content, instructions = canonical(context), PROMPT + canonical(OUTPUT_SCHEMA)
    if len((content + instructions).encode()) > config["max_input_tokens"]:
        raise ValueError("approved input byte upper bound exceeded")
    credential = credential_loader()
    transport = http.client.HTTPSConnection("api.openai.com", 443, timeout=30)
    try:
        transport.request(
            "POST",
            "/v1/responses",
            body=canonical(
                {
                    "model": MODEL,
                    "store": False,
                    "stream": False,
                    "background": False,
                    "service_tier": "default",
                    "instructions": instructions,
                    "input": content,
                    "max_output_tokens": 1024,
                    "reasoning": {"effort": "none"},
                    # JSON mode avoids changing the frozen schema to fit the provider's
                    # schema subset. Full closed validation remains mandatory locally.
                    "text": {"format": {"type": "json_object"}},
                }
            ),
            headers={
                "Authorization": "Bearer " + credential,
                "Content-Type": "application/json",
            },
        )
        response = transport.getresponse()
        raw = response.read(32001)
        # Never persist an echoed credential, including error-response bodies.
        if credential.encode() in raw:
            raise HostedFailure("REDACTED_PROVIDER_RESPONSE")
        if observer is not None:
            observer(raw)
        if response.status != 200:
            raise HostedFailure("TRANSPORT_FAILURE_AMBIGUOUS")
        if len(raw) > 32000:
            raise ValueError("oversized provider response")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("model") != MODEL:
            raise ValueError("provider model mismatch")
        if data.get("status") == "incomplete":
            raise HostedFailure("INCOMPLETE")
        if data.get("status") != "completed" or not isinstance(
            data.get("output"), list
        ):
            raise ValueError("provider completion required")
        messages = []
        for item in data["output"]:
            if not isinstance(item, dict) or item.get("type") != "message":
                raise ValueError("unexpected tool or reasoning output")
            if item.get("role") != "assistant" or item.get("status") != "completed":
                raise ValueError("completed assistant message required")
            if not isinstance(item.get("content"), list):
                raise TypeError("message content list required")
            for part in item["content"]:
                if not isinstance(part, dict):
                    raise TypeError("message content object required")
                if part.get("type") == "refusal":
                    raise HostedFailure("REFUSAL")
                if part.get("type") != "output_text" or not isinstance(
                    part.get("text"), str
                ):
                    raise ValueError("text-only output required")
                messages.append(part["text"])
        if len(messages) != 1:
            raise ValueError("single closed response required")
        proposal = validate_output(json.loads(messages[0]), context)
        usage = data.get("usage")
        if usage is not None:
            if not isinstance(usage, dict) or any(
                type(usage.get(k)) is not int or usage[k] < 0
                for k in ("input_tokens", "output_tokens")
            ):
                raise ValueError("invalid usage")
            if usage["input_tokens"] > 400000 or usage["output_tokens"] > 1024:
                raise ValueError("provider exceeded reserved limits")
            usage = {k: usage[k] for k in ("input_tokens", "output_tokens")}
        return proposal, usage
    finally:
        transport.close()
