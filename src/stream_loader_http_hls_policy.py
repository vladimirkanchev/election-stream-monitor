"""State-transition helpers for the concrete HTTP/HLS api_stream loader.

Keep this module focused on small policy transformations that operate on
explicit state fragments:

- replay-cache pruning
- pending/emitted queue bookkeeping
- playlist window advance gap detection

The concrete loader shell still owns the overall live-run control flow and the
mutable runtime-state container.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from stream_loader_contracts import ApiStreamPlaylistSegment
from stream_loader_http_hls_playlist import _build_playlist_segment_key


@dataclass(frozen=True)
class _QueuedPlaylistSegmentsResult:
    """Summary of one playlist merge over the currently visible segments."""

    new_segment_count: int
    skipped_replay_count: int
    next_window_start_sec: float


def _prune_emitted_segment_keys(
    emitted_segment_keys: set[tuple[int, str]],
    *,
    first_visible_sequence: int,
) -> set[tuple[int, str]]:
    """Drop replay-cache keys that are older than the current playlist window."""
    return {
        key
        for key in emitted_segment_keys
        if key[0] >= first_visible_sequence
    }


def _calculate_window_advance_gap(
    *,
    last_seen_max_sequence: int | None,
    first_visible_sequence: int,
) -> int | None:
    """Return the count of skipped sequences when the playlist window jumps ahead."""
    if last_seen_max_sequence is None:
        return None
    if first_visible_sequence <= last_seen_max_sequence + 1:
        return None
    return first_visible_sequence - last_seen_max_sequence - 1


def _queue_unseen_playlist_segments(
    *,
    segments: Sequence[ApiStreamPlaylistSegment],
    pending_segments: list[ApiStreamPlaylistSegment],
    queued_segment_keys: set[tuple[int, str]],
    emitted_segment_keys: set[tuple[int, str]],
    segment_start_offsets: dict[tuple[int, str], float],
    next_window_start_sec: float,
) -> _QueuedPlaylistSegmentsResult:
    """Append newly visible segments and return the queue/update counters."""
    new_segment_count = 0
    skipped_replay_count = 0
    updated_window_start_sec = next_window_start_sec

    for segment in segments:
        segment_key = _build_playlist_segment_key(segment)
        if segment_key in queued_segment_keys or segment_key in emitted_segment_keys:
            skipped_replay_count += 1
            continue
        segment_start_offsets[segment_key] = updated_window_start_sec
        updated_window_start_sec += max(segment.duration_sec, 0.1)
        pending_segments.append(segment)
        queued_segment_keys.add(segment_key)
        new_segment_count += 1

    return _QueuedPlaylistSegmentsResult(
        new_segment_count=new_segment_count,
        skipped_replay_count=skipped_replay_count,
        next_window_start_sec=updated_window_start_sec,
    )


def _finalize_pending_segment_state(
    *,
    pending_segments: list[ApiStreamPlaylistSegment],
    queued_segment_keys: set[tuple[int, str]],
    emitted_segment_keys: set[tuple[int, str]],
    segment_start_offsets: dict[tuple[int, str], float],
    segment_key: tuple[int, str],
    mark_emitted: bool,
) -> None:
    """Remove the current pending segment from queue state after one attempt."""
    pending_segments.pop(0)
    queued_segment_keys.discard(segment_key)
    if mark_emitted:
        emitted_segment_keys.add(segment_key)
    segment_start_offsets.pop(segment_key, None)
