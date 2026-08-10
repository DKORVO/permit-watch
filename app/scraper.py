import hashlib
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "PermitWatch/0.1 (local civic-information monitor; contact: administrator)"

MERX_SOURCES = [
    {
        "name": "MERX — Canada opportunities",
        "url": "https://www.merx.com/public/solicitations/open",
        "type": "merx",
        "item_selector": "a.solicitation-link",
        "enabled": True,
        "min_request_interval_seconds": 5,
        "page_limit": 5,
        "page_request_interval_seconds": 1,
        "detail_lookup_limit": 100,
        "detail_request_interval_seconds": 0.5,
        "relevance_profile": "physical_security_integrator",
        "minimum_relevance_score": 6,
    },
]

CANADABUYS_SOURCE = {
    "name": "CanadaBuys — tender opportunities",
    "url": "https://canadabuys.canada.ca/en/tender-opportunities?status%5B0%5D=1920&status%5B1%5D=87",
    "type": "canadabuys",
    "enabled": True,
    "min_request_interval_seconds": 5,
    "page_limit": 1,
    "page_request_interval_seconds": 1,
    "detail_lookup_limit": 100,
    "detail_request_interval_seconds": 0.5,
    "relevance_profile": "physical_security_integrator",
    "minimum_relevance_score": 6,
}

LEGACY_MERX_SOURCE_NAMES = {
    "MERX — Ottawa opportunities",
    "MERX — Gatineau opportunities",
}

PHYSICAL_SECURITY_TERMS = (
    "access control", "card reader", "credential system", "cctv",
    "video surveillance", "security camera", "intrusion detection",
    "intrusion alarm", "burglar alarm", "intercom", "video intercom",
    "duress alarm", "panic alarm", "electronic security",
    "integrated security system", "physical security system",
    "perimeter detection", "security management system",
)
SECURITY_WORK_TERMS = (
    "integrator", "integration", "supply and install", "installation",
    "replacement", "upgrade", "retrofit", "commissioning", "programming",
    "maintenance", "repair", "support", "design-build",
)
SECURITY_BRANDS = (
    "genetec", "lenel", "avigilon", "milestone", "kantech", "axis",
    "bosch", "honeywell", "hid", "johnson controls", "gallagher", "salto",
)
SECURITY_EXCLUSIONS = (
    "cybersecurity", "network security", "information security",
    "security awareness", "penetration testing", "security guard",
    "guarding services", "patrol services", "airport screening",
    "event security", "financial security", "scada", "fire alarm only",
)


def load_sources(data_dir: Path):
    with (data_dir / "sources.json").open(encoding="utf-8") as handle:
        config = json.load(handle)
    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources.json must contain a 'sources' list")
    # Replace the legacy Ottawa/Gatineau defaults with the nationwide source.
    sources = [source for source in sources if source.get("name") not in LEGACY_MERX_SOURCE_NAMES]
    source_names = {source.get("name") for source in sources}
    builtin_sources = [*MERX_SOURCES, CANADABUYS_SOURCE]
    sources.extend(source for source in builtin_sources if source["name"] not in source_names)
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
        link = node if node.name == "a" and node.get("href") else node.select_one(source.get("link_selector", "a[href]"))
        url = urljoin(source["url"], link["href"]) if link and link.get("href") else source["url"]
        yield {"title": title, "url": url, "published_text": select_text(node, source.get("date_selector")), "excerpt": clean(node.get_text(" ", strip=True))[:4000]}


