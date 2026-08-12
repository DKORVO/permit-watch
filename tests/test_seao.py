import json
import unittest
from unittest.mock import Mock

from app.lifecycle import lifecycle_fields, parse_closing_at
from app.scraper import physical_security_score
from app.seao import seao_items


class SeaoConnectorTests(unittest.TestCase):
    def test_active_notice_is_mapped_and_duplicate_weeks_are_deduplicated(self):
        package = Mock()
        package.json.return_value = {"result": {"resources": [
            {"name": "hebdo_20260803_20260809.json", "format": "JSON", "url": "week"},
        ]}}
        release = {
            "ocid": "ocds-seao-1",
            "date": "2026-08-05T12:00:00-04:00",
            "tag": ["tender"],
            "buyer": {"id": "buyer-1", "name": "Ville de Gatineau"},
            "parties": [{"id": "buyer-1", "address": {"locality": "Gatineau", "region": "Outaouais"}}],
            "tender": {
                "id": "12345",
                "title": "Remplacement du système de vidéosurveillance",
                "status": "active",
                "procurementMethodDetails": "Appel d'offres public",
                "tenderPeriod": {
                    "startDate": "2026-08-05T12:00:00-04:00",
                    "endDate": "2026-09-10T10:30:00-04:00",
                },
                "documents": [{"url": "https://www.seao.ca/avis/12345"}],
                "items": [{"classification": {"description": "Systèmes de sécurité"}}],
            },
        }
        week = Mock()
        week.json.return_value = {"releases": [release, release]}
        session = Mock()
        session.get.side_effect = [package, week]

        items = list(seao_items({"resource_limit": 1}, session))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://www.seao.ca/avis/12345")
        metadata = json.loads(items[0]["metadata"])
        self.assertEqual(metadata["City"], "Gatineau")
        self.assertEqual(metadata["Province"], "Quebec")
        score, reasons, _ = physical_security_score(items[0], metadata)
        self.assertGreaterEqual(score, 6)
        self.assertIn("vidéosurveillance", reasons)

    def test_iso_deadline_preserves_its_offset(self):
        self.assertEqual(
            parse_closing_at("2026-09-10T10:30:00-04:00"),
            "2026-09-10T14:30:00Z",
        )

    def test_incomplete_ottawa_status_is_not_terminal(self):
        _, status = lifecycle_fields(
            "City of Ottawa — applications",
            {"Application Status": "Incomplete"},
        )
        self.assertEqual(status, "open")


if __name__ == "__main__":
    unittest.main()
