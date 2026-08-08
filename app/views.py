import json
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for

bp = Blueprint("views", __name__)

def grouped_items(items):
    groups = {"awaiting": [], "enriched": [], "failed": []}
    for item in items:
        try:
            item["metadata"] = json.loads(item["metadata"]) if item.get("metadata") else {}
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
        status = item.get("enrichment_status") or "awaiting"
        groups[status if status in groups else "awaiting"].append(item)
    return groups


def render_source_page(section):
    db = current_app.extensions["db"]
    items = [dict(item) for item in db.recent_items()]
    if section == "ottawa":
        items = [item for item in items if "ottawa" in item["source_name"].lower()]
        page_title = "City of Ottawa"
        page_subtitle = "Development applications"
        empty_message = "No City of Ottawa findings have been collected yet."
    else:
        items = [item for item in items if "merx" in item["source_name"].lower()]
        page_title = "MERX"
        page_subtitle = "Procurement opportunities"
        empty_message = "MERX monitoring is coming soon. Add a MERX source when you are ready."
    assets_dir = Path(current_app.config["DATA_DIR"]) / "assets"
    logo_filename = next(
        (name for name in ("ottawa-logo.png", "ottawa-logo.svg", "ottawa-logo.webp") if (assets_dir / name).is_file()),
        None,
    )
    return render_template(
        "index.html", groups=grouped_items(items), total_items=len(items), latest_run=db.latest_run(),
        address_counts=db.ottawa_address_counts() if section == "ottawa" else None,
        logo_filename=logo_filename, section=section, page_title=page_title,
        page_subtitle=page_subtitle, empty_message=empty_message,
    )


@bp.get("/ottawa")
def ottawa():
    return render_source_page("ottawa")


@bp.get("/merx")
def merx():
    return render_source_page("merx")


@bp.get("/")
def home():
    data_dir = Path(current_app.config["DATA_DIR"])
    logo_filename = next(
        (name for name in ("ottawa-logo.png", "ottawa-logo.svg", "ottawa-logo.webp") if (data_dir / "assets" / name).is_file()),
        None,
    )
    return render_template(
        "index.html", section="home", logo_filename=logo_filename,
        groups={"awaiting": [], "enriched": [], "failed": []}, total_items=0,
        latest_run=None, address_counts=None,
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
    return redirect(request.referrer or url_for("views.ottawa"))


@bp.post("/retry-enrichment")
def retry_enrichment():
    scheduler = current_app.extensions["scraper_scheduler"].scheduler
    scheduler.add_job(
        current_app.extensions["scraper_scheduler"].retry_failed_enrichments,
        "date",
        id="retry-enrichment",
        replace_existing=True,
    )
    return redirect(request.referrer or url_for("views.ottawa"))

@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
