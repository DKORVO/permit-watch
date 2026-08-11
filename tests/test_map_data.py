import json
import unittest

from app.map_data import build_map_points


class OpportunityMapTests(unittest.TestCase):
    def test_uses_city_coordinates_when_available(self):
        data = build_map_points([{
            "id": 1,
            "source_name": "MERX — Canada opportunities",
            "title": "CCTV installation",
            "url": "https://example.test/1",
            "metadata": json.dumps({"City": "Ottawa", "Province": "Ontario"}),
        }])

        self.assertEqual(data["unknown"], 0)
        self.assertEqual(len(data["points"]), 1)
        point = data["points"][0]
        self.assertEqual(point["source_group"], "merx")
        self.assertEqual(point["location"], "Ottawa, Ontario")
        self.assertFalse(point["approximate"])
        self.assertEqual(point["items"][0]["enrichment_status"], "awaiting")

    def test_falls_back_to_approximate_province_location(self):
        data = build_map_points([{
            "id": 2,
            "source_name": "CanadaBuys — tender opportunities",
            "title": "Access control",
            "url": "https://example.test/2",
            "metadata": json.dumps({"Province": "Saskatchewan"}),
        }])

        point = data["points"][0]
        self.assertTrue(point["approximate"])
        self.assertEqual(point["source_group"], "canadabuys")

    def test_groups_findings_at_the_same_location_and_counts_unknown(self):
        rows = [{
            "id": identifier,
            "source_name": "City of Ottawa",
            "title": f"Application {identifier}",
            "url": f"https://example.test/{identifier}",
            "metadata": json.dumps({"Addresses": f"{identifier} Main Street"}),
        } for identifier in (1, 2)]
        rows.append({
            "id": 3,
            "source_name": "MERX — Canada opportunities",
            "title": "Unknown location",
            "url": "https://example.test/3",
            "metadata": None,
        })

        data = build_map_points(rows)

        self.assertEqual(data["unknown"], 1)
        self.assertEqual(data["points"][0]["count"], 2)
        self.assertEqual(len(data["points"][0]["items"]), 2)

    def test_cached_coordinates_override_fallback_and_expose_filters(self):
        rows = [{
            "id": 4,
            "source_name": "MERX — Canada opportunities",
            "title": "Camera installation",
            "url": "https://example.test/4",
            "relevant": 1,
            "enrichment_status": "enriched",
            "metadata": json.dumps({"City": "Ottawa", "Province": "Ontario"}),
        }]
        cache = {
            "ottawa, ontario, canada": {
                "latitude": 45.5,
                "longitude": -75.6,
                "precision": "exact",
            }
        }

        point = build_map_points(rows, cache)["points"][0]

        self.assertEqual((point["lat"], point["lng"]), (45.5, -75.6))
        self.assertFalse(point["approximate"])
        self.assertEqual(point["matched_count"], 1)
        self.assertEqual(point["items"][0]["relevant"], 1)
        self.assertEqual(point["items"][0]["enrichment_status"], "enriched")


if __name__ == "__main__":
    unittest.main()
