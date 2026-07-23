"""Shared response and bounded-storage-read policy for collection reads."""

from collections.abc import Sequence
from typing import TypeVar


DEFAULT_READ_PAGE_LIMIT = 100
MAX_READ_PAGE_LIMIT = 250
MAX_ALERT_QUERY_ROWS = 5_000
MAX_SESSION_SNAPSHOT_RESPONSE_BYTES = 2 * 1024 * 1024

PageItem = TypeVar("PageItem")


def validate_optional_row_limit(max_rows: int | None) -> None:
    """Validate an internal store-work ceiling shared by persistence backends."""
    if max_rows is None:
        return
    if isinstance(max_rows, bool) or max_rows < 1:
        raise ValueError("max_rows must be a positive integer")


def paginate_read_items(
    items: Sequence[PageItem],
    *,
    limit: int = DEFAULT_READ_PAGE_LIMIT,
    offset: int = 0,
) -> list[PageItem]:
    """Return one stable offset page within the public response bounds."""
    if isinstance(limit, bool) or not 1 <= limit <= MAX_READ_PAGE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_READ_PAGE_LIMIT}")
    if isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    return list(items[offset : offset + limit])
