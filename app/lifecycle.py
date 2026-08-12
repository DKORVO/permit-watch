import json
import re
from datetime import datetime, timezone
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
    text = re.sub(r"\s+(EST|EDT|AST|ADT|CST|CDT|MST|MDT|PST|PDT)$", "", text, flags=re.I)
    text = re.sub(r"\s+at\s+", " ", text, flags=re.I)
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=TORONTO)
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
        if any(word in status_text for word in terminal):
            return None, "closed"
        return None, "open" if status_text.strip() else "unknown"

    closing_at = parse_closing_at(values.get("Closing Date"))
    if not closing_at:
        return None, "unknown"
    current = now or datetime.now(UTC)
    closing = datetime.strptime(closing_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return closing_at, "closed" if closing < current else "open"
