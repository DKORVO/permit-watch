import json
import time

import requests

from .map_data import coordinates_for, location_query, normalized

GEOAPIFY_URL = "https://api.geoapify.com/v1/geocode/search"
OTTAWA_LOCATOR_URL = (
    "https://maps.ottawa.ca/arcgis/rest/services/"
    "compositeLocator/GeocodeServer/findAddressCandidates"
)


def _ottawa_candidate(session, query):
    response = session.get(
        OTTAWA_LOCATOR_URL,
        params={
            "SingleLine": query,
            "f": "json",
            "outFields": "Match_addr",
            "outSR": 4326,
            "maxLocations": 1,
        },
        timeout=(10, 30),
    )
    response.raise_for_status()
    candidates = response.json().get("candidates") or []
    candidate = candidates[0] if candidates else None
    if not candidate or float(candidate.get("score", 0)) < 80:
        return None
    location = candidate.get("location") or {}
    return float(location["y"]), float(location["x"]), "exact"


def _geoapify_candidate(session, query, api_key):
    response = session.get(
        GEOAPIFY_URL,
        params={
            "text": query,
            "filter": "countrycode:ca",
            "format": "json",
            "limit": 1,
            "apiKey": api_key,
        },
        timeout=(10, 30),
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    result = results[0] if results else None
    confidence = float((result or {}).get("rank", {}).get("confidence", 0))
    if not result or confidence < 0.4:
        return None
    result_type = result.get("result_type") or "location"
    precision = "exact" if result_type in {"building", "amenity", "street"} else result_type
    return float(result["lat"]), float(result["lon"]), precision


def geocode_map_locations(db, api_key, limit=100, session=None):
    """Resolve a cached batch using Ottawa's locator, then Geoapify as fallback."""
    session = session or requests.Session()
    cache = db.cached_coordinates()
    queries = []
    seen = set()
    batch_limit = min(500, max(0, int(limit)))

    for row in db.map_items():
        item = dict(row)
        try:
            metadata = json.loads(item.get("metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        source = item.get("source_name") or ""
        is_ottawa = normalized(source).startswith("city of ottawa")
        city = metadata.get("City", "")
        province = metadata.get("Province", "")

        # Known Canadian cities already resolve locally without using an API.
        local = coordinates_for(city, province, source)
        if not is_ottawa and local and not local[2]:
            continue

        query = location_query(metadata, source)
        key = normalized(query)
        if not query or key in seen or key in cache:
            continue
        if not is_ottawa and not api_key:
            continue
        seen.add(key)
        queries.append((key, query, is_ottawa))
        if len(queries) >= batch_limit:
            break

    counts = {"requested": 0, "resolved": 0, "unresolved": 0}
    for key, query, is_ottawa in queries:
        counts["requested"] += 1
        try:
            candidate = (
                _ottawa_candidate(session, query)
                if is_ottawa
                else _geoapify_candidate(session, query, api_key)
            )
            if candidate:
                db.cache_coordinates(key, *candidate)
                counts["resolved"] += 1
            else:
                db.cache_coordinates(key, None, None, "unresolved")
                counts["unresolved"] += 1
        except (requests.RequestException, ValueError, TypeError, KeyError):
            # Transient request failures are not cached, so a later batch can retry.
            counts["unresolved"] += 1
        time.sleep(0.22)
    return counts
