"""Direct tests for the HTTP/HLS live-run policy helper module.

These cases keep the orchestration shell focused on control flow while
validating the small state-transition helpers directly.
"""

import pytest

from stream_loader_contracts import ApiStreamPlaylistSegment
from stream_loader_http_hls_policy import (
    _calculate_window_advance_gap,
    _finalize_pending_segment_state,
    _prune_emitted_segment_keys,
    _queue_unseen_playlist_segments,
)


def test_prune_emitted_segment_keys_drops_old_window_entries() -> None:
    """Replay-cache pruning should discard segments that fell behind the window."""
    assert _prune_emitted_segment_keys(
        {(1, "old.ts"), (5, "keep.ts")},
        first_visible_sequence=3,
    ) == {(5, "keep.ts")}


@pytest.mark.parametrize(
    ("last_seen_max_sequence", "first_visible_sequence", "expected"),
    [
        (None, 10, None),
        (10, 11, None),
        (10, 14, 3),
    ],
)
def test_calculate_window_advance_gap_detects_skipped_sequences(
    last_seen_max_sequence: int | None,
    first_visible_sequence: int,
    expected: int | None,
) -> None:
    """Window-advance accounting should report only the skipped sequences."""
    assert _calculate_window_advance_gap(
        last_seen_max_sequence=last_seen_max_sequence,
        first_visible_sequence=first_visible_sequence,
    ) == expected


def test_queue_unseen_playlist_segments_skips_replays_and_tracks_window_offsets() -> None:
    """Queueing should append only new segments and advance offsets predictably."""
    pending: list[ApiStreamPlaylistSegment] = []
    queued_keys: set[tuple[int, str]] = set()
    emitted_keys: set[tuple[int, str]] = {(1, "segment_001.ts")}
    offsets: dict[tuple[int, str], float] = {}
    segments = [
        ApiStreamPlaylistSegment(1, "http://example.test/segment_001.ts", 1.0),
        ApiStreamPlaylistSegment(2, "http://example.test/segment_002.ts", 2.0),
    ]

    result = _queue_unseen_playlist_segments(
        segments=segments,
        pending_segments=pending,
        queued_segment_keys=queued_keys,
        emitted_segment_keys=emitted_keys,
        segment_start_offsets=offsets,
        next_window_start_sec=0.0,
    )

    assert result.new_segment_count == 1
    assert result.skipped_replay_count == 1
    assert result.next_window_start_sec == 2.0
    assert [segment.sequence for segment in pending] == [2]
    assert offsets[(2, "segment_002.ts")] == 0.0


def test_finalize_pending_segment_state_updates_all_queues() -> None:
    """Finalizing a pending segment should clear queue state and mark emission."""
    segment = ApiStreamPlaylistSegment(7, "http://example.test/segment_007.ts", 1.0)
    pending = [segment]
    queued_keys = {(7, "segment_007.ts")}
    emitted_keys: set[tuple[int, str]] = set()
    offsets = {(7, "segment_007.ts"): 12.0}

    _finalize_pending_segment_state(
        pending_segments=pending,
        queued_segment_keys=queued_keys,
        emitted_segment_keys=emitted_keys,
        segment_start_offsets=offsets,
        segment_key=(7, "segment_007.ts"),
        mark_emitted=True,
    )

    assert pending == []
    assert queued_keys == set()
    assert emitted_keys == {(7, "segment_007.ts")}
    assert offsets == {}


def test_finalize_pending_segment_state_can_skip_emitted_marking() -> None:
    """Finalizing a pending segment should also support non-emitted cleanup paths."""
    segment = ApiStreamPlaylistSegment(9, "http://example.test/segment_009.ts", 1.0)
    pending = [segment]
    queued_keys = {(9, "segment_009.ts")}
    emitted_keys: set[tuple[int, str]] = set()
    offsets = {(9, "segment_009.ts"): 18.0}

    _finalize_pending_segment_state(
        pending_segments=pending,
        queued_segment_keys=queued_keys,
        emitted_segment_keys=emitted_keys,
        segment_start_offsets=offsets,
        segment_key=(9, "segment_009.ts"),
        mark_emitted=False,
    )

    assert pending == []
    assert queued_keys == set()
    assert emitted_keys == set()
    assert offsets == {}
