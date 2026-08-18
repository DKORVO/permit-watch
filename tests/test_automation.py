import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.digest import send_daily_digest
from app.scraper import should_auto_enrich


class AutomaticEnrichmentPolicyTests(unittest.TestCase):
    def test_only_matched_procurement_records_auto_enrich(self):
        procurement = {"relevance_profile": "physical_security_integrator", "type": "merx"}
        self.assertTrue(should_auto_enrich(procurement, {"relevant": 1}))
        self.assertFalse(should_auto_enrich(procurement, {"relevant": 0}))
        self.assertFalse(should_auto_enrich({"type": "html"}, {"relevant": 1}))

    def test_all_ottawa_applications_auto_enrich(self):
        source = {"type": "ottawa_devapps"}
        self.assertTrue(should_auto_enrich(source, {"relevant": 0}))


class FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message


class DailyDigestTests(unittest.TestCase):
    def setUp(self):
        FakeSmtp.instances.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "watcher.db")
        self.db.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_item(self, identifier, source, relevant):
        self.db.add_item({
            "source_name": source,
            "title": f"Finding {identifier}",
            "url": f"https://example.test/{identifier}",
            "published_text": "",
            "excerpt": "Public opportunity",
            "fingerprint": f"digest-{identifier}",
            "relevant": relevant,
            "enrichment": f"Summary {identifier}" if relevant else None,
            "metadata": json.dumps({}),
            "enrichment_status": "enriched" if relevant else "awaiting",
        })

    @patch.dict("os.environ", {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "watcher@example.test",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "watcher@example.test",
        "DIGEST_EMAIL_TO": "sales@example.test",
        "SMTP_STARTTLS": "true",
    }, clear=False)
    def test_digest_sends_matched_procurement_and_all_ottawa(self):
        self.add_item(1, "MERX — Canada opportunities", 1)
        self.add_item(2, "MERX — Canada opportunities", 0)
        self.add_item(3, "City of Ottawa — applications", 0)

        result = send_daily_digest(self.db, smtp_factory=FakeSmtp)

        self.assertEqual(result, {"status": "sent", "items": 2})
        smtp = FakeSmtp.instances[0]
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("watcher@example.test", "secret"))
        body = smtp.message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("Finding 1", body)
        self.assertNotIn("Finding 2", body)
        self.assertIn("Finding 3", body)
        self.assertIsNotNone(self.db.latest_digest_sent_at())

    @patch.dict("os.environ", {
        "SMTP_HOST": "",
        "SMTP_FROM": "",
        "DIGEST_EMAIL_TO": "",
    }, clear=False)
    def test_digest_is_disabled_without_email_configuration(self):
        self.assertEqual(
            send_daily_digest(self.db, smtp_factory=FakeSmtp),
            {"status": "disabled", "items": 0},
        )
        self.assertEqual(FakeSmtp.instances, [])


if __name__ == "__main__":
    unittest.main()
