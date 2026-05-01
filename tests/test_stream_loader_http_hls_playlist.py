"""Direct tests for the pure HTTP/HLS playlist parsing helper module.

These tests cover the helpers extracted from `stream_loader_http_hls.py`
while keeping the loader-level behavior suites as the primary end-to-end
safety net.
"""

import pytest

from stream_loader_http_hls_playlist import (
    _derive_api_stream_poll_interval,
    _detect_hls_playlist_kind,
    _parse_master_playlist_variants,
    _parse_media_playlist,
)


@pytest.mark.parametrize(
    ("playlist_text", "expected_kind"),
    [
        ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1", "master"),
        ("#EXTM3U\n#EXTINF:1.0,\nsegment.ts", "media"),
        ("not a playlist", "unknown"),
    ],
)
def test_detect_hls_playlist_kind_classifies_known_playlist_shapes(
    playlist_text: str,
    expected_kind: str,
) -> None:
    """Playlist kind detection should stay stable across the supported shapes."""
    assert _detect_hls_playlist_kind(playlist_text) == expected_kind


def test_parse_master_playlist_variants_resolves_relative_entries() -> None:
    """Master playlist parsing should resolve relative variant URLs against the source URL."""
    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-STREAM-INF:BANDWIDTH=1",
            "low/index.m3u8",
            "#EXT-X-STREAM-INF:BANDWIDTH=2",
            "high/index.m3u8",
        ]
    )

    variants = _parse_master_playlist_variants(
        playlist_text,
        "http://example.test/live/master.m3u8",
    )

    assert variants == [
        "http://example.test/live/low/index.m3u8",
        "http://example.test/live/high/index.m3u8",
    ]


def test_parse_media_playlist_handles_sequences_durations_and_endlist() -> None:
    """Media playlist parsing should preserve sequences, durations, and ENDLIST state."""
    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:4",
            "#EXT-X-MEDIA-SEQUENCE:10",
            "#EXTINF:2.5,",
            "segment_010.ts",
            "#EXTINF:1.0,",
            "segment_011.ts",
            "#EXT-X-ENDLIST",
        ]
    )

    snapshot = _parse_media_playlist(playlist_text, "http://example.test/live/index.m3u8")

    assert snapshot.is_endlist is True
    assert snapshot.target_duration_sec == 4.0
    assert [(segment.sequence, segment.uri, segment.duration_sec) for segment in snapshot.segments] == [
        (10, "http://example.test/live/segment_010.ts", 2.5),
        (11, "http://example.test/live/segment_011.ts", 1.0),
    ]


def test_parse_media_playlist_rejects_missing_extm3u_header() -> None:
    """Media playlist parsing should fail closed when the required header is absent."""
    with pytest.raises(ValueError, match="missing EXTM3U"):
        _parse_media_playlist("segment.ts", "http://example.test/live/index.m3u8")

@pytest.mark.parametrize(
    ("configured_poll_interval_sec", "target_duration_sec", "expected"),
    [
        (5.0, None, 5.0),
        (5.0, 2.0, 2.0),
        (-1.0, 2.0, 0.0),
    ],
)
def test_derive_api_stream_poll_interval_respects_target_duration_cap(
    configured_poll_interval_sec: float,
    target_duration_sec: float | None,
    expected: float,
) -> None:
    """The derived poll interval should clamp to the smaller valid interval."""
    assert _derive_api_stream_poll_interval(
        configured_poll_interval_sec=configured_poll_interval_sec,
        target_duration_sec=target_duration_sec,
    ) == expected
