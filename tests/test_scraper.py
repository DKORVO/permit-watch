import unittest
from unittest.mock import Mock, patch

import requests

from app.scraper import canadabuys_items, canadabuys_page_url, merx_page_url, physical_security_score


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

    def test_canadabuys_pagination_url(self):
        self.assertEqual(
            canadabuys_page_url(
                "https://canadabuys.canada.ca/en/tender-opportunities?status=open",
                2,
            ),
            "https://canadabuys.canada.ca/en/tender-opportunities?status=open&page=1",
        )

    def test_merx_pagination_url(self):
        self.assertEqual(
            merx_page_url("https://www.merx.com/public/solicitations/open", 2),
            "https://www.merx.com/public/solicitations/open?pageNumber=2",
        )


class CanadaBuysPaginationTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "name": "CanadaBuys",
            "url": "https://canadabuys.canada.ca/en/tender-opportunities?status=open",
            "page_limit": 2,
            "page_request_interval_seconds": 0,
            "detail_lookup_limit": 0,
        }
        self.first_page = Mock(
            text="""
                <table><tbody><tr>
                  <td><a href="/en/tender-opportunities/tender-notice/example">Camera replacement</a></td>
                  <td>Security equipment</td><td>2026/08/10</td>
                  <td>2026/09/10</td><td>Example department</td>
                </tr></tbody></table>
            """
        )
        self.first_page.raise_for_status.return_value = None

    @patch("app.scraper.time.sleep")
    def test_later_page_failure_keeps_first_page_results(self, _sleep):
        forbidden = Mock()
        forbidden.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        session = Mock()
        session.get.side_effect = [self.first_page, forbidden]

        items = list(canadabuys_items(self.source, session))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Camera replacement")
        self.assertEqual(session.get.call_count, 2)

    def test_first_page_failure_is_reported(self):
        forbidden = Mock()
        forbidden.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        session = Mock()
        session.get.return_value = forbidden

        with self.assertRaises(requests.HTTPError):
            list(canadabuys_items(self.source, session))


if __name__ == "__main__":
    unittest.main()
