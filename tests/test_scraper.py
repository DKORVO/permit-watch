import unittest

from app.scraper import canadabuys_page_url, merx_page_url, physical_security_score


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


if __name__ == "__main__":
    unittest.main()
