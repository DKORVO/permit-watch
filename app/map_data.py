import json
import re
import unicodedata
from collections import OrderedDict

PROVINCE_COORDINATES = {
    "alberta": (54.0, -115.0),
    "british columbia": (54.0, -125.0),
    "manitoba": (54.5, -97.0),
    "new brunswick": (46.6, -66.3),
    "newfoundland and labrador": (53.1, -60.0),
    "nova scotia": (45.0, -63.0),
    "ontario": (50.0, -85.0),
    "prince edward island": (46.4, -63.3),
    "quebec": (53.0, -71.5),
    "saskatchewan": (54.0, -106.0),
    "northwest territories": (64.0, -119.0),
    "nunavut": (66.0, -96.0),
    "yukon": (64.0, -135.0),
}

CITY_COORDINATES = {
    "brampton": (43.7315, -79.7624),
    "calgary": (51.0447, -114.0719),
    "charlottetown": (46.2382, -63.1311),
    "edmonton": (53.5461, -113.4938),
    "fredericton": (45.9636, -66.6431),
    "gatineau": (45.4765, -75.7013),
    "halifax": (44.6488, -63.5752),
    "hamilton": (43.2557, -79.8711),
    "iqaluit": (63.7467, -68.5170),
    "kingston": (44.2312, -76.4860),
    "kitchener": (43.4516, -80.4925),
    "laval": (45.6066, -73.7124),
    "london": (42.9849, -81.2453),
    "longueuil": (45.5312, -73.5181),
    "mississauga": (43.5890, -79.6441),
    "moncton": (46.0878, -64.7782),
    "montreal": (45.5019, -73.5674),
    "montréal": (45.5019, -73.5674),
    "ottawa": (45.4215, -75.6972),
    "oshawa": (43.8971, -78.8658),
    "quebec city": (46.8139, -71.2080),
    "quebec": (46.8139, -71.2080),
    "québec": (46.8139, -71.2080),
    "regina": (50.4452, -104.6189),
    "saint john": (45.2733, -66.0633),
    "saskatoon": (52.1332, -106.6700),
    "sherbrooke": (45.4000, -71.9000),
    "st johns": (47.5615, -52.7126),
    "st. john's": (47.5615, -52.7126),
    "sudbury": (46.4917, -80.9930),
    "thunder bay": (48.3809, -89.2477),
    "toronto": (43.6532, -79.3832),
    "vancouver": (49.2827, -123.1207),
    "victoria": (48.4284, -123.3656),
    "waterloo": (43.4643, -80.5204),
    "whitehorse": (60.7212, -135.0568),
    "windsor": (42.3149, -83.0364),
    "winnipeg": (49.8951, -97.1384),
    "yellowknife": (62.4540, -114.3718),
}


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"\s+", " ", "".join(char for char in text if not unicodedata.combining(char))).strip().lower()


def coordinates_for(city, province, source_name):
    city_key = normalized(city)
    if normalized(source_name).startswith("city of ottawa"):
        return (*CITY_COORDINATES["ottawa"], False)
    if city_key in CITY_COORDINATES:
        return (*CITY_COORDINATES[city_key], False)
    province_key = normalized(province)
    if province_key in PROVINCE_COORDINATES:
        return (*PROVINCE_COORDINATES[province_key], True)
    for name, coordinates in PROVINCE_COORDINATES.items():
        if name in province_key:
            return (*coordinates, True)
    return None


def build_map_points(rows):
    """Group stored relevant findings by mapped location and source."""
    groups = OrderedDict()
    unknown = 0
    for row in rows:
        item = dict(row)
        try:
            metadata = json.loads(item.get("metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        source = item.get("source_name") or "Unknown source"
        city = metadata.get("City", "")
        province = metadata.get("Province", "")
        if normalized(source).startswith("city of ottawa"):
            city = city or "Ottawa"
            province = province or "Ontario"
        resolved = coordinates_for(city, province, source)
        if not resolved:
            unknown += 1
            continue
        latitude, longitude, approximate = resolved
        location = ", ".join(value for value in (city, province) if value)
        if not location:
            location = metadata.get("Location") or metadata.get("Addresses") or "Approximate location"
        source_group = (
            "ottawa" if normalized(source).startswith("city of ottawa")
            else "canadabuys" if normalized(source).startswith("canadabuys")
            else "merx"
        )
        key = (latitude, longitude, source_group, location)
        group = groups.setdefault(
            key,
            {
                "lat": latitude,
                "lng": longitude,
                "source_group": source_group,
                "source": source,
                "location": location,
                "approximate": approximate,
                "count": 0,
                "items": [],
            },
        )
        group["count"] += 1
        if len(group["items"]) < 8:
            group["items"].append(
                {
                    "title": item.get("title") or "Untitled finding",
                    "url": item.get("url") or "",
                    "closing": metadata.get("Closing Date", ""),
                }
            )
    return {"points": list(groups.values()), "unknown": unknown}
