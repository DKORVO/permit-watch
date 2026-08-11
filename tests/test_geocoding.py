import json
import unittest
from unittest.mock import patch

from app.geocoding import GEOAPIFY_URL, OTTAWA_LOCATOR_URL, geocode_map_locations


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.responses.pop(0))


class Database:
    def __init__(self, rows, cache=None):
        self.rows = rows
        self.cache = cache or {}
        self.saved = []

    def map_items(self):
        return self.rows

    def cached_coordinates(self):
        return self.cache

    def cache_coordinates(self, *values):
        self.saved.append(values)


class HybridGeocodingTests(unittest.TestCase):
    @patch("app.geocoding.time.sleep")
    def test_uses_official_ottawa_locator_without_geoapify_key(self, _sleep):
        db = Database([{
            "source_name": "City of Ottawa",
            "metadata": json.dumps({"Addresses": "110 Laurier Avenue West"}),
        }])
        session = Session([{"candidates": [{
            "score": 100,
            "location": {"x": -75.6901, "y": 45.4218},
        }]}])

        result = geocode_map_locations(db, "", session=session)

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(session.calls[0][0], OTTAWA_LOCATOR_URL)
        self.assertEqual(db.saved[0][1:3], (45.4218, -75.6901))

    @patch("app.geocoding.time.sleep")
    def test_uses_geoapify_only_for_unknown_non_ottawa_city(self, _sleep):
        db = Database([{
            "source_name": "MERX — Canada opportunities",
            "metadata": json.dumps({"City": "Exampleville", "Province": "Ontario"}),
        }])
        session = Session([{"results": [{
            "lat": 45.1,
            "lon": -75.1,
            "result_type": "city",
            "rank": {"confidence": 0.9},
        }]}])

        result = geocode_map_locations(db, "test-key", session=session)

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(session.calls[0][0], GEOAPIFY_URL)

    def test_known_city_is_resolved_locally_without_api_request(self):
        db = Database([{
            "source_name": "CanadaBuys — tender opportunities",
            "metadata": json.dumps({"City": "Toronto", "Province": "Ontario"}),
        }])
        session = Session([])

        result = geocode_map_locations(db, "test-key", session=session)

        self.assertEqual(result["requested"], 0)
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
