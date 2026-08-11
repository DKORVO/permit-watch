import json
import unittest

from app.map_data import build_map_points


class OpportunityMapTests(unittest.TestCase):
    def test_uses_city_coordinates_when_available(self):
        data = build_map_points([
            {
                "id": 1,
                "source_name": "MERX — Canada opportunities",
                "title": "CCTV installation",
                "url": "https://example.test/1",
                "metadata": json.dumps({"City": "Ottawa", "Province": "Ontario"}),
            }
        ])

        self.assertEqual(data["unknown"], 0)
        self.assertEqual(len(data["points"]), 1)
        point = data["points"][0]
        self.assertEqual(point["source_group"], "merx")
        self.assertEqual(point["location"], "Ottawa, Ontario")
        self.assertFalse(point["approximate"])

    def test_falls_back_to_approximate_province_location(self):
        data = build_map_points([
            {
                "id": 2,
                "source_name": "CanadaBuys — tender opportunities",
                "title": "Access control",
                "url": "https://example.test/2",
                "metadata": json.dumps({"Province": "Saskatchewan"}),
            }
        ])

        point = data["points"][0]
        self.assertTrue(point["approximate"])
        self.assertEqual(point["source_group"], "canadabuys")

    def test_groups_findings_at_the_same_location_and_counts_unknown(self):
        rows = [
            {
                "id": identifier,
                "source_name": "City of Ottawa",
                "title": f"Application {identifier}",
                "url": f"https://example.test/{identifier}",
                "metadata": json.dumps({"Addresses": f"{identifier} Main Street"}),
            }
            for identifier in (1, 2)
        ]
        rows.append(
            {
                "id": 3,
                "source_name": "MERX — Canada opportunities",
                "title": "Unknown location",
                "url": "https://example.test/3",
                "metadata": None,
            }
        )

        data = build_map_points(rows)

        self.assertEqual(data["unknown"], 1)
        self.assertEqual(data["points"][0]["count"], 2)
        self.assertEqual(len(data["points"][0]["items"]), 2)


if __name__ == "__main__":
    unittest.main()
