"""Canonical JSON encoding for Investigator state and integrity digests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import UUID

CANONICALIZATION_VERSION = "olin-canonical-json-1"


class CanonicalizationError(ValueError):
    """Raised when a value has no unambiguous Investigator encoding."""


def normalize_timestamp(value: datetime) -> str:
    """Return a UTC timestamp with an explicit, fixed-width microsecond precision."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("timestamps must be timezone-aware")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError("binary floating-point values are not canonical")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalizationError("decimal values must be finite")
        return format(value, "f")
    if isinstance(value, datetime):
        return normalize_timestamp(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("object keys must be strings")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise CanonicalizationError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a logical value as deterministic UTF-8 JSON bytes."""
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""
    return sha256(canonical_json_bytes(value)).hexdigest()
