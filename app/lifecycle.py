import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TORONTO = ZoneInfo("America/Toronto")
UTC = timezone.utc
DATE_FORMATS = (
    "%Y/%m/%d %I:%M:%S %p",
    "%Y/%m/%d %I:%M %p",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%B %d, %Y %I:%M %p",
    "%B %d, %Y",
    "%b %d, %Y %I:%M %p",
    "%b %d, %Y",
)


def metadata_dict(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_closing_at(value):
    """Normalize supported tender deadlines to a UTC timestamp."""
    text = " ".join(str(value or "").replace("\u00a0", " ").split())
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    suffixes = {
        "EST": -5, "EDT": -4, "AST": -4, "ADT": -3, "CST": -6,
        "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
    }
    suffix_match = re.search(r"\s+([A-Z]{3})$", text, flags=re.I)
    explicit_zone = None
    if suffix_match and suffix_match.group(1).upper() in suffixes:
        explicit_zone = timezone(timedelta(hours=suffixes[suffix_match.group(1).upper()]))
        text = text[:suffix_match.start()].strip()
    text = re.sub(r"\s+at\s+", " ", text, flags=re.I)
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=explicit_zone or TORONTO)
            return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def lifecycle_fields(source_name, metadata, now=None):
    values = metadata_dict(metadata)
    source = (source_name or "").lower()
    if source.startswith("city of ottawa"):
        status_text = " ".join(
            str(values.get(field, "")) for field in ("Application Status", "Review Status")
        ).lower()
        terminal = ("closed", "complete", "completed", "withdrawn", "refused", "approved")
        if any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", status_text) for word in terminal):
            return None, "closed"
        return None, "open" if status_text.strip() else "unknown"

    closing_at = parse_closing_at(values.get("Closing Date"))
    if not closing_at:
        return None, "unknown"
    current = now or datetime.now(UTC)
    closing = datetime.strptime(closing_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return closing_at, "closed" if closing < current else "open"
