import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = "PermitWatch/0.1 (local civic-information monitor; contact: administrator)"


def load_sources(data_dir: Path):
    with (data_dir / "sources.json").open(encoding="utf-8") as handle:
        config = json.load(handle)
    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources.json must contain a 'sources' list")
    return [s for s in sources if s.get("enabled", True)]


def clean(value):
    return " ".join((value or "").split())


def display_value(value):
    """Render Ottawa's bilingual values as their English public label."""
    if isinstance(value, dict):
        preferred = value.get("en") or value.get("fr") or next((item for item in value.values() if item not in (None, "")), "")
        return display_value(preferred)
    if isinstance(value, list):
        return ", ".join(display_value(item) for item in value if display_value(item))
    return clean(str(value)) if value is not None else ""


def normal_key(key):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(key).replace("_", " "))
    return re.sub(r"\s+", " ", spaced).strip().lower()

def select_text(node, selector):
    found = node.select_one(selector) if selector else None
    return clean(found.get_text(" ", strip=True) if found else "")


def html_items(source, session):
    response = session.get(source["url"], timeout=(10, 45))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    selector = source.get("item_selector")
    if not selector:
        raise ValueError(f"{source['name']}: item_selector is required for HTML sources")
    for node in soup.select(selector):
        title = select_text(node, source.get("title_selector")) or clean(node.get_text(" ", strip=True))[:240]
        link = node.select_one(source.get("link_selector", "a[href]"))
        url = urljoin(source["url"], link["href"]) if link and link.get("href") else source["url"]
        yield {"title": title, "url": url, "published_text": select_text(node, source.get("date_selector")), "excerpt": clean(node.get_text(" ", strip=True))[:4000]}


def rss_items(source, session):
    response = session.get(source["url"], timeout=(10, 45))
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "xml")
    for node in soup.select("item, entry"):
        link = node.find("link")
        url = (link.get("href") if link and link.get("href") else (link.text if link else source["url"]))
        title_tag = node.find("title")
        date_tag = node.find("pubDate") or node.find("updated")
        excerpt_tag = node.find("description") or node.find("summary") or node
        yield {"title": clean(title_tag.get_text(" ", strip=True) if title_tag else ""), "url": urljoin(source["url"], url), "published_text": clean(date_tag.get_text(" ", strip=True) if date_tag else ""), "excerpt": clean(excerpt_tag.get_text(" ", strip=True))[:4000]}


OTTAWA_LANDING_PAGE = "https://devapps.ottawa.ca/en/"
OTTAWA_API = "https://devapps-restapi.ottawa.ca/devapps/feature/all"
OTTAWA_TYPES_API = "https://devapps-restapi.ottawa.ca/devapps/apptype/all"
# Values exposed by the City of Ottawa's public Application Type selector.
# Keep the dynamic lookup below as a fallback for future types.
OTTAWA_KNOWN_TYPE_CODES = {
    "____5ccv": "Site Plan Control",
    "__1ovdh7": "Plan of Condominium",
}


def find_ottawa_key(session):
    """Obtain the public client key from Ottawa's current JavaScript bundle.

    The key is distributed by the City's own public page and can change; it is
    deliberately discovered at run time rather than stored in sources.json.
    """
    page = session.get(OTTAWA_LANDING_PAGE, timeout=(10, 45))
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    bundles = [urljoin(OTTAWA_LANDING_PAGE, tag["src"]) for tag in soup.select("script[src]") if "/js/app." in tag.get("src", "")]
    if not bundles:
        raise ValueError("Ottawa application bundle was not found")
    script = session.get(bundles[0], timeout=(10, 45))
    script.raise_for_status()
    patterns = [r"authKey.{0,80}?[\"']([A-Za-z0-9._-]{12,})[\"']", r"[\"']authKey[\"']\s*[:,]\s*[\"']([A-Za-z0-9._-]{12,})[\"']"]
    for pattern in patterns:
        match = re.search(pattern, script.text)
        if match:
            return match.group(1)
    raise ValueError("Ottawa public client key format changed")


def ottawa_properties(record):
    if isinstance(record, dict):
        for key in ("properties", "attributes", "data"):
            if isinstance(record.get(key), dict):
                return record[key]
        return record
    return {}


def ottawa_record_list(payload):
    """Locate the list in the City's response without coupling to its wrapper."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("features", "data", "results", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = ottawa_record_list(value)
            if nested:
                return nested
    return []


def first_value(values, *names):
    lowered = {normal_key(key): value for key, value in values.items()}
    for name in names:
        requested = normal_key(name)
        value = lowered.get(requested)
        if value not in (None, ""):
            return display_value(value)
        for key, candidate in lowered.items():
            if requested in key or key in requested:
                if candidate not in (None, ""):
                    return display_value(candidate)
    return ""


def ottawa_type_map(session, key):
    """Map the API's internal application-type codes to their public names."""
    response = session.get(OTTAWA_TYPES_API, params={"authKey": key}, timeout=(10, 60))
    response.raise_for_status()
    mapping = {}
    for record in ottawa_record_list(response.json()):
        values = ottawa_properties(record)
        label = first_value(values, "application type", "applicationtype", "description", "name", "label", "title")
        if not label:
            continue
        for value in values.values():
            candidate = clean(str(value)).lower()
            if candidate and candidate != label.lower():
                mapping[candidate] = label
    return mapping


