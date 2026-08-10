import json
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from .config import env_int

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


def metadata_options(items, field):
    return sorted({
        str(item["metadata"].get(field, "")).strip()
        for item in items
        if item["metadata"].get(field)
    })


def render_source_page(section):
    db = current_app.extensions["db"]
    daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 50)
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
            ("Location", "Location"),
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
            ("Location", "Region of delivery"),
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
        "index.html", groups=groups, total_items=len(items), latest_run=db.latest_run(),
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
    daily_limit = env_int("ENRICHMENT_DAILY_LIMIT", 50)
    return render_template(
        "index.html", section="home",
        groups={"awaiting": [], "enriched": [], "failed": []}, total_items=0,
        latest_run=db.latest_run(),
        enrichment_budget=db.enrichment_budget(daily_limit),
        home_summaries=[
            {
                "name": "City of Ottawa", "description": "Development applications",
                "endpoint": "views.ottawa", "summary": db.source_summary("City of Ottawa"),
            },
            {
                "name": "MERX", "description": "Canada-wide physical-security integration opportunities",
                "endpoint": "views.merx", "summary": db.source_summary("MERX"),
            },
            {
                "name": "CanadaBuys", "description": "Federal physical-security tender opportunities",
                "endpoint": "views.canadabuys", "summary": db.source_summary("CanadaBuys"),
            },
        ],
    )


@bp.post("/run-now")
def run_now():
    current_app.extensions["scraper_scheduler"].scheduler.add_job(
        current_app.extensions["scraper_scheduler"].run,
        "date",
        id="manual-scrape",
        replace_existing=True,
    )
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
