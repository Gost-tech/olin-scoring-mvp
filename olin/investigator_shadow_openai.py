"""shadow-hosted-1: bounded OpenAI transport, usable only with explicit custody.

No ambient credential lookup, SDK retries, tools, or database imports.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import stat
from copy import deepcopy
from decimal import Decimal

from .investigator_shadow import (
    ACTION_CATALOGUE_VERSION,
    CATALOGUE_GUIDANCE_DIGEST,
    OUTPUT_SCHEMA,
    PROMPT,
    canonical,
    digest,
    generation_schema,
    validate_output,
)

AMENDMENT = "shadow-hosted-1"
MODEL = "gpt-5.4-mini-2026-03-17"
ENDPOINT = "https://api.openai.com/v1/responses"
PAYLOAD_VERSION = "shadow-openai-structured-3"
TRANSPORT_SCHEMA_VERSION = "shadow-openai-schema-2"


def provider_schema(context=None):
    """Fixed, loss-explicit adaptation of the application contract, not a compiler.

    uniqueItems is not in the documented provider subset; local validation still
    enforces uniqueness. Singleton enum expresses const; nullable enum gets an
    explicit type. All remaining application schema constraints are retained.
    """
    schema = deepcopy(OUTPUT_SCHEMA) if context is None else generation_schema(context)
    version = schema["properties"]["schema_version"].pop("const")
    schema["properties"]["schema_version"].update(type="string", enum=[version])
    fields = schema["properties"]["proposals"]["items"]["properties"]
    fields["references"].pop("uniqueItems")
    fields["action_type"]["type"] = ["string", "null"]
    return schema


# Standard USD rates checked 2026-09-19; no cache discount assumed.
INPUT_RATE = Decimal("0.75")
OUTPUT_RATE = Decimal("4.50")
# Reserve the entire documented context window, not an uncertain framing estimate.
REQUEST_RESERVE_USD = (400000 * INPUT_RATE + 1024 * OUTPUT_RATE) / 1000000


class HostedFailure(Exception):
    def __init__(self, status, details=None):
        super().__init__(status)  # Closed status only, never provider bodies.
        self.status = status
        self.details = details or {}


def request_id(value):
    """Accept only the bounded provider request-ID format, never arbitrary headers."""
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"req_[0-9a-f]{32}", value)
        else None
    )


def http_failure(http_status, raw, provider_request_id=None):
    """Closed metadata only; provider messages and unknown parameters are suppressed.

    https://developers.openai.com/api/docs/guides/error-codes
    A bare 429 is not proof of exhausted funds. All HTTP failures stop this run.
    """
    billing = {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
    codes = billing | {
        "invalid_api_key",
        "model_not_found",
        "rate_limit_exceeded",
        "slow_down",
        "invalid_value",
        "invalid_json",
        "invalid_parameter",
        "unsupported_parameter",
        "unsupported_value",
        "missing_required_parameter",
    }
    types = {
        "insufficient_quota",
        "rate_limit_error",
        "invalid_request_error",
        "authentication_error",
    }
    error = {}
    try:
        if len(raw) <= 32000:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                error = parsed["error"]
    except (ValueError, UnicodeError):
        pass
    code, kind = error.get("code"), error.get("type")
    code = code if isinstance(code, str) and code in codes else None
    kind = kind if isinstance(kind, str) and kind in types else None
    param = error.get("param")
    parameters = {
        "model",
        "input",
        "input[0].content",
        "input[1].content",
        "instructions",
        "text",
        "text.format",
        "text.format.type",
        "max_output_tokens",
        "reasoning",
        "reasoning.effort",
        "store",
        "stream",
        "background",
        "service_tier",
    }
    param = param if isinstance(param, str) and param in parameters else None
    status = "TRANSPORT_FAILURE_AMBIGUOUS"
    if http_status == 401:
        status = "AUTHENTICATION_FAILED"
    elif http_status == 403 or (http_status == 404 and code == "model_not_found"):
        status = "ACCESS_DENIED"
    elif http_status == 429:
        if code in billing or (code is None and kind == "insufficient_quota"):
            status = "BILLING_OR_QUOTA_BLOCKED"
        elif code in {"rate_limit_exceeded", "slow_down"} or kind == "rate_limit_error":
            status = "RATE_LIMITED"
    return HostedFailure(
        status,
        {
            "http_status": http_status
            if type(http_status) is int and 100 <= http_status <= 599
            else None,
            "error_code": code,
            "error_type": kind,
            "error_param": param,
            "request_id": request_id(provider_request_id),
            # Never retain free-form provider messages: they may echo partial inputs
            # or credentials in forms that substring redaction cannot safely cover.
            "message_disposition": "SUPPRESSED",
        },
    )


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


def request_body(context):
    """Frozen research content; versioned transport layout, explicitly UTF-8."""
    return canonical(
        {
            "model": MODEL,
            "store": False,
            "stream": False,
            "background": False,
            "service_tier": "default",
            "input": [
                {"role": "developer", "content": PROMPT},
                {"role": "user", "content": canonical(context)},
            ],
            "max_output_tokens": 1024,
            "reasoning": {"effort": "none"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "shadow_proposal",
                    "strict": True,
                    "schema": provider_schema(context),
                }
            },
        }
    ).encode("utf-8")


def generate(config, context, credential_loader, observer, diagnostics=None):
    """Exactly one HTTPS request; no redirects, retries, fallback or polling."""
    if credential_loader is None:
        raise ValueError("dedicated isolated credential custody required")
    body = request_body(context)
    if len(body) > config["max_input_tokens"]:
        raise ValueError("approved input byte upper bound exceeded")
    if diagnostics is None:
        diagnostics = {}
    diagnostics.clear()  # Never attribute a prior request ID to a later failure.
    diagnostics.update(
        payload_version=PAYLOAD_VERSION,
        payload_sha256=hashlib.sha256(body).hexdigest(),
        transport_schema_version=TRANSPORT_SCHEMA_VERSION,
        transport_schema_digest=digest(provider_schema(context)),
        catalogue_version=ACTION_CATALOGUE_VERSION,
        catalogue_guidance_digest=CATALOGUE_GUIDANCE_DIGEST,
    )
    credential = credential_loader()
    transport = http.client.HTTPSConnection("api.openai.com", 443, timeout=30)
    try:
        transport.request(
            "POST",
            "/v1/responses",
            body=body,
            headers={
                "Authorization": "Bearer " + credential,
                "Content-Type": "application/json",
            },
        )
        response = transport.getresponse()
        diagnostics["request_id"] = request_id(response.getheader("x-request-id"))
        diagnostics["http_status"] = (
            response.status
            if type(response.status) is int and 100 <= response.status <= 599
            else None
        )
        raw = response.read(32001)
        if response.status != 200:
            # Error bodies may echo credentials; only allowlisted metadata exits.
            raise http_failure(response.status, raw, diagnostics["request_id"])
        # Never persist an echoed credential, including error-response bodies.
        if credential.encode() in raw:
            raise HostedFailure("REDACTED_PROVIDER_RESPONSE")
        if observer is not None:
            observer(raw)
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
