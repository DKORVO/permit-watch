import json

DATASET_ID = "d23b2e02-085d-43e5-9e6e-e1d558ebfdd5"
CKAN_PACKAGE_URL = "https://www.donneesquebec.ca/recherche/api/3/action/package_show"
SEAO_SEARCH_URL = "https://www.seao.ca/OpportunityPublication/ConsulterAvis/Categorie"


def _text(value):
    return " ".join(str(value or "").split())


def _buyer_address(release):
    buyer_id = (release.get("buyer") or {}).get("id")
    party = next((p for p in release.get("parties") or [] if p.get("id") == buyer_id), {})
    address = party.get("address") or {}
    return _text(address.get("locality")), _text(address.get("region"))


def _resource_urls(source, session):
    response = session.get(
        source.get("dataset_api_url", CKAN_PACKAGE_URL),
        params={"id": source.get("dataset_id", DATASET_ID)},
        timeout=(10, 45),
    )
    response.raise_for_status()
    resources = (response.json().get("result") or {}).get("resources") or []
    resources = [
        resource for resource in resources
        if str(resource.get("format", "")).upper() == "JSON"
        and str(resource.get("name", "")).lower().startswith("hebdo_")
        and resource.get("url")
    ]
    resources.sort(key=lambda resource: resource.get("name", ""), reverse=True)
    limit = max(1, min(int(source.get("resource_limit", 8)), 12))
    return [resource["url"] for resource in resources[:limit]]


def _active_release(release, seen):
    tender = release.get("tender") or {}
    identity = release.get("ocid") or tender.get("id")
    is_active = (
        "tender" in (release.get("tag") or [])
        and tender.get("status") == "active"
        and bool(identity)
        and identity not in seen
    )
    return tender, identity if is_active else None


def _tender_categories(tender):
    values = []
    for item in tender.get("items") or []:
        classification = item.get("classification") or {}
        values.extend([classification.get("description"), item.get("description")])
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _release_item(release, tender):
    documents = tender.get("documents") or []
    url = next(
        (document.get("url") for document in documents if document.get("url")),
        SEAO_SEARCH_URL,
    )
    buyer = _text((release.get("buyer") or {}).get("name"))
    city, region = _buyer_address(release)
    categories = _tender_categories(tender)
    period = tender.get("tenderPeriod") or {}
    metadata = {
        "Organization": buyer,
        "Notice Number": _text(tender.get("id")),
        "Publication": _text(period.get("startDate") or release.get("date")),
        "Closing Date": _text(period.get("endDate")),
        "Procurement Method": _text(
            tender.get("procurementMethodDetails") or tender.get("procurementMethod")
        ),
        "Category": ", ".join(categories),
        "Province": "Quebec",
        "City": city,
        "Region": region,
    }
    metadata = {key: value for key, value in metadata.items() if value}
    title = _text(tender.get("title")) or f"SEAO notice {tender.get('id', '')}".strip()
    excerpt = _text(
        " ".join([title, buyer, *categories, metadata.get("Procurement Method", "")])
    )
    return {
        "title": title,
        "url": url,
        "published_text": metadata.get("Publication", ""),
        "excerpt": excerpt[:4000],
        "metadata": json.dumps(metadata, ensure_ascii=False),
    }


def seao_items(source, session):
    """Yield active SEAO notices from Quebec's official weekly open dataset."""
    seen = set()
    for resource_url in _resource_urls(source, session):
        response = session.get(resource_url, timeout=(10, 90))
        response.raise_for_status()
        for release in response.json().get("releases") or []:
            tender, identity = _active_release(release, seen)
            if not identity:
                continue
            seen.add(identity)
            yield _release_item(release, tender)

