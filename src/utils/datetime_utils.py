# API datetime formats
# Used today (2026-03-25), matches: https://api.snooker.org/?t=14&tr=main
# - ScheduledDate/InitDate/ModDate: 2026-03-30T12:00:00Z
# - Sessions (not used by app): 31.03.2026 14:00:00

# Legacy (supported by code; not seen today):
#   2026-03-30T12:00:00+00:00, 
#   2026-03-30T12:00:00, 
#   2025-10-08 11:30:00

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.constants import DEFAULT_TIMEZONE

def _ensure_utc(dt: datetime) -> datetime:
    """Ensures a datetime object is timezone-aware (defaulting to UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def parse_api_datetime(date_str: str) -> datetime:
    """
    Parses various API datetime string formats into a UTC-aware datetime.
    """
    if not isinstance(date_str, str) or not date_str.strip():
        raise ValueError(f"Unable to parse date string '{date_str}': empty or non-string")

    date_str = date_str.strip()
    if len(date_str) == 10 and date_str.count("-") == 2:
        raise ValueError(
            f"Unable to parse date string '{date_str}': date-only values are not supported"
        )

    # Attempt standard parsing (ISO 8601 & standard SQL formats)
    # Note: .replace("Z", "+00:00") ensures compatibility with Python < 3.11
    # Note: fromisoformat natively handles "2025-10-08 11:30:00"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return _ensure_utc(dt)
    except ValueError:
        pass

    # Attempt legacy formats
    legacy_formats = (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    )
    
    for fmt in legacy_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return _ensure_utc(dt)
        except ValueError:
            continue

    # If all parsing attempts fail
    raise ValueError(f"Unable to parse date string '{date_str}'")

def resolve_timezone(name: str) -> ZoneInfo:
    """
    Resolve an IANA timezone name.

    Raises rather than falling back to a fixed offset: a fixed offset silently
    produces times that are an hour wrong for half the year under DST, and
    Google Calendar is then handed a meaningless zone name.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(
            f"Unknown timezone {name!r}. Use an IANA name such as 'Europe/Warsaw'. "
            "On Windows this also requires the 'tzdata' package "
            "(pip install -r requirements.txt)."
        ) from exc


def convert_to_local_timezone(
    scheduled_date: str,
    target_timezone: str = DEFAULT_TIMEZONE
) -> datetime:
    """Convert an API timestamp to the target zone, applying DST as of that date."""
    return parse_api_datetime(scheduled_date).astimezone(resolve_timezone(target_timezone))