def ottawa_items(source, session):
    key = find_ottawa_key(session)
    type_map = ottawa_type_map(session, key)
    response = session.get(OTTAWA_API, params={"authKey": key}, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    records = ottawa_record_list(payload)
    if not records:
        raise ValueError("Ottawa data response did not contain an application list")
    wanted_types = [clean(item).lower() for item in source.get("application_types", ["Site Plan Control", "Plan of Condominium"])]
    for record in records:
        values = ottawa_properties(record)
        application_type = first_value(values, "application type", "applicationtype", "application type description", "type")
        # City field labels vary across records/releases. Match against every
        # public field, then retain the matched type for a readable title.
        record_values = [display_value(value).lower() for value in values.values()]
        record_text = " ".join(record_values)
        resolved_types = [type_map.get(value, OTTAWA_KNOWN_TYPE_CODES.get(value, "")) for value in record_values]
        resolved_types = [item for item in resolved_types if item]
        type_text = " ".join([record_text, *resolved_types]).lower()
        matched_type = next((wanted for wanted in wanted_types if wanted in type_text), "")
        if wanted_types and not matched_type:
            continue
        application_type = application_type or (resolved_types[0] if resolved_types else matched_type.title())
        number = first_value(values, "application number", "applicationnumber", "file number", "filenumber")
        address = first_value(values, "address", "site address", "municipal address", "location")
        title = " — ".join(part for part in (number, address, application_type) if part) or "Ottawa development application"
        published = first_value(values, "date received", "application date", "date submitted", "date")
        details = "; ".join(f"{key}: {display_value(value)}" for key, value in values.items() if value not in (None, ""))
        detail_url = f"{OTTAWA_LANDING_PAGE}applications/{number}/details" if number else OTTAWA_LANDING_PAGE
        fields = {
            "Application #": number,
            "Application Status": first_value(values, "application status", "application file status", "status"),
            "Date Received": first_value(values, "date received", "received date", "application received date", "application date"),
            "Addresses": first_value(values, "addresses", "address list", "address", "site address", "municipal address", "location"),
            "Application": application_type,
            "Review Status": first_value(values, "review status", "application review status", "reviewstatus"),
            "Status Date": first_value(values, "status date", "statusdate"),
            "Description": first_value(values, "description", "application description", "proposal description", "proposal"),
            "File Lead": first_value(values, "file lead", "filelead", "file lead name", "planner", "planner name", "case officer", "lead"),
        }
        yield {"title": title, "url": detail_url, "published_text": published, "excerpt": details[:4000], "metadata": json.dumps(fields)}


def relevant(item, source):
    words = [word.lower() for word in source.get("keywords", [])]
    return not words or any(word in (item["title"] + " " + item["excerpt"]).lower() for word in words)


def enrichment_status(summary):
    if not summary:
        return "awaiting"
    lowered = summary.lower()
    if lowered.startswith("enrichment unavailable") or lowered.startswith("enrichment returned no summary"):
        return "failed"
    return "enriched"


def fingerprint(item):
    stable = "\n".join((item["url"], item["title"], item["published_text"], item["excerpt"]))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def collect(source, session):
    source_type = source.get("type", "html")
    if source_type == "ottawa_devapps":
        get_items = ottawa_items
    else:
        get_items = rss_items if source_type == "rss" else html_items
    for item in get_items(source, session):
        if not item["title"]:
            continue
        item["source_name"] = source["name"]
        item["relevant"] = int(relevant(item, source))
        item["fingerprint"] = fingerprint(item)
        item["enrichment"] = None
        item["enrichment_status"] = "awaiting"
        item.setdefault("metadata", None)
        yield item


def scrape_all(data_dir, db, enrich):
    sources = load_sources(data_dir)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    counts = {"seen": 0, "new": 0, "relevant": 0}
    for index, source in enumerate(sources):
        for item in collect(source, session):
            counts["seen"] += 1
            if item["relevant"]:
                counts["relevant"] += 1
                item["enrichment"] = enrich(item)
                item["enrichment_status"] = enrichment_status(item["enrichment"])
            if db.add_item(item):
                counts["new"] += 1
        if index < len(sources) - 1:
            time.sleep(max(1, int(source.get("min_request_interval_seconds", 5))))
    return counts


def retry_failed_enrichments(db, enrich, limit):
    """Retry a capped number of failed summaries without re-scraping sources."""
    items = db.failed_enrichment_items(limit)
    counts = {"retried": len(items), "awaiting": 0, "enriched": 0, "failed": 0}
    for row in items:
        item = dict(row)
        summary = enrich(item)
        status = enrichment_status(summary)
        db.update_enrichment(item["id"], summary, status)
        counts[status] += 1
    return counts
