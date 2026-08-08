import json
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, send_from_directory, url_for

bp = Blueprint("views", __name__)

@bp.get("/")
def index():
    db = current_app.extensions["db"]
    items = [dict(item) for item in db.recent_items()]
    groups = {"awaiting": [], "enriched": [], "failed": []}
    for item in items:
        try:
            item["metadata"] = json.loads(item["metadata"]) if item.get("metadata") else {}
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
        status = item.get("enrichment_status") or "awaiting"
        groups[status if status in groups else "awaiting"].append(item)
    assets_dir = Path(current_app.config["DATA_DIR"]) / "assets"
    logo_filename = next(
        (name for name in ("ottawa-logo.png", "ottawa-logo.svg", "ottawa-logo.webp") if (assets_dir / name).is_file()),
        None,
    )
    return render_template(
        "index.html", groups=groups, total_items=len(items), latest_run=db.latest_run(),
        address_counts=db.ottawa_address_counts(), logo_filename=logo_filename,
    )


@bp.get("/assets/<filename>")
def persistent_asset(filename):
    """Serve the administrator-provided dashboard logo from persistent data."""
    allowed = {"ottawa-logo.png", "ottawa-logo.svg", "ottawa-logo.webp"}
    if filename not in allowed:
        abort(404)
    assets_dir = Path(current_app.config["DATA_DIR"]) / "assets"
    if not (assets_dir / filename).is_file():
        abort(404)
    return send_from_directory(assets_dir, filename, max_age=3600)

@bp.post("/run-now")
def run_now():
    current_app.extensions["scraper_scheduler"].scheduler.add_job(current_app.extensions["scraper_scheduler"].run, "date", replace_existing=True)
    return redirect(url_for("views.index"))


@bp.post("/retry-enrichment")
def retry_enrichment():
    scheduler = current_app.extensions["scraper_scheduler"].scheduler
    scheduler.add_job(
        current_app.extensions["scraper_scheduler"].retry_failed_enrichments,
        "date",
        id="retry-enrichment",
        replace_existing=True,
    )
    return redirect(url_for("views.index"))

@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