def physical_security_score(item, metadata):
    """Score a MERX opportunity for physical-security integration work."""
    text = " ".join(
        [item.get("title", ""), item.get("excerpt", ""), *[str(value) for value in metadata.values()]]
    ).lower()
    technology = sorted({term for term in PHYSICAL_SECURITY_TERMS if term in text})
    work = sorted({term for term in SECURITY_WORK_TERMS if term in text})
    brands = sorted({term for term in SECURITY_BRANDS if term in text})
    exclusions = sorted({term for term in SECURITY_EXCLUSIONS if term in text})
    score = (
        4 * min(len(technology), 2)
        + 3 * min(len(work), 2)
        + 2 * min(len(brands), 2)
        - 5 * min(len(exclusions), 2)
    )
    # "Access control" is common in software bids. Require another physical
    # technology term when software/security exclusions are also present.
    if technology == ["access control"] and exclusions:
        score = min(score, 0)
    reasons = technology + work + brands
    return score, reasons, exclusions


def merx_detail_fields(session, url):
    """Read public MERX fields and searchable detail text."""
    response = session.get(url, timeout=(10, 45))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    fields = {}
    wanted = {
        "title": "Title",
        "issuing organization": "Issuing Organization",
        "solicitation type": "Solicitation Type",
        "publication date": "Publication",
        "closing date": "Closing Date",
        "location": "Location",
        "description": "Description",
    }
    for node in soup.select(".mets-field"):
        label_node = node.select_one(".mets-field-label")
        value_node = node.select_one(".mets-field-body")
        if not label_node or not value_node:
            continue
        destination = wanted.get(normal_key(clean(label_node.get_text(" ", strip=True))))
        if destination:
            value = clean(value_node.get_text(" ", strip=True))
            if value:
                fields[destination] = value
    description = fields.pop("Description", "") or select_text(
        soup, ".solicitation-description, .mets-description, #description"
    )
    detail_text = clean(" ".join([description, soup.get_text(" ", strip=True)]))[:12000]
    return fields, detail_text


def merx_page_url(base_url, page_number):
    if page_number == 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}pageNumber={page_number}"


def merx_items(source, session):
    """Collect nationwide public MERX cards and selected detail fields."""
    detail_limit = max(0, int(source.get("detail_lookup_limit", 100)))
    detail_interval = max(0, float(source.get("detail_request_interval_seconds", 0.5)))
    page_limit = max(1, int(source.get("page_limit", 5)))
    page_interval = max(0, float(source.get("page_request_interval_seconds", 1)))
    detail_lookups = 0
    seen_urls = set()

    for page_number in range(1, page_limit + 1):
        page_url = merx_page_url(source["url"], page_number)
        response = session.get(page_url, timeout=(10, 45))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        nodes = soup.select(source.get("item_selector", "a.solicitation-link"))
        page_had_new_items = False

        for node in nodes:
            title = select_text(node, ".rowTitle") or clean(node.get_text(" ", strip=True))[:240]
            url = urljoin(source["url"], node.get("href", ""))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            page_had_new_items = True
            excerpt = clean(node.get_text(" ", strip=True))[:4000]
            fields = {
                "Issuing Organization": select_text(node, ".buyer-name"),
                "Location": select_text(node, ".location"),
                "Dates": select_text(node, ".timeRemaining"),
                "Publication": select_text(node, ".publicationDate .dateValue"),
                "Closing Date": select_text(node, ".closingDate .dateValue"),
            }
            item = {"title": title, "url": url, "published_text": fields["Publication"], "excerpt": excerpt}
            if detail_lookups < detail_limit:
                try:
                    detail_fields, detail_text = merx_detail_fields(session, url)
                    fields.update(detail_fields)
                    item["excerpt"] = detail_text[:4000] or item["excerpt"]
                except requests.RequestException as exc:
                    logger.warning("MERX detail lookup failed for %s: %s", url, exc)
                detail_lookups += 1
                time.sleep(detail_interval)
            item["title"] = fields.pop("Title", item["title"])
            yield {**item, "metadata": json.dumps({label: value for label, value in fields.items() if value})}

        if not nodes or not page_had_new_items:
            break
        if page_number < page_limit:
            time.sleep(page_interval)


def canadabuys_page_url(base_url, page_number):
    """CanadaBuys uses zero-based Drupal page numbers after the first page."""
    if page_number == 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page_number - 1}"


