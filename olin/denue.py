"""INEGI DENUE connector for persistent public establishment evidence.

DENUE is used as a public registry reference. It is not a credit signal by
itself and it never proves repayment capacity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
import math
import os
import re
import unicodedata
from urllib.parse import quote

import requests


DENUE_BASE = "https://www.inegi.org.mx/app/api/denue/v1/consulta"


def _token() -> str:
    value = os.getenv("INEGI_DENUE_TOKEN", "").strip()
    if not value:
        raise EnvironmentError("INEGI_DENUE_TOKEN is not configured")
    return value


def _plain(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _normalized_record(record: dict) -> dict[str, object]:
    return {_plain(key).replace(" ", "_"): value for key, value in record.items()}


def _pick(record: dict[str, object], *names: str) -> str:
    for name in names:
        value = record.get(_plain(name).replace(" ", "_"))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _street_number(text: str) -> str:
    match = re.search(r"\b(\d{1,6})\b", text or "")
    return match.group(1) if match else ""


def _distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if latitude_b is None or longitude_b is None:
        return None
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return round(6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)), 1)


def _record_to_candidate(
    raw: dict,
    query: str,
    declared_address: str,
    latitude: float,
    longitude: float,
) -> dict:
    row = _normalized_record(raw)
    name = _pick(row, "nombre", "nombre_de_la_unidad_economica")
    street = _pick(row, "calle", "nombre_de_la_vialidad")
    exterior = _pick(row, "num_exterior", "numero_exterior_o_km")
    colonia = _pick(row, "colonia", "nombre_del_asentamiento_humano")
    postal_code = _pick(row, "cp", "codigo_postal")
    location = _pick(row, "ubicacion", "entidad_municipio_localidad")
    address = ", ".join(
        item for item in (" ".join(x for x in (street, exterior) if x), colonia, postal_code, location)
        if item
    )
    declared_number = _street_number(declared_address)
    candidate_number = _street_number(" ".join((street, exterior)))
    number_match = not declared_number or declared_number == candidate_number
    name_score = SequenceMatcher(None, _plain(query), _plain(name)).ratio()
    address_tokens = {
        token for token in re.findall(r"[a-z0-9]+", _plain(declared_address))
        if len(token) > 3
    }
    candidate_tokens = set(re.findall(r"[a-z0-9]+", _plain(address)))
    overlap = len(address_tokens & candidate_tokens)
    candidate_latitude = _float(_pick(row, "latitud"))
    candidate_longitude = _float(_pick(row, "longitud"))
    distance_m = _distance_m(
        latitude,
        longitude,
        candidate_latitude,
        candidate_longitude,
    )
    proximity_score = (
        max(0.0, 1.0 - distance_m / 750.0)
        if distance_m is not None else 0.0
    )
    address_consistent = bool(
        number_match
        and overlap >= 2
        and distance_m is not None
        and distance_m <= 350
    )
    return {
        "denueId": _pick(row, "id", "id_de_establecimiento", "id_establecimiento"),
        "clee": _pick(row, "clee"),
        "name": name,
        "legalName": _pick(row, "razon_social"),
        "activity": _pick(row, "clase_actividad", "nombre_de_la_clase_de_actividad"),
        "sizeBand": _pick(row, "estrato", "personal_ocupado_estrato"),
        "address": address,
        "latitude": candidate_latitude,
        "longitude": candidate_longitude,
        "distanceM": distance_m,
        "addressConsistent": address_consistent,
        "matchScore": round(
            (name_score * 0.55)
            + (min(overlap, 3) / 3 * 0.25)
            + (proximity_score * 0.20),
            3,
        ),
    }


def normalize_establishment(raw: dict, latitude: float, longitude: float) -> dict:
    """Normalize public DENUE fields for aggregate geospatial analysis."""
    row = _normalized_record(raw)
    candidate = _record_to_candidate(raw, "", "", latitude, longitude)
    candidate.update({
        "scianCode": _pick(
            row,
            "id_clase_actividad",
            "clave_de_la_clase_de_actividad_economica",
            "codigo_scian",
        ),
        "scianSector": _pick(
            row,
            "id_sector_actividad",
            "clave_del_sector_de_actividad_economica",
        ),
    })
    return candidate


def lookup_business(
    merchant_name: str,
    declared_address: str,
    latitude: float,
    longitude: float,
    radius_m: int = 500,
) -> dict | None:
    """Find and normalize the best nearby DENUE establishment."""
    name = str(merchant_name or "").strip()
    if len(name) < 2:
        raise ValueError("merchantName must contain at least 2 characters")
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise ValueError("latitude or longitude is invalid")
    radius = max(50, min(int(radius_m), 5000))
    url = (
        f"{DENUE_BASE}/Buscar/{quote(name, safe='')}/"
        f"{float(latitude)},{float(longitude)}/{radius}/{_token()}"
    )
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return None
    candidates = [
        _record_to_candidate(
            item,
            name,
            declared_address,
            float(latitude),
            float(longitude),
        )
        for item in payload if isinstance(item, dict)
    ]
    candidates = [item for item in candidates if item["denueId"]]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["matchScore"], reverse=True)
    best = candidates[0]
    observed_at = datetime.now(timezone.utc).isoformat()
    return {
        "provider": "inegi_denue",
        "observedAt": observed_at,
        "bestMatch": best,
        "candidateCount": len(candidates),
        "alternatives": candidates[1:4],
        "persistable": {
            "denue_id": best["denueId"],
            "denue_clee": best["clee"],
            "denue_name": best["name"],
            "denue_address": best["address"],
            "denue_activity": best["activity"],
            "denue_size_band": best["sizeBand"],
            "denue_latitude": best["latitude"],
            "denue_longitude": best["longitude"],
            "denue_verified": bool(best["addressConsistent"]),
            "denue_observed_at": observed_at,
        },
        "limitations": [
            "DENUE confirms a public registry match, not repayment capacity",
            "An analyst must review ambiguous or inconsistent addresses",
        ],
    }
