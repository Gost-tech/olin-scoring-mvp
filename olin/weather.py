"""Open-Meteo weather context for sector-sensitive SME analysis."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import mean

import requests


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _window_end(value: str | None) -> date:
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("asOfDate must be YYYY-MM-DD") from exc
        if parsed > date.today() - timedelta(days=5):
            raise ValueError("asOfDate must allow the provider's historical-data delay")
        return parsed
    return date.today() - timedelta(days=6)


def _prior_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _daily(latitude: float, longitude: float, start: date, end: date) -> dict:
    response = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        },
        timeout=20,
    )
    response.raise_for_status()
    daily = response.json().get("daily") or {}
    maximums = [float(value) for value in daily.get("temperature_2m_max", []) if value is not None]
    minimums = [float(value) for value in daily.get("temperature_2m_min", []) if value is not None]
    precipitation = [float(value) for value in daily.get("precipitation_sum", []) if value is not None]
    if not maximums or len(maximums) != len(minimums) or len(maximums) != len(precipitation):
        raise ValueError("Open-Meteo returned incomplete daily history")
    return {"maximums": maximums, "minimums": minimums, "precipitation": precipitation}


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def analyze_weather(
    latitude: float,
    longitude: float,
    as_of_date: str | None = None,
) -> dict:
    """Compare the latest 30 complete days with the same prior-year window."""
    lat, lon = float(latitude), float(longitude)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude or longitude is invalid")
    end = _window_end(as_of_date)
    start = end - timedelta(days=29)
    baseline_end = _prior_year(end)
    baseline_start = baseline_end - timedelta(days=29)
    current = _daily(lat, lon, start, end)
    baseline = _daily(lat, lon, baseline_start, baseline_end)

    current_mean = mean(
        (high + low) / 2
        for high, low in zip(current["maximums"], current["minimums"])
    )
    baseline_mean = mean(
        (high + low) / 2
        for high, low in zip(baseline["maximums"], baseline["minimums"])
    )
    baseline_heat = max(35.0, _percentile(baseline["maximums"], .90) + 2.0)
    baseline_rain = max(30.0, _percentile(baseline["precipitation"], .90))
    extreme_days = sum(
        high >= baseline_heat or rain >= baseline_rain
        for high, rain in zip(current["maximums"], current["precipitation"])
    )
    current_precipitation = sum(current["precipitation"])
    baseline_precipitation = sum(baseline["precipitation"])
    precipitation_anomaly = (
        (current_precipitation - baseline_precipitation)
        / baseline_precipitation * 100
        if baseline_precipitation > 0 else 0.0
    )
    observed_at = datetime.now(timezone.utc).isoformat()
    reference = f"open-meteo:{lat:.5f},{lon:.5f}:{start.isoformat()}:{end.isoformat()}"
    metrics = {
        "extreme_weather_days_30d": extreme_days,
        "temperature_anomaly_c": round(current_mean - baseline_mean, 2),
        "precipitation_anomaly_pct": round(precipitation_anomaly, 1),
    }
    return {
        "provider": "open_meteo",
        "observed_at": observed_at,
        "comparison_window": {"start": start.isoformat(), "end": end.isoformat()},
        "baseline_window": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
        "signal_evidence": {
            "weather_risk": {
                "metrics": metrics,
                "source": "open_meteo",
                "verified": True,
                "evidence_reference": reference,
                "observed_at": observed_at,
            }
        },
        "limitations": [
            "Weather is sector context and not a borrower characteristic",
            "The comparison uses one prior-year window and is not a climate model",
            "A bank-approved sector sensitivity is required before decision use",
        ],
    }
