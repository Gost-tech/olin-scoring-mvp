"""
Google Places (New) API connector -> MapsRatingData + TenureData

Endpoints:
  POST /v1/places:searchText    – find the business by free-text address/name
  GET  /v1/places/{place_id}    – rating, userRatingCount, reviews, address

Tenure strategy
---------------
The Places API (New) returns up to 5 reviews sorted by "most relevant", not
by date. We parse every review's publishTime and relativePublishTimeDescription
to find the oldest visible evidence of the business on Google Maps.
This is a conservative lower bound — the real tenure may be longer.

review_velocity_6m: count of returned reviews published in the last 182 days.
Because we only see 5 reviews, this undercounts for busy businesses; it's
used as a supporting signal, not a hard filter.

address_consistent: True when the Google-returned formattedAddress shares at
least one meaningful token with the original query (colonia / city level).
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise ImportError("pip install requests  (see requirements.txt)") from exc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .models import MapsRatingData, TenureData

PLACES_BASE = "https://places.googleapis.com/v1"

# Tokens too generic to use for address_consistent
_STOP_WORDS = {
    "cdmx", "ciudad", "mexico", "df", "de", "la", "el", "los", "las",
    "san", "del", "y", "a", "en", "mexico.", "mexico,", "cdmx,",
}


def _api_key() -> str:
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("GOOGLE_PLACES_API_KEY must be set in .env")
    return key


def _headers(field_mask: str) -> dict:
    return {
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _search_place(query: str, max_results: int = 10) -> Optional[dict]:
    """Text Search (New) — return the best matching place.

    Prefers results that already have a rating (i.e. at least one review),
    falling back to the top result if none do.
    """
    resp = requests.post(
        f"{PLACES_BASE}/places:searchText",
        headers=_headers(
            "places.id,places.displayName,places.rating,"
            "places.userRatingCount,places.formattedAddress"
        ),
        json={
            "textQuery": query,
            "languageCode": "es",
            "maxResultCount": max_results,
            "locationBias": {
                "circle": {
                    "center": {"latitude": 19.3661, "longitude": -99.0603},
                    "radius": 50000.0,
                }
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        return None
    # Prefer the first result that already has a rating
    for p in places:
        if p.get("rating") is not None:
            return p
    return places[0]


def _get_place_details(place_id: str) -> dict:
    """Place Details (New) — rating, reviews, address."""
    resp = requests.get(
        f"{PLACES_BASE}/places/{place_id}",
        headers=_headers(
            "rating,userRatingCount,reviews,"
            "displayName,formattedAddress"
        ),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _parse_publish_time(review: dict) -> Optional[date]:
    """Return the review's publish date, or None if not parseable."""
    raw = review.get("publishTime")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            pass
    return None


def _years_from_relative(description: str) -> Optional[float]:
    """
    Parse strings like '5 years ago', 'hace 3 años', 'a year ago'.
    Returns float years or None.
    """
    desc = description.lower()
    # "N years ago" / "hace N años"
    m = re.search(r"(\d+)\s+(?:year|año)", desc)
    if m:
        return float(m.group(1))
    # "a year ago" / "un año"
    if re.search(r"\ba\s+year\b|\bun\s+año\b", desc):
        return 1.0
    # months — less than a year
    m = re.search(r"(\d+)\s+(?:month|mes)", desc)
    if m:
        return round(int(m.group(1)) / 12, 2)
    return None


def _oldest_years_from_reviews(reviews: list[dict]) -> float:
    """
    Best estimate of years on Google Maps from visible review timestamps.
    Used when the Places API returns reviews (Advanced SKU).
    """
    today = date.today()
    max_years = 0.0
    for r in reviews:
        d = _parse_publish_time(r)
        if d:
            max_years = max(max_years, (today - d).days / 365.25)
        rel = r.get("relativePublishTimeDescription", "")
        yrs = _years_from_relative(rel)
        if yrs is not None:
            max_years = max(max_years, yrs)
    return round(max_years, 1)


# Review-count → minimum tenure heuristic.
# Calibrated for CDMX micro-merchants (~2-5 reviews/year accumulation rate).
# This is a conservative lower bound; actual tenure is typically 30-50% higher.
_REVIEW_COUNT_TO_MIN_YEARS: list[tuple[int, float]] = [
    (200, 10.0),
    (100, 7.0),
    (60,  5.0),
    (25,  3.5),
    (10,  2.0),
    (4,   1.0),
    (1,   0.5),
    (0,   0.0),
]


def _tenure_from_review_count(count: int) -> float:
    """
    Estimate minimum years on Google Maps from total review count.
    Fallback when review timestamps are unavailable (Basic API tier).
    """
    for threshold, years in _REVIEW_COUNT_TO_MIN_YEARS:
        if count >= threshold:
            return years
    return 0.0


def _review_velocity_6m(reviews: list[dict]) -> int:
    """
    Count reviews published in the last 182 days.
    Returns 0 when the API doesn't return review objects (Basic tier) —
    the signal is simply absent, not negative.
    """
    cutoff = date.today() - timedelta(days=182)
    count = 0
    for r in reviews:
        d = _parse_publish_time(r)
        if d and d >= cutoff:
            count += 1
            continue
        rel = r.get("relativePublishTimeDescription", "").lower()
        if any(w in rel for w in ("day", "week", "month", "hora", "día", "semana", "mes")):
            count += 1
    return count


def _address_consistent(query: str, google_address: str) -> bool:
    """
    True when the Google-formatted address shares a meaningful token with
    the original query. Filters stop-words and punctuation.
    """
    def tokenize(s: str) -> set[str]:
        tokens = re.sub(r"[^\w\s]", " ", s.lower()).split()
        return {t for t in tokens if t not in _STOP_WORDS and len(t) > 2}

    query_tokens = tokenize(query)
    address_tokens = tokenize(google_address)
    return bool(query_tokens & address_tokens)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_maps_data(address: str) -> Tuple[Optional[MapsRatingData], Optional[TenureData]]:
    """
    Find a business on Google Maps and return (MapsRatingData, TenureData).

    Returns (None, None) if the place is not found.

    TenureData.years_in_imss is always 0.0 here — set it from the IMSS
    connector before passing TenureData to the scorecard.

    Args:
        address: free-text query, e.g.
            "Abarrotes La Lupita, Iztapalapa, CDMX"
    """
    place = _search_place(address)
    if place is None:
        return None, None

    place_id = place["id"]
    details = _get_place_details(place_id)

    rating       = float(details.get("rating", 0.0))
    review_count = int(details.get("userRatingCount", 0))
    reviews      = details.get("reviews", [])
    google_addr  = details.get("formattedAddress", "")
    display_name = details.get("displayName", {}).get("text", "")

    maps = MapsRatingData(
        rating=round(rating, 1),
        review_count=review_count,
        review_velocity_6m=_review_velocity_6m(reviews),
    )

    # Tenure: prefer review timestamps if available (Advanced API tier);
    # fall back to review-count heuristic when reviews aren't returned.
    if reviews:
        years_on_maps = _oldest_years_from_reviews(reviews)
    else:
        years_on_maps = _tenure_from_review_count(review_count)

    tenure = TenureData(
        years_on_google_maps=years_on_maps,
        years_in_imss=0.0,
        address_consistent=_address_consistent(address, google_addr),
    )

    return maps, tenure
