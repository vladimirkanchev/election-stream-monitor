"""Utility functions for the buffering-latency proxy server."""

from datetime import datetime, timezone


def parse_timestamp(val: int | float | str | datetime | None) -> str:
    """
    Normalize different timestamp inputs into short UTC string.

    Accepts ISO strings, epoch (s/ms), datetime objects, or None.
    Output format: "YYYY-MM-DD HH:MM:SS"
    """
    if val is None:
        ts = datetime.now(timezone.utc)
    elif isinstance(val, datetime):
        ts = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    elif isinstance(val, (int, float)):
        ts = _from_number(val)
    elif isinstance(val, str):
        ts = _from_string(val)
    else:
        ts = datetime.now(timezone.utc)

    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _from_number(val: int | float) -> datetime:
    """
    Convert numeric epoch to datetime UTC.

    Handles both seconds (10-digit) and milliseconds (13-digit) timestamps.
    Includes tolerance for floats from time.time().
    """
    # If epoch value looks like milliseconds (>= year 2286 in seconds)
    if val > 1e11:  # 100 billion ~ year 5138 in seconds
        val /= 1000.0
    return datetime.fromtimestamp(val, tz=timezone.utc)


def _from_string(val: str) -> datetime:
    """Convert ISO or fallback string to datetime UTC."""
    try:
        ts = datetime.fromisoformat(val)
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return datetime.now(timezone.utc)
