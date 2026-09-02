"""Google Places (New) evidence connector.

Endpoints:
  POST /v1/places:searchText    – find the business by free-text address/name
  GET  /v1/places/{place_id}    – rating, userRatingCount, reviews, address

Important underwriting limitation
---------------------------------
Places returns a small, relevance-ranked review sample.  Olin records only
facts visible in that response.  It never converts review volume into inferred
business tenure.  The oldest visible review is a lower-bound observation, not
the business opening date.

review_velocity_6m: count of returned reviews published in the last 182 days.
Because we only see 5 reviews, this undercounts for busy businesses; it's
used as a supporting signal, not a hard filter.

address_consistent: True when the Google-returned formattedAddress shares at
least one meaningful token with the original query (colonia / city level).
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Tuple

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
            "places.userRatingCount,places.formattedAddress,"
            "places.businessStatus,places.primaryType,places.location"
        ),
        json={
            "textQuery": query,
            "languageCode": "es",
            "regionCode": "MX",
            "maxResultCount": max_results,
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
    """Place Details (New) — public operating and location evidence."""
    resp = requests.get(
        f"{PLACES_BASE}/places/{place_id}",
        headers=_headers(
            "rating,userRatingCount,reviews,"
            "displayName,formattedAddress,businessStatus,primaryType,types,"
            "location,googleMapsUri,websiteUri,regularOpeningHours"
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


def _oldest_visible_review(reviews: list[dict]) -> tuple[float, str]:
    """
    Best estimate of years on Google Maps from visible review timestamps.
    Used when the Places API returns reviews (Advanced SKU).
    """
    today = date.today()
    max_years = 0.0
    oldest_date: Optional[date] = None
    for r in reviews:
        d = _parse_publish_time(r)
        if d:
            max_years = max(max_years, (today - d).days / 365.25)
            if oldest_date is None or d < oldest_date:
                oldest_date = d
        rel = r.get("relativePublishTimeDescription", "")
        yrs = _years_from_relative(rel)
        if yrs is not None:
            max_years = max(max_years, yrs)
    return round(max_years, 1), oldest_date.isoformat() if oldest_date else ""


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
    Conservative address cross-check.

    A shared neighborhood alone is not enough. If the declared query contains
    a street number, the provider address must contain the same number. At
    least two meaningful text tokens must also overlap.
    """
    def tokenize(s: str) -> set[str]:
        tokens = re.sub(r"[^\w\s]", " ", s.lower()).split()
        return {t for t in tokens if t not in _STOP_WORDS and len(t) > 2}

    query_tokens = tokenize(query)
    address_tokens = tokenize(google_address)
    query_numbers = set(re.findall(r"\b\d{2,6}\b", query))
    address_numbers = set(re.findall(r"\b\d{2,6}\b", google_address))
    if query_numbers and not (query_numbers & address_numbers):
        return False
    return len(query_tokens & address_tokens) >= 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_place(address: str) -> Optional[dict[str, Any]]:
    """Return normalized, provider-observed business evidence.

    The response is safe to persist in an expediente.  It includes a clear
    observation timestamp and the Google place id used as evidence reference.
    No score or decision is produced by this function.
    """
    query = str(address or "").strip()
    if len(query) < 5:
        raise ValueError("Google Places query must contain at least 5 characters")
    if len(query) > 300:
        raise ValueError("Google Places query must be 300 characters or fewer")

    place = _search_place(query)
    if place is None:
        return None

    place_id = str(place.get("id", "")).strip()
    if not place_id:
        return None
    details = _get_place_details(place_id)
    reviews = details.get("reviews", []) or []
    google_addr = str(details.get("formattedAddress", ""))
    display_name = str((details.get("displayName") or {}).get("text", ""))
    location = details.get("location") or {}
    years_visible, oldest_review = _oldest_visible_review(reviews)
    observed_at = datetime.now(timezone.utc).isoformat()

    maps = MapsRatingData(
        rating=round(float(details.get("rating", 0.0) or 0.0), 1),
        review_count=int(details.get("userRatingCount", 0) or 0),
        review_velocity_6m=_review_velocity_6m(reviews),
        source="google_places",
        verified=True,
        evidence_reference=place_id,
        observed_at=observed_at,
        display_name=display_name,
        formatted_address=google_addr,
        business_status=str(details.get("businessStatus", "")),
        primary_type=str(details.get("primaryType", "")),
        latitude=float(location["latitude"]) if location.get("latitude") is not None else None,
        longitude=float(location["longitude"]) if location.get("longitude") is not None else None,
        google_maps_uri=str(details.get("googleMapsUri", "")),
        website_uri=str(details.get("websiteUri", "")),
        oldest_visible_review_at=oldest_review,
        review_sample_size=len(reviews),
    )
    tenure = TenureData(
        years_on_google_maps=years_visible,
        years_in_imss=0.0,
        address_consistent=_address_consistent(query, google_addr),
    )
    return {
        "provider": "google_places",
        "observed_at": observed_at,
        "maps": asdict(maps),
        "tenure": asdict(tenure),
        # Google permits place IDs to be stored. Other Places content is
        # returned for live analyst display only and must not be persisted.
        "persistable": {
            "source": "google_places",
            "verified": True,
            "evidence_reference": place_id,
            "observed_at": observed_at,
        },
        "limitations": [
            "Oldest visible review is a lower bound, not an opening date",
            "Recent-review count uses Google's limited relevance-ranked sample",
            "Only the Google place id is persisted; other Places content is live-display only",
            "Geo evidence supports review and does not independently approve credit",
        ],
    }


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
    evidence = lookup_place(address)
    if evidence is None:
        return None, None
    # Backward-compatible helper, intentionally limited to the subset Google
    # permits us to persist. Call ``lookup_place`` for live analyst display.
    # Do not silently turn live Places content into a stored underwriting
    # feature: the dossier must retain a retrievable provider reference and a
    # separate address-consistency result.
    return (
        MapsRatingData(**evidence["persistable"]),
        TenureData(
            years_on_google_maps=0.0,
            years_in_imss=0.0,
            address_consistent=evidence["tenure"]["address_consistent"],
        ),
    )
