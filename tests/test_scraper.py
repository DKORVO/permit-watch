import json
import unittest
from unittest.mock import Mock

import requests

from app.scraper import canadabuys_items, merx_page_url, physical_security_score


class PhysicalSecurityScoreTests(unittest.TestCase):
    def test_integrator_bid_matches(self):
        item = {
            "title": "Access control and CCTV replacement",
            "excerpt": "Supply, install, program, and commission the new system.",
        }
        score, reasons, exclusions = physical_security_score(item, {})
        self.assertGreaterEqual(score, 6)
        self.assertIn("access control", reasons)
        self.assertEqual(exclusions, [])

    def test_software_access_control_is_rejected(self):
        item = {
            "title": "Online services platform",
            "excerpt": "Role-based access control and cybersecurity implementation.",
        }
        score, _, exclusions = physical_security_score(item, {})
        self.assertLess(score, 6)
        self.assertIn("cybersecurity", exclusions)

    def test_guard_services_are_rejected(self):
        item = {
            "title": "Security guard and patrol services",
            "excerpt": "Provide guarding services for public facilities.",
        }
        score, _, exclusions = physical_security_score(item, {})
        self.assertLess(score, 6)
        self.assertIn("security guard", exclusions)

    def test_merx_pagination_url(self):
        self.assertEqual(
            merx_page_url("https://www.merx.com/public/solicitations/open", 2),
            "https://www.merx.com/public/solicitations/open?pageNumber=2",
        )


class CanadaBuysOpenDataTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "name": "CanadaBuys",
            "url": "https://canadabuys.canada.ca/opendata/pub/open.csv",
            "landing_url": "https://canadabuys.canada.ca/en/tender-opportunities?status=open",
        }

    def response(self, content):
        response = Mock(content=content.encode("utf-8"))
        response.raise_for_status.return_value = None
        return response

    def test_csv_notice_keeps_hyperlink_and_metadata(self):
        csv_text = (
            "title-titre-eng,referenceNumber-numeroReference,"
            "solicitationNumber-numeroSollicitation,publicationDate-datePublication,"
            "tenderClosingDate-appelOffresDateCloture,tenderStatus-appelOffresStatut-eng,"
            "procurementCategory-categorieApprovisionnement,"
            "contractingEntityName-nomEntitContractante-eng,"
            "tenderDescription-descriptionAppelOffres-eng,noticeURL\n"
            "CCTV replacement,REF-7,SOL-7,2026-08-10,2026-09-10T14:00:00,"
            "Open,GD,Example department,Supply and install security cameras,"
            "https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/example\n"
        )
        session = Mock()
        session.get.return_value = self.response(csv_text)

        items = list(canadabuys_items(self.source, session))

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"],
            "https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/example",
        )
        metadata = json.loads(items[0]["metadata"])
        self.assertEqual(metadata["Category"], "Goods")
        self.assertEqual(metadata["Organization"], "Example department")
        self.assertEqual(metadata["Solicitation Number"], "SOL-7")

    def test_non_open_rows_are_ignored(self):
        csv_text = (
            "title-titre-eng,tenderStatus-appelOffresStatut-eng,noticeURL\n"
            "Expired opportunity,Expired,https://example.test/expired\n"
        )
        session = Mock()
        session.get.return_value = self.response(csv_text)

        self.assertEqual(list(canadabuys_items(self.source, session)), [])

    def test_missing_notice_url_gets_unique_landing_link(self):
        csv_text = (
            "title-titre-eng,referenceNumber-numeroReference,"
            "tenderStatus-appelOffresStatut-eng\n"
            "Access control,REF 12,Open\n"
        )
        session = Mock()
        session.get.return_value = self.response(csv_text)

        item = list(canadabuys_items(self.source, session))[0]

        self.assertTrue(item["url"].endswith("#notice-REF%2012"))

    def test_download_failure_is_reported(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        session = Mock()
        session.get.return_value = response

        with self.assertRaises(requests.HTTPError):
            list(canadabuys_items(self.source, session))


if __name__ == "__main__":
    unittest.main()
