import json
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from .config import env_int
from .map_data import build_map_points

bp = Blueprint("views", __name__)

SOURCE_ACTIONS = {
    "ottawa": {
        "source_type": "ottawa_devapps",
        "source_prefix": "City of Ottawa",
        "label": "City of Ottawa",
        "endpoint": "views.ottawa",
    },
    "merx": {
        "source_type": "merx",
        "source_prefix": "MERX",
        "label": "MERX",
        "endpoint": "views.merx",
    },
    "canadabuys": {
        "source_type": "canadabuys",
        "source_prefix": "CanadaBuys",
        "label": "CanadaBuys",
        "endpoint": "views.canadabuys",
    },
}


def source_action():
    section = request.form.get("section", "")
    action = SOURCE_ACTIONS.get(section)
    if not action:
        abort(400, "A valid source tab is required")
    return section, action


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


def metadata_options(items, field):
    return sorted({
        str(item["metadata"].get(field, "")).strip()
        for item in items
        if item["metadata"].get(field)
    })


def render_source_page(section):
    db = current_app.extensions["db"]
    daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 100)
    if section == "ottawa":
        rows = db.recent_items_for_source("City of Ottawa")
        page_title = "City of Ottawa"
        page_subtitle = "Development applications"
        empty_message = "No City of Ottawa findings have been collected yet."
        search_placeholder = "Application number, address, description, file lead…"
        filter_fields = [
            ("Application", "Application type"),
            ("Application Status", "Application status"),
            ("Review Status", "Review status"),
        ]
        sort_options = [
            ("newest", "Newest collected"),
            ("received", "Date received"),
            ("address", "Address"),
            ("title", "Title A–Z"),
        ]
    elif section == "merx":
        # Keep non-matches available for review; the page defaults to scored
        # physical-security integrator matches.
        rows = db.recent_items_for_source("MERX", relevant_only=False)
        page_title = "MERX"
        page_subtitle = "Canada-wide physical-security integration opportunities"
        empty_message = "No Canadian MERX opportunities have been collected yet."
        search_placeholder = "Title, organization, location, security technology…"
        filter_fields = [
            ("_Security Match", "Security relevance"),
            ("Solicitation Type", "Solicitation type"),
            ("Province", "Province"),
            ("City", "City"),
        ]
        sort_options = [
            ("closing", "Closing soon"),
            ("publication", "Publication date"),
            ("newest", "Newest collected"),
            ("title", "Title A–Z"),
        ]
    else:
        rows = db.recent_items_for_source("CanadaBuys", relevant_only=False)
        page_title = "CanadaBuys"
        page_subtitle = "Federal tender opportunities for physical-security integrators"
        empty_message = "No CanadaBuys tender opportunities have been collected yet."
        search_placeholder = "Title, department, category, security technology…"
        filter_fields = [
            ("_Security Match", "Security relevance"),
            ("Category", "Category"),
            ("Organization", "Organization"),
            ("Notice Type", "Notice type"),
            ("Province", "Province"),
            ("City", "City"),
        ]
        sort_options = [
            ("closing", "Closing soon"),
            ("publication", "Publication date"),
            ("newest", "Newest collected"),
            ("title", "Title A–Z"),
        ]

    items = [dict(item) for item in rows]
    groups = grouped_items(items)
    prepared_items = [item for group in groups.values() for item in group]
    filters = []
    for field, label in filter_fields:
        options = metadata_options(prepared_items, field)
        if field == "_Security Match":
            options = ["matched", "other"]
        filters.append({"field": field, "label": label, "options": options})

    return render_template(
        "index.html", groups=groups, total_items=len(items), latest_run=db.latest_run(page_title),
        section=section, page_title=page_title, page_subtitle=page_subtitle,
        empty_message=empty_message, search_placeholder=search_placeholder,
        filters=filters, sort_options=sort_options,
        enrichment_budget=db.enrichment_budget(daily_limit), home_summaries=None,
    )


@bp.get("/ottawa")
def ottawa():
    return render_source_page("ottawa")


