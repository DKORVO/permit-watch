import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.db import Database
from app.lifecycle import lifecycle_fields, parse_closing_at


class LifecycleParsingTests(unittest.TestCase):
    def test_merx_deadline_is_normalized_in_toronto_time(self):
        self.assertEqual(
            parse_closing_at("2026/08/12 03:00:00 PM EDT"),
            "2026-08-12T19:00:00Z",
        )

    def test_unknown_date_is_not_closed(self):
        closing_at, status = lifecycle_fields(
            "CanadaBuys — tender opportunities",
            json.dumps({"Closing Date": "Contact buyer"}),
            now=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        self.assertIsNone(closing_at)
        self.assertEqual(status, "unknown")

    def test_past_and_future_deadlines_are_classified(self):
        now = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(
            lifecycle_fields(
                "MERX", json.dumps({"Closing Date": "2026/08/12 03:00:00 PM EDT"}), now
            )[1],
            "open",
        )
        self.assertEqual(
            lifecycle_fields(
                "MERX", json.dumps({"Closing Date": "2026/08/11 03:00:00 PM EDT"}), now
            )[1],
            "closed",
        )

    def test_terminal_ottawa_status_is_closed(self):
        self.assertEqual(
            lifecycle_fields(
                "City of Ottawa",
                json.dumps({"Application Status": "Application completed"}),
            )[1],
            "closed",
        )


class LifecycleDatabaseTests(unittest.TestCase):
    def make_item(self, identifier, closing_date):
        return {
            "source_name": "MERX — Canada opportunities",
            "title": f"Finding {identifier}",
            "url": f"https://example.test/{identifier}",
            "published_text": "",
            "excerpt": "",
            "fingerprint": f"fingerprint-{identifier}",
            "relevant": 1,
            "enrichment": None,
            "metadata": json.dumps({"Closing Date": closing_date}),
            "enrichment_status": "awaiting",
        }

    def test_closed_records_are_excluded_from_summary_and_map(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "watcher.db")
            db.initialize()
            db.add_item(self.make_item(1, "2020/01/01"))
            db.add_item(self.make_item(2, "2099/01/01"))

            self.assertEqual(db.source_summary("MERX")["total"], 1)
            self.assertEqual(len(db.map_items()), 1)

    def test_retention_cleanup_deletes_only_old_normalized_deadlines(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "watcher.db")
            db.initialize()
            db.add_item(self.make_item(1, "2020/01/01"))
            db.add_item(self.make_item(2, "Not supplied"))

            self.assertEqual(db.purge_closed_items(90), 1)
            self.assertEqual(len(db.recent_items_for_source("MERX", relevant_only=False)), 1)


if __name__ == "__main__":
    unittest.main()
