import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from app.scraper import (
    canadabuys_items,
    canadian_location_parts,
    load_sources,
    merx_page_url,
    ottawa_items,
    physical_security_score,
    rescore_stored_security_items,
)


class OttawaCollectorTests(unittest.TestCase):
    @patch("app.scraper.time.sleep")
    @patch("app.scraper.ottawa_detail_fields")
    @patch("app.scraper.ottawa_type_map", return_value={})
    @patch("app.scraper.find_ottawa_key", return_value="public-key")
    def test_missing_list_address_is_filled_from_public_detail(
        self, _find_key, _type_map, detail_fields, _sleep
    ):
        response = Mock()
        response.json.return_value = {
            "features": [
                {
                    "properties": {
                        "Application Type": "Site Plan Control",
                        "Application Number": "D07-12-26-0001",
                        "Address": "Not provided by City of Ottawa",
                        "Date Received": "2026-08-18",
                    }
                }
            ]
        }
        session = Mock()
        session.get.return_value = response
        detail_fields.return_value = {"Addresses": "110 Laurier Avenue West"}

        items = list(ottawa_items({"detail_lookup_limit": 1}, session))

        self.assertEqual(len(items), 1)
        self.assertIn("110 Laurier Avenue West", items[0]["title"])
        self.assertEqual(json.loads(items[0]["metadata"])["Addresses"], "110 Laurier Avenue West")
        detail_fields.assert_called_once_with(session, "public-key", "D07-12-26-0001")


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

    def test_brand_substrings_and_work_verbs_do_not_create_a_match(self):
        item = {
            "title": "Facilities maintenance",
            "excerpt": "Installation and maintenance services for children and accessibility.",
        }
        score, reasons, _ = physical_security_score(item, {})
        self.assertLess(score, 6)
        self.assertNotIn("hid", reasons)

    def test_plural_security_camera_bid_matches(self):
        item = {
            "title": "Security cameras modernization",
            "excerpt": "Supply and install new cameras at municipal buildings.",
        }
        score, reasons, _ = physical_security_score(item, {})
        self.assertGreaterEqual(score, 6)
        self.assertIn("security cameras", reasons)

    def test_merx_pagination_url(self):
        self.assertEqual(
            merx_page_url("https://www.merx.com/public/solicitations/open", 2),
            "https://www.merx.com/public/solicitations/open?pageNumber=2",
        )


class StoredSecurityRescoreTests(unittest.TestCase):
    def test_historical_rows_are_rescored_without_old_match_feedback(self):
        db = Mock()
        db.stored_security_items.return_value = [
            {
                "id": 1,
                "source_name": "MERX — Ottawa opportunities",
                "title": "Programmed Culvert Replacement Package",
                "excerpt": "",
                "relevant": 1,
                "metadata": json.dumps({
                    "_Security Match": "matched",
                    "_Match Reasons": "replacement, integration",
                }),
            },
            {
                "id": 2,
                "source_name": "MERX — Ottawa opportunities",
                "title": "CCTV asset inspection and decision support",
                "excerpt": "",
                "relevant": 1,
                "metadata": None,
            },
        ]

        result = rescore_stored_security_items(db)

        self.assertEqual(result, {"seen": 2, "relevant": 1, "changed": 1})
        first_update = db.update_item_relevance.call_args_list[0].args
        second_update = db.update_item_relevance.call_args_list[1].args
        self.assertEqual(first_update[0:2], (1, 0))
        self.assertEqual(second_update[0:2], (2, 1))
        self.assertEqual(json.loads(first_update[2])["_Security Match"], "other")
        self.assertEqual(json.loads(second_update[2])["_Security Match"], "matched")


class CanadianLocationTests(unittest.TestCase):
    def test_extracts_province_and_city(self):
        self.assertEqual(
            canadian_location_parts("Canada, Ontario, Ottawa"),
            ("Ontario", "Ottawa"),
        )

    def test_province_only_leaves_city_empty(self):
        self.assertEqual(canadian_location_parts("QC"), ("Quebec", ""))



class SourceMigrationTests(unittest.TestCase):
    def test_existing_canadabuys_source_uses_open_data_feed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "sources.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "name": "CanadaBuys — tender opportunities",
                                "type": "canadabuys",
                                "url": "https://canadabuys.canada.ca/en/tender-opportunities?page=1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            source = load_sources(data_dir)[0]

        self.assertEqual(
            source["url"],
            "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv",
        )
        self.assertIn("/en/tender-opportunities?", source["landing_url"])


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
            "tenderDescription-descriptionAppelOffres-eng,regionsOfDelivery-regionLivraison-eng,noticeURL\n"
            "CCTV replacement,REF-7,SOL-7,2026-08-10,2026-09-10T14:00:00,"
            "Open,GD,Example department,Supply and install security cameras,"
            "\"Canada, Ontario, Ottawa\","
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
        self.assertEqual(metadata["Province"], "Ontario")
        self.assertEqual(metadata["City"], "Ottawa")

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