def canadabuys_detail(session, url):
    response = session.get(url, timeout=(10, 45))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.select_one("main") or soup
    title_node = main.select_one("h1")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    text = clean(main.get_text(" ", strip=True))
    fields = {}
    patterns = {
        "Solicitation Number": r"Solicitation number\s+(.+?)\s+Publication date",
        "Publication": r"Publication date\s+(\d{4}/\d{2}/\d{2})",
        "Closing Date": r"Closing date and time\s+(.+?)\s+(?:Last amendment date|Status)",
        "Status": r"Status\s+Status\s+(.+?)\s+Time to closing",
        "Notice Type": r"Notice type\s+(.+?)\s+Language",
        "Location": r"Region\(s\) of delivery\s+(.+?)\s+Procurement method",
    }
    for label, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            fields[label] = clean(match.group(1))
    return title, fields, text[:12000]


def canadabuys_items(source, session):
    """Collect public CanadaBuys tender rows and their public notice details."""
    page_limit = max(1, int(source.get("page_limit", 5)))
    page_interval = max(0, float(source.get("page_request_interval_seconds", 1)))
    detail_limit = max(0, int(source.get("detail_lookup_limit", 100)))
    detail_interval = max(0, float(source.get("detail_request_interval_seconds", 0.5)))
    detail_lookups = 0
    seen_urls = set()

    for page_number in range(1, page_limit + 1):
        page_url = canadabuys_page_url(source["url"], page_number)
        try:
            response = session.get(page_url, timeout=(10, 45))
            response.raise_for_status()
        except requests.RequestException as exc:
            if page_number == 1:
                raise
            # CanadaBuys can reject automated pagination even after serving
            # the first page. Keep those results and try again next run.
            logger.warning(
                "CanadaBuys pagination stopped at page %s after %s: %s",
                page_number,
                page_url,
                exc,
            )
            break
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr")
        page_had_new_items = False

        for row in rows:
            link = row.select_one('a[href*="/tender-opportunities/tender-notice/"]')
            cells = row.find_all("td")
            if not link or len(cells) < 5:
                continue
            url = urljoin(source["url"], link.get("href", ""))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            page_had_new_items = True
            fields = {
                "Category": clean(cells[1].get_text(" ", strip=True)),
                "Publication": clean(cells[2].get_text(" ", strip=True)),
                "Closing Date": clean(cells[3].get_text(" ", strip=True)),
                "Organization": clean(cells[4].get_text(" ", strip=True)),
            }
            item = {
                "title": clean(link.get_text(" ", strip=True)),
                "url": url,
                "published_text": fields["Publication"],
                "excerpt": clean(row.get_text(" ", strip=True))[:4000],
            }
            if detail_lookups < detail_limit:
                try:
                    detail_title, detail_fields, detail_text = canadabuys_detail(session, url)
                    fields.update(detail_fields)
                    item["title"] = detail_title or item["title"]
                    item["excerpt"] = detail_text[:4000] or item["excerpt"]
                except requests.RequestException as exc:
                    logger.warning("CanadaBuys detail lookup failed for %s: %s", url, exc)
                detail_lookups += 1
                time.sleep(detail_interval)
            yield {**item, "metadata": json.dumps({label: value for label, value in fields.items() if value})}

        if not rows or not page_had_new_items:
            break
        if page_number < page_limit:
            time.sleep(page_interval)


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
OTTAWA_DETAIL_API = "https://devapps-restapi.ottawa.ca/devapps"
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
    def usable(candidate):
        text = display_value(candidate)
        # Ottawa's API uses underscore-prefixed opaque identifiers in several
        # fields. They are not public addresses or other display values.
        if re.fullmatch(r"_[A-Za-z0-9_]+", text):
            return ""
        return text

    lowered = {normal_key(key): value for key, value in values.items()}
    for name in names:
        requested = normal_key(name)
        value = lowered.get(requested)
        if value not in (None, ""):
            text = usable(value)
            if text:
                return text
        for key, candidate in lowered.items():
            if requested in key or key in requested:
                if candidate not in (None, ""):
                    text = usable(candidate)
                    if text:
                        return text
    return ""


