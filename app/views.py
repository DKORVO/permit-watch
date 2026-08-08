import json

from flask import Blueprint, current_app, jsonify, redirect, render_template, url_for

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
    return render_template("index.html", groups=groups, total_items=len(items), latest_run=db.latest_run())

@bp.post("/run-now")
def run_now():
    current_app.extensions["scraper_scheduler"].scheduler.add_job(current_app.extensions["scraper_scheduler"].run, "date", replace_existing=True)
    return redirect(url_for("views.index"))

@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
