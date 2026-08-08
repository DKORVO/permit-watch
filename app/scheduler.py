import atexit
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from .enrichment import enrich_item
from .scraper import scrape_all


class ScrapeScheduler:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.scheduler = BackgroundScheduler(timezone=os.environ.get("TZ", "UTC"))

    def start(self):
        minutes = max(15, int(os.environ.get("SCRAPE_INTERVAL_MINUTES", "360")))
        self.scheduler.add_job(self.run, "interval", minutes=minutes, id="scrape", max_instances=1, coalesce=True)
        self.scheduler.start()
        atexit.register(lambda: self.scheduler.shutdown(wait=False))
        self.scheduler.add_job(self.run, "date", id="startup", replace_existing=True)

    def run(self):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            db = self.app.extensions["db"]
            run_id = db.begin_run()
            try:
                result = scrape_all(self.app.config["DATA_DIR"], db, enrich_item)
                db.finish_run(run_id, "success", f"{result['new']} new from {result['seen']} items ({result['relevant']} relevant)")
            except Exception as exc:
                self.app.logger.exception("Scrape run failed")
                db.finish_run(run_id, "error", str(exc)[:1000])
            return True
        finally:
            self.lock.release()