def ottawa_title(application_number, address, application_type):
    """Build a concise title using only public, readable values."""
    if address.startswith("Not provided by City of Ottawa") or re.fullmatch(r"_[A-Za-z0-9_]+", address):
        address = ""
    return " — ".join(part for part in (application_number, address, application_type) if part) or "Ottawa development application"


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


def ottawa_detail_fields(session, key, application_number):
    """Return public detail fields, including readable street addresses.

    The City's list service sometimes returns an internal address identifier.
    Its public per-application endpoint provides the actual address records.
    """
    response = session.get(
        f"{OTTAWA_DETAIL_API}/{quote(application_number, safe='')}",
        params={"authKey": key},
        timeout=(10, 45),
    )
    response.raise_for_status()
    detail = response.json()
    if not isinstance(detail, dict):
        return {}

    addresses = []
    for address in detail.get("devAppAddresses", []):
        if not isinstance(address, dict):
            continue
        text = display_value(address.get("addressNumberRoadName"))
        if not text:
            parts = [
                display_value(address.get("addressNumber")),
                display_value(address.get("addressQualifier")),
                display_value(address.get("roadName")),
                display_value(address.get("cardinalDirection")),
                display_value(address.get("roadType")),
            ]
            text = " ".join(part for part in parts if part)
        if text and text not in addresses:
            addresses.append(text)

    planner = " ".join(part for part in (
        display_value(detail.get("plannerFirstName")),
        display_value(detail.get("plannerLastName")),
    ) if part)
    # Field names have varied between releases of the public Ottawa service.
    # Check the known alternatives without exposing a generic City contact
    # number as though it belonged to the application file lead.
    planner_phone = first_value(
        detail,
        "planner phone number",
        "planner phone",
        "planner telephone",
        "file lead phone number",
        "file lead phone",
        "file lead telephone",
    )
    return {
        "Addresses": "; ".join(addresses),
        "Date Received": display_value(detail.get("applicationDateYMD")),
        "Description": display_value(detail.get("applicationBriefDesc")),
        "File Lead": planner,
        "File Lead Phone": planner_phone,
    }


def ottawa_items(source, session, db=None):
    key = find_ottawa_key(session)
    type_map = ottawa_type_map(session, key)
    response = session.get(OTTAWA_API, params={"authKey": key}, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    records = ottawa_record_list(payload)
    if not records:
        raise ValueError("Ottawa data response did not contain an application list")
    wanted_types = [clean(item).lower() for item in source.get("application_types", ["Site Plan Control", "Plan of Condominium"])]
    detail_lookup_limit = max(0, int(source.get("detail_lookup_limit", 25)))
    detail_interval = max(0.2, float(source.get("detail_request_interval_seconds", 0.5)))
    detail_lookups = 0
    known_addresses = db.resolved_addresses_by_url() if db else {}
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
            "File Lead Phone": first_value(values, "file lead phone", "planner phone", "file lead telephone", "planner telephone"),
        }
        if known_addresses.get(detail_url):
            fields["Addresses"] = known_addresses[detail_url]
        address_is_missing = not fields["Addresses"] or fields["Addresses"].startswith("Not provided by City of Ottawa")
        if number and address_is_missing and detail_lookups < detail_lookup_limit:
            try:
                detail = ottawa_detail_fields(session, key, number)
                for label, value in detail.items():
                    if value:
                        fields[label] = value
                if fields["Addresses"]:
                    known_addresses[detail_url] = fields["Addresses"]
            except (requests.RequestException, ValueError) as exc:
                # Leave the public list value in place if one detail record is
                # temporarily unavailable; a later scheduled scrape can retry.
                logger.warning("Ottawa detail lookup failed for %s: %s", number, exc)
            detail_lookups += 1
            time.sleep(detail_interval)
        title = ottawa_title(number, fields["Addresses"], application_type)
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


