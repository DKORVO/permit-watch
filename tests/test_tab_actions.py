import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.scraper import enrich_selected_items, source_matches


class SourceSelectionTests(unittest.TestCase):
    def test_source_matches_active_tab(self):
        self.assertTrue(source_matches({"type": "ottawa_devapps"}, "ottawa_devapps"))
        self.assertTrue(source_matches({"type": "canadabuys"}, "canadabuys"))
        self.assertTrue(source_matches({"name": "MERX legacy source"}, "merx"))
        self.assertFalse(source_matches({"type": "canadabuys"}, "merx"))


class FakeDatabase:
    def __init__(self):
        self.updated = []
        self.attempts = []

    def enrichment_items_by_ids(self, item_ids, source_prefix):
        self.requested = (item_ids, source_prefix)
        return [
            {
                "id": 7,
                "title": "Selected opportunity",
                "excerpt": "Access control installation",
            }
        ]

    def enrichment_budget(self, limit):
        return {"remaining": limit, "used": 0, "limit": limit}

    def record_enrichment_attempt(self, context):
        self.attempts.append(context)

    def update_enrichment(self, item_id, summary, status):
        self.updated.append((item_id, summary, status))


class SelectedEnrichmentTests(unittest.TestCase):
    def test_only_requested_records_are_enriched(self):
        db = FakeDatabase()

        result = enrich_selected_items(
            db,
            lambda item: "Selected summary",
            [7],
            "MERX",
            daily_limit=100,
        )

        self.assertEqual(db.requested, ([7], "MERX"))
        self.assertEqual(db.updated, [(7, "Selected summary", "enriched")])
        self.assertEqual(result["selected"], 1)
        self.assertEqual(result["attempted"], 1)


class RunScopeTests(unittest.TestCase):
    def test_latest_run_is_scoped_to_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "watcher.db")
            db.initialize()
            merx_run = db.begin_run("MERX")
            db.finish_run(merx_run, "success", "MERX finished")
            canada_run = db.begin_run("CanadaBuys")
            db.finish_run(canada_run, "error", "CanadaBuys failed")

            self.assertEqual(db.latest_run("MERX")["message"], "MERX finished")
            self.assertEqual(db.latest_run("CanadaBuys")["message"], "CanadaBuys failed")
            self.assertEqual(db.latest_run()["source_scope"], "CanadaBuys")

    def test_queued_run_transitions_to_running_and_success(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "watcher.db")
            db.initialize()
            run_id = db.queue_run("MERX", "MERX run queued")
            self.assertEqual(db.latest_run("MERX")["status"], "queued")

            db.start_run(run_id, "MERX run in progress")
            self.assertEqual(db.latest_run("MERX")["status"], "running")

            db.finish_run(run_id, "success", "MERX finished")
            latest = db.latest_run("MERX")
            self.assertEqual(latest["status"], "success")
            self.assertEqual(latest["message"], "MERX finished")


if __name__ == "__main__":
    unittest.main()
