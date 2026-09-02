"""Auditable SME geointelligence from INEGI DENUE radius queries.

Only aggregate snapshots and public DENUE identifiers are stored. Radial
catchments are never represented as drive-time or observed foot traffic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import math
import os
import sqlite3
import unicodedata
from urllib.parse import quote
from uuid import uuid4

import requests

from .denue import DENUE_BASE, normalize_establishment
from .business_comparison import build_public_peer_comparison
from .models import BusinessType
from .store import connect_database


MAX_RADIUS_M = 5_000
MAX_PUBLIC_RESULTS = 5_000
RETURNED_ESTABLISHMENTS = 25
MAX_TARGET_ACTIVITY_LENGTH = 120
SQLITE_BUSY_TIMEOUT_MS = 10_000
SNAPSHOT_HISTORY_LIMIT = 100
ANNUAL_WINDOW_MIN_DAYS = 270
ANNUAL_WINDOW_MAX_DAYS = 460
ANNUAL_TARGET_DAYS = 365
CATCHMENT_BANDS_M = (250, 500, 1_000, 2_000, 5_000)
PUBLIC_FIELDS = (
    "denueId", "name", "activity", "scianCode", "sizeBand", "distanceM",
    "latitude", "longitude",
)

SECTOR_TERMS: dict[str, tuple[str, ...]] = {
    "abarrotes": ("abarrotes", "miscelanea", "minisuper", "tienda de conveniencia"),
    "jugueria": ("jugos", "bebidas", "cafeteria"),
    "taqueria": ("tacos", "antojitos", "restaurante"),
    "restaurant": ("restaurante", "alimentos", "cafeteria"),
    "retail": ("comercio al por menor",),
    "services": ("servicios",),
    "health_beauty": ("salon", "belleza", "peluqueria", "spa"),
    "professional": ("servicios profesionales", "consultoria", "contabilidad"),
    "transport": ("transporte",),
    "light_manufacturing": ("manufactura", "fabricacion"),
    "wholesale": ("comercio al por mayor",),
    "ecommerce": ("comercio por internet",),
    "construction": ("construccion",),
    "agriculture": ("agricultura", "ganaderia"),
    "hospitality": ("hotel", "alojamiento"),
    "education": ("escuela", "educacion", "capacitacion"),
    "healthcare": ("medico", "clinica", "hospital", "farmacia"),
    "pharmacy": ("farmacia", "botica", "medicamento"),
    "logistics": ("mensajeria", "paqueteria", "logistica"),
    "other": (),
}

COMPLEMENT_TERMS: dict[str, tuple[str, ...]] = {
    "abarrotes": ("panaderia", "farmacia", "tortilleria", "carniceria"),
    "jugueria": ("gimnasio", "escuela", "oficina", "mercado"),
    "taqueria": ("oficina", "bar", "escuela", "estacionamiento"),
    "restaurant": ("hotel", "bar", "oficina", "estacionamiento"),
    "retail": ("estacionamiento", "banco", "restaurante", "transporte"),
    "services": ("oficina", "banco", "restaurante", "estacionamiento"),
    "health_beauty": ("gimnasio", "boutique", "farmacia", "hotel"),
    "professional": ("oficina", "banco", "notaria", "restaurante"),
    "transport": ("gasolinera", "taller", "almacen", "estacionamiento"),
    "light_manufacturing": ("almacen", "transporte", "comercio al por mayor"),
    "wholesale": ("almacen", "transporte", "fabricacion"),
    "ecommerce": ("mensajeria", "paqueteria", "almacen"),
    "construction": ("materiales", "ferreteria", "transporte"),
    "agriculture": ("veterinaria", "fertilizantes", "transporte", "almacen"),
    "hospitality": ("restaurante", "transporte", "turismo", "estacionamiento"),
    "education": ("papeleria", "transporte", "alimentos", "libreria"),
    "healthcare": ("farmacia", "laboratorio", "transporte", "estacionamiento"),
    "pharmacy": ("consultorio", "clinica", "laboratorio", "hospital"),
    "logistics": ("almacen", "transporte", "gasolinera", "taller"),
    "other": (),
}


def _plain(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _coordinate(value: float, minimum: float, maximum: float) -> float:
    coordinate = float(value)
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise ValueError("latitude or longitude is invalid")
    return coordinate


def _validate(latitude: float, longitude: float, radius_m: int, business_type: str) -> tuple[float, float, int, str]:
    lat = _coordinate(latitude, -90, 90)
    lon = _coordinate(longitude, -180, 180)
    radius = int(radius_m)
    if radius < 50 or radius > MAX_RADIUS_M:
        raise ValueError("radiusM must be between 50 and 5000")
    segment = str(business_type or "other").strip().lower()
    if segment not in {item.value for item in BusinessType}:
        raise ValueError("businessType is not supported")
    return lat, lon, radius, segment


def fetch_nearby(latitude: float, longitude: float, radius_m: int) -> list[dict]:
    """Fetch public establishments through DENUE Buscar/todos."""
    token = os.getenv("INEGI_DENUE_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("INEGI_DENUE_TOKEN is not configured")
    url = (
        f"{DENUE_BASE}/Buscar/{quote('todos', safe='')}/"
        f"{latitude},{longitude}/{radius_m}/{token}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("INEGI DENUE returned an unexpected response")
    return [item for item in payload[:MAX_PUBLIC_RESULTS] if isinstance(item, dict)]


def _classification_rules(segment: str, target_scian: str, target_activity: str) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    scian = "".join(ch for ch in str(target_scian) if ch.isdigit())[:6]
    if target_scian and len(scian) not in (2, 3, 4, 5, 6):
        raise ValueError("targetScian must contain a 2-6 digit SCIAN prefix")
    supplied_term = _plain(str(target_activity).strip())
    if len(supplied_term) > MAX_TARGET_ACTIVITY_LENGTH:
        raise ValueError("targetActivity is too long")
    competitor_terms = (supplied_term,) if supplied_term else tuple(
        _plain(item) for item in SECTOR_TERMS[segment]
    )
    complement_terms = tuple(_plain(item) for item in COMPLEMENT_TERMS[segment])
    return scian, supplied_term, competitor_terms, complement_terms


def _matches(record: dict, terms: tuple[str, ...], scian_prefix: str) -> bool:
    code = str(record.get("scianCode") or "")
    if scian_prefix:
        return code.startswith(scian_prefix)
    haystack = _plain(f"{record.get('activity', '')} {record.get('name', '')}")
    return bool(terms and any(term in haystack for term in terms))


def _normalized_nearby(rows: list[dict], lat: float, lon: float, radius: int) -> list[dict]:
    normalized = [normalize_establishment(row, lat, lon) for row in rows]
    nearby = [
        row for row in normalized
        if row["denueId"] and row["distanceM"] is not None and row["distanceM"] <= radius
    ]
    return sorted(nearby, key=lambda row: (row["distanceM"], row["denueId"]))


def _classify(records: list[dict], competitor_terms: tuple[str, ...], complement_terms: tuple[str, ...], scian: str) -> tuple[list[dict], list[dict]]:
    competitors = [row for row in records if _matches(row, competitor_terms, scian)]
    complements = [
        row for row in records
        if not _matches(row, competitor_terms, scian)
        and _matches(row, complement_terms, "")
    ]
    return competitors, complements


def _band_counts(records: list[dict], radius_m: int) -> list[dict]:
    bands = sorted({min(radius_m, band) for band in CATCHMENT_BANDS_M})
    return [{
        "radiusM": band,
        "establishmentCount": sum((row.get("distanceM") or math.inf) <= band for row in records),
    } for band in bands]


def _market_metrics(records: list[dict], competitors: list[dict], complements: list[dict], area_km2: float) -> dict:
    categories: dict[str, int] = {}
    for row in records:
        category = str(row.get("scianSector") or row.get("activity") or "unknown")
        categories[category] = categories.get(category, 0) + 1
    total = len(records)
    concentration = sum((count / total) ** 2 for count in categories.values()) if total else 0.0
    return {
        "establishmentCount": total,
        "competitorCount": len(competitors),
        "complementaryBusinessCount": len(complements),
        "densityPerKm2": round(total / area_km2, 2),
        "sameActivityShare": round(len(competitors) / total, 4) if total else 0.0,
        "activityConcentrationHhi": round(concentration, 4),
    }


def _public_record(row: dict) -> dict:
    return {key: row[key] for key in PUBLIC_FIELDS}


def _evidence_reference(records: list[dict]) -> str:
    material = [{
        "id": row["denueId"], "activity": row["activity"],
        "scian": row["scianCode"], "size": row["sizeBand"],
        "latitude": round(float(row["latitude"]), 6),
        "longitude": round(float(row["longitude"]), 6),
    } for row in records]
    digest = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _geojson(lat: float, lon: float, records: list[dict]) -> dict:
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"kind": "subject"},
    }]
    features.extend({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
        "properties": {
            "kind": "establishment", "denueId": row["denueId"],
            "name": row["name"], "activity": row["activity"],
            "distanceM": row["distanceM"],
        },
    } for row in records[:RETURNED_ESTABLISHMENTS])
    return {"type": "FeatureCollection", "features": features}


def _signal_evidence(metrics: dict, radius: int, reference: str, observed_at: str) -> dict:
    common = {
        "source": "inegi_denue_radius", "verified": True,
        "evidence_reference": reference, "observed_at": observed_at,
    }
    return {
        "zone_commerce_density": {
            **common,
            "metrics": {
                "establishment_count": metrics["establishmentCount"],
                "same_activity_count": metrics["competitorCount"],
                "radius_m": radius,
            },
        },
        "commercial_neighbor_ecosystem": {
            **common,
            "metrics": {
                "active_neighbor_count": metrics["establishmentCount"],
                "complementary_business_count": metrics["complementaryBusinessCount"],
            },
        },
    }


def analyze_neighborhood(
    latitude: float,
    longitude: float,
    radius_m: int,
    business_type: str,
    *,
    target_scian: str = "",
    target_activity: str = "",
    raw_records: list[dict] | None = None,
) -> dict:
    """Build a sector-aware radial market profile and attachable evidence."""
    lat, lon, radius, segment = _validate(latitude, longitude, radius_m, business_type)
    scian, term, competitor_terms, complement_terms = _classification_rules(
        segment, target_scian, target_activity,
    )
    source_rows = raw_records if raw_records is not None else fetch_nearby(lat, lon, radius)
    records = _normalized_nearby(source_rows, lat, lon, radius)
    competitors, complements = _classify(records, competitor_terms, complement_terms, scian)
    area_km2 = math.pi * (radius / 1_000) ** 2
    metrics = _market_metrics(records, competitors, complements, area_km2)
    observed_at = datetime.now(timezone.utc).isoformat()
    reference = _evidence_reference(records)
    return {
        "provider": "inegi_denue",
        "analysisVersion": "geointelligence-1.0.0",
        "decisionUse": "context_only_not_default_probability",
        "observedAt": observed_at,
        "location": {"latitude": lat, "longitude": lon, "radiusM": radius},
        "sector": {"businessType": segment, "targetScian": scian or None, "targetActivity": term or None},
        "catchment": {"method": "radial_not_drive_time", "areaKm2": round(area_km2, 3), "bands": _band_counts(records, radius)},
        "metrics": metrics,
        "nearbyEstablishments": [_public_record(row) for row in records[:RETURNED_ESTABLISHMENTS]],
        "nearestCompetitors": [_public_record(row) for row in competitors[:10]],
        "nearestComplementaryBusinesses": [_public_record(row) for row in complements[:10]],
        "peerComparison": build_public_peer_comparison(competitors),
        "map": _geojson(lat, lon, records),
        "resultCount": len(records),
        "providerResultTruncated": len(source_rows) >= MAX_PUBLIC_RESULTS,
        "evidenceReference": reference,
        "establishmentIds": sorted(str(row["denueId"]) for row in records),
        "signal_evidence": _signal_evidence(metrics, radius, reference, observed_at),
        "limitations": [
            "DENUE establishment presence is commercial context, not repayment capacity",
            "Catchments are radial and are not drive-time, walking-time, or observed foot traffic",
            "Competitor classification is a transparent SCIAN/keyword rule and requires sector review",
            "Provider result limits can make dense-area counts lower bounds when truncated",
            "A missing DENUE identifier is a directory change and must be validated before it is treated as a closure",
        ],
    }


def _create_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geointelligence_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            owner_actor TEXT NOT NULL,
            location_key TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            establishment_ids_json TEXT NOT NULL,
            evidence_reference TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_geo_snapshots_owner_location_time
        ON geointelligence_snapshots(owner_actor, location_key, observed_at DESC)
    """)


