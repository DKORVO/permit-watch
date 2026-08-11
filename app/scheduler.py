import atexit
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from .config import env_int
from .enrichment import enrich_item
from .scraper import enrich_selected_items, retry_failed_enrichments, scrape_all


class ScrapeScheduler:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.scheduler = BackgroundScheduler(timezone=app.config["DISPLAY_TIMEZONE"])

    def start(self):
        minutes = env_int("SCRAPE_INTERVAL_MINUTES", 360, minimum=15)
        self.scheduler.add_job(self.run, "interval", minutes=minutes, id="scrape", max_instances=1, coalesce=True)
        self.scheduler.start()
        atexit.register(lambda: self.scheduler.shutdown(wait=False))
        self.scheduler.add_job(self.run, "date", id="startup", replace_existing=True)

    def run(self, source_type=None, source_label=None):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run(source_label or "All sources")
            try:
                daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 100)
                result = scrape_all(
                    self.app.config["DATA_DIR"], db, enrich_item, daily_limit, source_type
                )
                budget = db.enrichment_budget(daily_limit)
                db.finish_run(
                    run_id,
                    "success",
                    f"{source_label + ': ' if source_label else ''}"
                    f"{result['new']} new from {result['seen']} items ({result['relevant']} relevant); "
                    f"enrichment budget {budget['used']}/{budget['limit']} today",
                )
            except Exception as exc:
                self.app.logger.exception("Scrape run failed")
                db.finish_run(run_id, "error", str(exc)[:1000])
            return True
        finally:
            self.lock.release()

    def enrich_selected(self, item_ids, source_prefix, source_label):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run(source_label)
            try:
                daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 100)
                result = enrich_selected_items(
                    db, enrich_item, item_ids, source_prefix, daily_limit
                )
                budget = db.enrichment_budget(daily_limit)
                db.finish_run(
                    run_id,
                    "success",
                    f"{source_label} selected enrichment: "
                    f"{result['enriched']} enriched, {result['failed']} failed, "
                    f"{result['awaiting']} awaiting ({result['attempted']} attempted); "
                    f"budget {budget['used']}/{budget['limit']} today",
                )
            except Exception as exc:
                self.app.logger.exception("Selected enrichment failed")
                db.finish_run(
                    run_id,
                    "error",
                    f"{source_label} selected enrichment: {str(exc)[:900]}",
                )
            return True
        finally:
            self.lock.release()

    def retry_failed_enrichments(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run("All sources")
            try:
                limit = env_int("ENRICHMENT_RETRY_LIMIT", 10)
                daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 100)
                result = retry_failed_enrichments(db, enrich_item, limit, daily_limit)
                budget = db.enrichment_budget(daily_limit)
                db.finish_run(
                    run_id,
                    "success",
                    f"Enrichment retry: {result['enriched']} enriched, {result['failed']} still failed, "
                    f"{result['awaiting']} awaiting ({result['retried']} attempted); "
                    f"budget {budget['used']}/{budget['limit']} today",
                )
            except Exception as exc:
                self.app.logger.exception("Enrichment retry failed")
                db.finish_run(run_id, "error", f"Enrichment retry: {str(exc)[:950]}")
            return True
        finally:
            self.lock.release()
