import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask

from .db import Database
from .scheduler import ScrapeScheduler
from .views import bp


def create_app():
    app = Flask(__name__)
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(data_dir / "permit_watch.sqlite3")
    db.initialize()
    app.config["DATA_DIR"] = data_dir
    app.config["DISPLAY_TIMEZONE"] = os.environ.get("TZ", "UTC")

    @app.template_filter("localtime")
    def localtime(value):
        if not value:
            return ""
        try:
            parsed = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo(app.config["DISPLAY_TIMEZONE"])).strftime("%Y-%m-%d %H:%M:%S %Z")
        except (TypeError, ValueError):
            return value
    app.extensions["db"] = db
    app.extensions["scraper_scheduler"] = ScrapeScheduler(app)
    app.register_blueprint(bp)

    # Gunicorn has one worker by design; do not raise it without moving scheduling out.
    app.extensions["scraper_scheduler"].start()
    return app