def _location_key(analysis: dict) -> str:
    location, sector = analysis["location"], analysis["sector"]
    identity = {
        "latitude": round(float(location["latitude"]), 4),
        "longitude": round(float(location["longitude"]), 4),
        "radiusM": int(location["radiusM"]),
        "businessType": sector["businessType"],
        "targetScian": sector.get("targetScian"),
        "targetActivity": sector.get("targetActivity"),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _select_comparison(history: list[tuple], current_time: datetime) -> tuple | None:
    eligible = []
    for item in history:
        observed = datetime.fromisoformat(str(item[1]).replace("Z", "+00:00"))
        interval = max(0, (current_time - observed).days)
        if ANNUAL_WINDOW_MIN_DAYS <= interval <= ANNUAL_WINDOW_MAX_DAYS:
            eligible.append((abs(interval - ANNUAL_TARGET_DAYS), item))
    if eligible:
        return min(eligible, key=lambda pair: pair[0])[1]
    return history[0] if history else None


def _comparison(previous: tuple, current_ids: set[str], analysis: dict, snapshot_id: str) -> dict:
    prior_metrics = json.loads(previous[2])
    prior_ids = set(json.loads(previous[3]))
    prior_count = int(prior_metrics.get("establishmentCount", 0))
    current_count = int(analysis["metrics"]["establishmentCount"])
    previous_time = datetime.fromisoformat(str(previous[1]).replace("Z", "+00:00"))
    current_time = datetime.fromisoformat(str(analysis["observedAt"]).replace("Z", "+00:00"))
    interval_days = max(0, (current_time - previous_time).days)
    result = {
        "status": "compared", "previousSnapshotId": previous[0],
        "previousObservedAt": previous[1],
        "activeBusinessChange": round((current_count - prior_count) / prior_count, 4) if prior_count else None,
        "closureRate": round(len(prior_ids - current_ids) / len(prior_ids), 4) if prior_ids else None,
        "newEstablishmentCount": len(current_ids - prior_ids),
        "missingEstablishmentCount": len(prior_ids - current_ids),
        "comparisonCount": len(prior_ids), "intervalDays": interval_days,
        "eligibleForTwelveMonthSignal": ANNUAL_WINDOW_MIN_DAYS <= interval_days <= ANNUAL_WINDOW_MAX_DAYS,
    }
    if result["eligibleForTwelveMonthSignal"] and result["activeBusinessChange"] is not None and result["closureRate"] is not None:
        reference = f"denue-snapshots:{previous[0]}:{snapshot_id}"
        common = {
            "source": "versioned_denue_snapshots", "verified": True,
            "evidence_reference": reference, "observed_at": analysis["observedAt"],
        }
        analysis["signal_evidence"].update({
            "neighborhood_permanence": {
                **common,
                "metrics": {"active_business_change_12m": result["activeBusinessChange"], "closure_rate_12m": result["closureRate"]},
            },
            "neighborhood_closure_rate": {
                **common,
                "metrics": {"closure_rate_12m": result["closureRate"], "comparison_count": result["comparisonCount"]},
            },
        })
    return result


def save_snapshot(db_path: str, owner_actor: str, analysis: dict) -> dict:
    """Persist a partner-isolated aggregate snapshot and derive changes."""
    location_key = _location_key(analysis)
    snapshot_id = uuid4().hex
    current_ids = set(analysis.pop("establishmentIds"))
    current_time = datetime.fromisoformat(str(analysis["observedAt"]).replace("Z", "+00:00"))
    with closing(connect_database(db_path)) as conn:
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        _create_snapshot_schema(conn)
        history = conn.execute(
            f"""SELECT snapshot_id, observed_at, metrics_json,
                       establishment_ids_json, evidence_reference
                FROM geointelligence_snapshots
                WHERE owner_actor=? AND location_key=?
                ORDER BY observed_at DESC LIMIT {SNAPSHOT_HISTORY_LIMIT}""",
            (owner_actor, location_key),
        ).fetchall()
        latest = history[0] if history else None
        if latest and latest[4] == analysis["evidenceReference"]:
            analysis["snapshot"] = {
                "snapshotId": latest[0], "locationKey": location_key,
                "status": "unchanged", "previousSnapshotId": latest[0],
            }
            return analysis
        conn.execute(
            """INSERT INTO geointelligence_snapshots
               (snapshot_id, owner_actor, location_key, observed_at, metrics_json,
                establishment_ids_json, evidence_reference)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (snapshot_id, owner_actor, location_key, analysis["observedAt"],
             json.dumps(analysis["metrics"], sort_keys=True),
             json.dumps(sorted(current_ids)), analysis["evidenceReference"]),
        )
        conn.commit()
    previous = _select_comparison(history, current_time)
    comparison = (
        _comparison(previous, current_ids, analysis, snapshot_id)
        if previous else {"status": "baseline_created", "previousSnapshotId": None}
    )
    analysis["snapshot"] = {"snapshotId": snapshot_id, "locationKey": location_key, **comparison}
    return analysis