def budgeted_enrich(item, db, enrich, daily_limit, context):
    """Make one enrichment call only while today's local app budget remains."""
    if db.enrichment_budget(daily_limit)["remaining"] <= 0:
        return None, False
    summary = enrich(item)
    # A missing API key returns None without making an OpenRouter request.
    if summary is None:
        return None, False
    db.record_enrichment_attempt(context)
    return summary, True


def fingerprint(item):
    stable = "\n".join((item["url"], item["title"], item["published_text"], item["excerpt"]))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def collect(source, session, db=None):
    source_type = source.get("type", "html")
    if source_type == "ottawa_devapps":
        items = ottawa_items(source, session, db)
    elif source_type == "canadabuys":
        items = canadabuys_items(source, session)
    elif source_type == "merx" or (source.get("name") or "").lower().startswith("merx"):
        # Also recognize earlier sources.json entries created before the
        # dedicated MERX type was introduced.
        items = merx_items(source, session)
    else:
        get_items = rss_items if source_type == "rss" else html_items
        items = get_items(source, session)
    for item in items:
        if not item["title"]:
            continue
        item["source_name"] = source["name"]
        if source.get("relevance_profile") == "physical_security_integrator":
            try:
                metadata = json.loads(item.get("metadata") or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            score, reasons, exclusions = physical_security_score(item, metadata)
            minimum_score = int(source.get("minimum_relevance_score", 6))
            item["relevant"] = int(score >= minimum_score)
            metadata["_Security Match"] = "matched" if item["relevant"] else "other"
            metadata["_Match Score"] = score
            metadata["_Match Reasons"] = ", ".join(reasons)
            metadata["_Exclusions"] = ", ".join(exclusions)
            item["metadata"] = json.dumps(metadata)
        else:
            item["relevant"] = int(relevant(item, source))
        item["fingerprint"] = fingerprint(item)
        item["enrichment"] = None
        item["enrichment_status"] = "awaiting"
        item.setdefault("metadata", None)
        yield item


def scrape_all(data_dir, db, enrich, daily_limit=100):
    sources = load_sources(data_dir)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    counts = {"seen": 0, "new": 0, "relevant": 0, "budget_skipped": 0}
    for index, source in enumerate(sources):
        for item in collect(source, session, db):
            counts["seen"] += 1
            if item["relevant"]:
                counts["relevant"] += 1
                # Existing items are refreshed below without calling OpenRouter
                # again. This keeps a scheduled scrape from consuming quota on
                # the same historical records every time it runs.
                if not db.item_exists(item["fingerprint"], item["url"]):
                    summary, attempted = budgeted_enrich(item, db, enrich, daily_limit, "new finding")
                    if attempted:
                        item["enrichment"] = summary
                        item["enrichment_status"] = enrichment_status(summary)
                    else:
                        counts["budget_skipped"] += 1
            if db.add_item(item):
                counts["new"] += 1
        if index < len(sources) - 1:
            time.sleep(max(1, int(source.get("min_request_interval_seconds", 5))))
    return counts


def retry_failed_enrichments(db, enrich, limit, daily_limit=100):
    """Retry a capped number of failed summaries without re-scraping sources."""
    items = db.failed_enrichment_items(limit)
    counts = {"retried": 0, "awaiting": 0, "enriched": 0, "failed": 0, "budget_skipped": 0}
    for row in items:
        item = dict(row)
        summary, attempted = budgeted_enrich(item, db, enrich, daily_limit, "manual retry")
        if not attempted:
            counts["budget_skipped"] += 1
            break
        status = enrichment_status(summary)
        db.update_enrichment(item["id"], summary, status)
        counts[status] += 1
        counts["retried"] += 1
    return counts

