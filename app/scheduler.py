import atexit
import os
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .enrichment import enrich_item
from .scraper import resolve_ottawa_addresses, retry_failed_enrichments, scrape_all


class ScrapeScheduler:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.scheduler = BackgroundScheduler(timezone=os.environ.get("TZ", "UTC"))

    def start(self):
        minutes = max(15, int(os.environ.get("SCRAPE_INTERVAL_MINUTES", "360")))
        self.scheduler.add_job(self.run, "interval", minutes=minutes, id="scrape", max_instances=1, coalesce=True)
        address_minutes = max(10, int(os.environ.get("ADDRESS_RESOLUTION_INTERVAL_MINUTES", "10")))
        self.scheduler.add_job(self.resolve_ottawa_addresses, "interval", minutes=address_minutes, id="address-backfill", max_instances=1, coalesce=True)
        self.scheduler.start()
        atexit.register(lambda: self.scheduler.shutdown(wait=False))
        self.scheduler.add_job(self.run, "date", id="startup", replace_existing=True)
        self.scheduler.add_job(
            self.resolve_ottawa_addresses,
            "date",
            run_date=datetime.now(self.scheduler.timezone) + timedelta(minutes=1),
            id="address-backfill-startup",
            replace_existing=True,
        )

    def run(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run()
            try:
                daily_limit = max(1, int(os.environ.get("ENRICHMENT_DAILY_LIMIT", "35")))
                result = scrape_all(self.app.config["DATA_DIR"], db, enrich_item, daily_limit)
                budget = db.enrichment_budget(daily_limit)
                db.finish_run(
                    run_id,
                    "success",
                    f"{result['new']} new from {result['seen']} items ({result['relevant']} relevant); "
                    f"enrichment budget {budget['used']}/{budget['limit']} today",
                )
            except Exception as exc:
                self.app.logger.exception("Scrape run failed")
                db.finish_run(run_id, "error", str(exc)[:1000])
            return True
        finally:
            self.lock.release()

    def retry_failed_enrichments(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run()
            try:
                limit = max(1, int(os.environ.get("ENRICHMENT_RETRY_LIMIT", "10")))
                daily_limit = max(1, int(os.environ.get("ENRICHMENT_DAILY_LIMIT", "35")))
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

    def resolve_ottawa_addresses(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run()
            try:
                limit = max(1, int(os.environ.get("ADDRESS_RESOLUTION_BATCH_SIZE", "25")))
                result = resolve_ottawa_addresses(self.app.config["DATA_DIR"], db, limit)
                db.finish_run(run_id, "success", f"Address backfill: {result['resolved']} resolved ({result['remaining']} remaining; {result['attempted']} attempted)")
            except Exception as exc:
                self.app.logger.exception("Ottawa address backfill failed")
                db.finish_run(run_id, "error", f"Address backfill: {str(exc)[:950]}")
            return True
        finally:
            self.lock.release()