@bp.get("/merx")
def merx():
    return render_source_page("merx")


@bp.get("/canadabuys")
def canadabuys():
    return render_source_page("canadabuys")


@bp.get("/")
def home():
    db = current_app.extensions["db"]
    daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 100)
    map_data = build_map_points(db.map_items(), db.cached_coordinates())
    return render_template(
        "index.html", section="home",
        groups={"awaiting": [], "enriched": [], "failed": []}, total_items=0,
        latest_run=db.latest_run(),
        enrichment_budget=db.enrichment_budget(daily_limit),
        map_data=map_data,
        home_summaries=[
            {
                "name": "City of Ottawa", "description": "Development applications",
                "endpoint": "views.ottawa", "summary": db.source_summary("City of Ottawa"),
                "show_matches": False,
            },
            {
                "name": "MERX", "description": "Canada-wide physical-security integration opportunities",
                "endpoint": "views.merx", "summary": db.source_summary("MERX"),
                "show_matches": True,
            },
            {
                "name": "CanadaBuys", "description": "Federal physical-security tender opportunities",
                "endpoint": "views.canadabuys", "summary": db.source_summary("CanadaBuys"),
                "show_matches": True,
            },
        ],
    )


@bp.get("/map")
def opportunity_map():
    db = current_app.extensions["db"]
    map_data = build_map_points(db.map_items(), db.cached_coordinates())
    return render_template(
        "map.html",
        section="map",
        page_title="Opportunity map",
        map_data=map_data,
    )


@bp.post("/run-now")
def run_now():
    section, action = source_action()
    db = current_app.extensions["db"]
    run_id = db.queue_run(action["label"], f"{action['label']} run queued")
    scraper_scheduler = current_app.extensions["scraper_scheduler"]
    try:
        scraper_scheduler.scheduler.add_job(
            scraper_scheduler.run,
            "date",
            id=f"manual-scrape-{section}",
            replace_existing=True,
            kwargs={
                "source_type": action["source_type"],
                "source_label": action["label"],
                "run_id": run_id,
            },
        )
    except Exception as exc:
        db.finish_run(run_id, "error", f"Unable to queue run: {str(exc)[:900]}")
        raise
    return redirect(url_for(action["endpoint"]))


@bp.post("/enrich-selected")
def enrich_selected():
    section, action = source_action()
    try:
        item_ids = list(dict.fromkeys(int(value) for value in request.form.getlist("item_id")))
    except ValueError:
        abort(400, "Finding IDs must be integers")
    if not item_ids or any(item_id <= 0 for item_id in item_ids):
        abort(400, "Select at least one finding")
    if len(item_ids) > 100:
        abort(400, "Select no more than 100 findings at a time")

    db = current_app.extensions["db"]
    run_id = db.queue_run(
        action["label"], f"{action['label']} selected enrichment queued"
    )
    scraper_scheduler = current_app.extensions["scraper_scheduler"]
    try:
        scraper_scheduler.scheduler.add_job(
            scraper_scheduler.enrich_selected,
            "date",
            id=f"enrich-selected-{section}",
            replace_existing=True,
            kwargs={
                "item_ids": item_ids,
                "source_prefix": action["source_prefix"],
                "source_label": action["label"],
                "run_id": run_id,
            },
        )
    except Exception as exc:
        db.finish_run(
            run_id, "error", f"Unable to queue selected enrichment: {str(exc)[:850]}"
        )
        raise
    return redirect(url_for(action["endpoint"]))

@bp.get("/run-status/<section>")
def run_status(section):
    action = SOURCE_ACTIONS.get(section)
    if not action:
        abort(404)
    row = current_app.extensions["db"].latest_run(action["label"])
    if not row:
        return jsonify(run=None)
    localtime = current_app.jinja_env.filters["localtime"]
    return jsonify(
        run={
            "id": row["id"],
            "status": row["status"],
            "message": row["message"] or "",
            "started_at": localtime(row["started_at"]),
            "finished_at": localtime(row["finished_at"]),
        }
    )


@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
