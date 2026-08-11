import json
import time

import requests

from .map_data import location_query, normalized

GEOAPIFY_URL = "https://api.geoapify.com/v1/geocode/search"


def geocode_map_locations(db, api_key, limit=100, session=None):
    """Resolve and cache a bounded batch of unique Canadian locations."""
    if not api_key:
        return {"requested": 0, "resolved": 0, "unresolved": 0}
    session = session or requests.Session()
    cache = db.cached_coordinates()
    queries = []
    seen = set()
    for row in db.map_items():
        item = dict(row)
        try:
            metadata = json.loads(item.get("metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        query = location_query(metadata, item.get("source_name") or "")
        key = normalized(query)
        if not query or key in seen or key in cache:
            continue
        seen.add(key)
        queries.append((key, query))
        if len(queries) >= max(0, int(limit)):
            break

    counts = {"requested": 0, "resolved": 0, "unresolved": 0}
    for key, query in queries:
        counts["requested"] += 1
        try:
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
            if result and confidence >= 0.4:
                result_type = result.get("result_type") or "location"
                precision = "exact" if result_type in {"building", "amenity", "street"} else result_type
                db.cache_coordinates(key, result["lat"], result["lon"], precision)
                counts["resolved"] += 1
            else:
                db.cache_coordinates(key, None, None, "unresolved")
                counts["unresolved"] += 1
        except (requests.RequestException, ValueError, TypeError, KeyError):
            # Transient request failures are not cached, so a later batch can retry.
            counts["unresolved"] += 1
        time.sleep(0.22)
    return counts
