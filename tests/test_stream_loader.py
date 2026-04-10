"""Tests for the explicit `api_stream` loader seam and source contracts."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

import config
from analyzer_contract import AnalysisSlice
from session_io import read_api_stream_seen_chunk_keys, request_session_cancel
import stream_loader
from stream_loader import (
    ApiStreamDedupPolicy,
    ApiStreamFailureSemantics,
    ApiStreamHttpLoaderContract,
    ApiStreamLoaderExceptionPolicy,
    ApiStreamLocalHttpTestHarnessContract,
    ApiStreamProgressSemantics,
    ApiStreamSourceContract,
    ApiStreamTempFilePolicy,
    FakeApiStreamEvent,
    FakeApiStreamLoader,
    HttpHlsApiStreamLoader,
    PlaceholderApiStreamLoader,
    StaticApiStreamLoader,
    build_api_stream_dedup_policy,
    collect_api_stream_slices,
    build_api_stream_analysis_slice,
    build_api_stream_chunk_identity,
    build_api_stream_failure_semantics,
    build_api_stream_http_loader_contract,
    build_api_stream_loader_exception_policy,
    build_api_stream_local_http_test_harness_contract,
    build_api_stream_playback_contract,
    build_api_stream_progress_semantics,
    build_api_stream_runtime_policy,
    build_api_stream_slice_identity_key,
    build_api_stream_source_contract,
    build_api_stream_source_group,
    build_api_stream_start_session_contract,
    build_api_stream_temp_file_policy,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    iter_api_stream_slices,
    select_api_stream_master_playlist_variant,
    validate_api_stream_chunk_sequence,
)


def test_build_api_stream_runtime_policy_reflects_current_config() -> None:
    """The runtime policy helper should expose the current validation/fetch limits."""
    policy = build_api_stream_runtime_policy()

    assert "http" in policy.allowed_schemes
    assert "https" in policy.allowed_schemes
    assert policy.max_reconnect_attempts >= 1
    assert policy.fetch_timeout_sec > 0
    assert policy.max_fetch_bytes > 0
    assert policy.max_session_runtime_sec > 0
    assert policy.max_playlist_refreshes >= 1


@pytest.mark.parametrize(
    ("builder", "expected_type", "expected_fields"),
    [
        (
            build_api_stream_http_loader_contract,
            ApiStreamHttpLoaderContract,
            {
                "accepted_playlist_types": ("media", "master"),
                "master_playlist_policy": "first_variant",
                "playlist_poll_interval_sec": 2.0,
            },
        ),
        (
            build_api_stream_local_http_test_harness_contract,
            ApiStreamLocalHttpTestHarnessContract,
            {
                "server_kind": "local_http",
                "fixture_format": "hls",
                "playlist_entrypoint": "index.m3u8",
            },
        ),
        (
            build_api_stream_dedup_policy,
            ApiStreamDedupPolicy,
            {
                "storage_scope": "loader_and_session",
                "persisted_session_side": True,
                "replayed_chunk_behavior": "skip_before_persistence",
            },
        ),
        (
            build_api_stream_loader_exception_policy,
            ApiStreamLoaderExceptionPolicy,
            {
                "skip_inside_loader_failure_kinds": (
                    "temporary_failure",
                    "retryable_failure",
                ),
                "reconnect_owner": "loader",
            },
        ),
        (
            build_api_stream_progress_semantics,
            ApiStreamProgressSemantics,
            {
                "running_total_count_mode": "latest_known",
                "allow_null_total_count": False,
                "frontend_progress_mode": "live_non_terminal",
            },
        ),
    ],
)
def test_api_stream_contract_builders_keep_stable_core_fields(
    builder,
    expected_type,
    expected_fields: dict[str, object],
) -> None:
    """Small builder helpers should keep the core contract fields that other code depends on."""
    contract = builder()

    assert isinstance(contract, expected_type)
    for field_name, expected_value in expected_fields.items():
        assert getattr(contract, field_name) == expected_value


def test_build_api_stream_temp_file_policy_uses_session_scoped_cleanup_defaults() -> None:
    """Future live temp files should keep one explicit root, budget, and cleanup policy."""
    policy = build_api_stream_temp_file_policy()

    assert isinstance(policy, ApiStreamTempFilePolicy)
    assert policy.session_scoped is True
    assert policy.cleanup_on_completed is True
    assert policy.cleanup_on_cancelled is True
    assert policy.cleanup_on_failed is True
    assert policy.max_bytes == 500_000_000
    assert "api_stream" in str(policy.temp_root)


def test_build_api_stream_temp_session_dir_is_session_scoped() -> None:
    """Each live session should get one dedicated temp directory under the shared root."""
    session_dir = build_api_stream_temp_session_dir("session-123")

    assert session_dir.name == "session-123"
    assert session_dir.parent == build_api_stream_temp_file_policy().temp_root


def test_select_api_stream_master_playlist_variant_uses_first_variant_policy() -> None:
    """Master-playlist selection should stay deterministic for the first real loader."""
    selected = select_api_stream_master_playlist_variant(
        [
            "https://example.com/live/variant-low.m3u8",
            "https://example.com/live/variant-high.m3u8",
        ]
    )

    assert selected == "https://example.com/live/variant-low.m3u8"


def test_build_api_stream_failure_semantics_matches_current_live_contract() -> None:
    """The live-failure helper should name status and reconnect expectations."""
    semantics = build_api_stream_failure_semantics()
    reconnect_budget = build_api_stream_runtime_policy().max_reconnect_attempts

    assert isinstance(semantics, ApiStreamFailureSemantics)
    assert semantics.temporary_status == "running"
    assert semantics.retryable_status == "running"
    assert semantics.terminal_status == "failed"
    assert semantics.duplicate_results_allowed is False
    assert semantics.duplicate_alerts_allowed is False
    assert semantics.max_reconnect_attempts == reconnect_budget


def test_api_stream_source_related_builders_share_validated_remote_identity() -> None:
    """Source, start-session, and playback builders should preserve one validated remote identity."""
    input_path = "https://example.com/live/playlist.m3u8"
    source_contract = build_api_stream_source_contract(input_path)
    start_contract = build_api_stream_start_session_contract(
        input_path=input_path,
        selected_detectors=["video_blur", "video_metrics"],
    )
    playback_contract = build_api_stream_playback_contract(input_path)

    assert source_contract == ApiStreamSourceContract(
        kind="api_stream",
        input_path=input_path,
        access="api_stream",
    )
    assert start_contract.mode == "api_stream"
    assert start_contract.input_path == input_path
    assert start_contract.selected_detectors == ["video_blur", "video_metrics"]
    assert playback_contract.source == input_path
    assert build_api_stream_source_group(source_contract) == input_path


def test_build_api_stream_chunk_identity_uses_readable_default_current_item() -> None:
    """Live chunks should have deterministic readable item names even without upstream names."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")

    identity = build_api_stream_chunk_identity(source=source, chunk_index=7)

    assert identity.source_group == source.input_path
    assert identity.chunk_index == 7
    assert identity.current_item == "live-chunk-000007"


def test_build_api_stream_analysis_slice_uses_chunk_identity(tmp_path: Path) -> None:
    """Live slices should carry stable source-group and monotonic chunk identity."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    file_path = tmp_path / "live-window-007.ts"
    file_path.write_bytes(b"ts")

    slice_ = build_api_stream_analysis_slice(
        source=source,
        file_path=file_path,
        chunk_index=7,
        current_item="playlist-window-007.ts",
        window_start_sec=7.0,
        window_duration_sec=1.0,
    )

    assert slice_.source_group == source.input_path
    assert slice_.source_name == "playlist-window-007.ts"
    assert slice_.window_index == 7
    assert slice_.window_start_sec == 7.0
    assert slice_.window_duration_sec == 1.0


def test_validate_api_stream_chunk_sequence_accepts_stable_monotonic_flow(tmp_path: Path) -> None:
    """Chunk-sequence validation should allow stable source-group + increasing index."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    first_path = tmp_path / "live-001.ts"
    second_path = tmp_path / "live-002.ts"
    first_path.write_bytes(b"ts")
    second_path.write_bytes(b"ts")
    first = build_api_stream_analysis_slice(source=source, file_path=first_path, chunk_index=1)
    second = build_api_stream_analysis_slice(source=source, file_path=second_path, chunk_index=2)

    validate_api_stream_chunk_sequence(first, second)


def test_validate_api_stream_chunk_sequence_rejects_duplicate_or_replayed_index(
    tmp_path: Path,
) -> None:
    """Reconnect-safe identity should reject duplicate or replayed chunk indexes."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    first_path = tmp_path / "live-001.ts"
    replay_path = tmp_path / "live-001-replay.ts"
    first_path.write_bytes(b"ts")
    replay_path.write_bytes(b"ts")
    first = build_api_stream_analysis_slice(source=source, file_path=first_path, chunk_index=1)
    replay = build_api_stream_analysis_slice(source=source, file_path=replay_path, chunk_index=1)

    with pytest.raises(ValueError, match="increase monotonically"):
        validate_api_stream_chunk_sequence(first, replay)


def test_build_api_stream_slice_identity_key_supports_reconnect_dedup(tmp_path: Path) -> None:
    """Live slices should expose one de-duplication key for reconnect-safe persistence."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    file_path = tmp_path / "live-002.ts"
    file_path.write_bytes(b"ts")
    slice_ = build_api_stream_analysis_slice(
        source=source,
        file_path=file_path,
        chunk_index=2,
        current_item="live-window-002.ts",
    )

    assert build_api_stream_slice_identity_key(slice_) == (
        "https://example.com/live/playlist.m3u8",
        2,
        "live-window-002.ts",
    )


def test_fake_loader_collects_clean_live_flow(tmp_path: Path) -> None:
    """The fake loader should model a clean bounded live stream."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=2, current_item="live-002.ts"),
        ]
    )

    slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == [
        "live-000.ts",
        "live-001.ts",
        "live-002.ts",
    ]
    assert [slice_.window_index for slice_ in slices] == [0, 1, 2]


def test_fake_loader_skips_temporary_outage_and_keeps_live_progress() -> None:
    """Temporary failures should be skipped without changing the session model."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(
                kind="temporary_failure",
                chunk_index=1,
                current_item="live-001.ts",
                message="chunk fetch timeout",
            ),
            FakeApiStreamEvent(kind="chunk", chunk_index=2, current_item="live-002.ts"),
        ]
    )

    slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["live-000.ts", "live-002.ts"]


def test_fake_loader_skips_duplicate_chunk_replayed_after_reconnect() -> None:
    """Duplicate chunk identities should not reach persistence after reconnect replay."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=2, current_item="live-002.ts"),
        ]
    )

    slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [0, 1, 2]


def test_fake_loader_skips_malformed_chunk_identity() -> None:
    """Malformed chunks should be dropped before they can affect results or alerts."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(kind="malformed_chunk", chunk_index=2, current_item="bad.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
        ]
    )

    slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["live-000.ts", "live-001.ts"]
    assert [slice_.window_index for slice_ in slices] == [0, 1]


def test_fake_loader_raises_on_terminal_stop() -> None:
    """Terminal failures should stop collection so the session can fail explicitly."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(kind="terminal_failure", message="playlist permanently unavailable"),
        ]
    )

    with pytest.raises(ValueError, match="playlist permanently unavailable"):
        collect_api_stream_slices(loader, source)


def test_fake_loader_exhausts_retry_budget_for_retryable_failures() -> None:
    """Retryable failures should consume reconnect budget before becoming terminal."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    semantics = build_api_stream_failure_semantics()
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(
                kind="retryable_failure",
                message=f"retry-{index}",
            )
            for index in range(semantics.max_reconnect_attempts + 1)
        ]
    )

    with pytest.raises(ValueError, match="reconnect budget exhausted"):
        collect_api_stream_slices(loader, source)


def test_collect_api_stream_slices_logs_failures_and_accepted_chunks(
    monkeypatch,
) -> None:
    """The loader seam should emit useful logs before full live loading exists."""
    info_logs: list[tuple[str, tuple[object, ...]]] = []
    warning_logs: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(
        stream_loader.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )
    monkeypatch.setattr(
        stream_loader.logger,
        "warning",
        lambda message, *args: warning_logs.append((message, args)),
    )

    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(kind="chunk", chunk_index=0, current_item="live-000.ts"),
            FakeApiStreamEvent(
                kind="temporary_failure",
                chunk_index=1,
                current_item="live-001.ts",
                message="temporary fetch timeout",
            ),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
            FakeApiStreamEvent(kind="chunk", chunk_index=1, current_item="live-001.ts"),
        ]
    )

    slices = collect_api_stream_slices(loader, source)

    assert len(slices) == 2
    assert info_logs
    assert info_logs[0][0] == "Collecting api_stream slices [%s]"
    assert "source_url='https://example.com/<redacted>'" in str(info_logs[0][1][0])
    assert any(message == "Accepted api_stream slice [%s]" for message, _ in info_logs[1:])
    assert any("processed_chunk_count=1" in str(args[0]) for message, args in info_logs if message == "Accepted api_stream slice [%s]")
    assert any(message == "Skipping temporary api_stream failure [%s]" for message, _ in warning_logs)
    assert any(message == "Skipping invalid api_stream slice [%s]" for message, _ in warning_logs)


def test_build_api_stream_temp_session_dir_rejects_blank_session_ids() -> None:
    """Temp-dir creation should reject blank session identities early."""
    with pytest.raises(ValueError, match="non-empty session_id"):
        build_api_stream_temp_session_dir("   ")


def test_select_api_stream_master_playlist_variant_rejects_empty_variant_lists() -> None:
    """The master-playlist policy helper should fail clearly on empty input."""
    with pytest.raises(ValueError, match="at least one variant URL"):
        select_api_stream_master_playlist_variant([])


def test_placeholder_loader_yields_no_slices_until_real_loading_exists() -> None:
    """The default placeholder should keep the seam explicit without fake ingestion."""
    loader = PlaceholderApiStreamLoader()
    loader.connect(build_api_stream_source_contract("https://example.com/live/playlist.m3u8"))

    assert list(loader.iter_slices()) == []

    loader.close()


def test_static_loader_yields_supplied_slices_after_connect(tmp_path: Path) -> None:
    """The static test loader should provide deterministic fake live slices."""
    slice_file = tmp_path / "live-window-001.ts"
    slice_file.write_bytes(b"ts")
    expected_slices = [
        AnalysisSlice(
            file_path=slice_file,
            source_group="stream-a",
            source_name="live-window-001.ts",
            window_index=0,
        )
    ]
    loader = StaticApiStreamLoader(expected_slices)

    loader.connect(build_api_stream_source_contract("https://example.com/live/playlist.m3u8"))

    assert list(loader.iter_slices()) == expected_slices

    loader.close()


def test_static_loader_requires_connect_before_iteration(tmp_path: Path) -> None:
    """The fake loader should behave like a real loader and require connect first."""
    slice_file = tmp_path / "live-window-001.ts"
    slice_file.write_bytes(b"ts")
    loader = StaticApiStreamLoader(
        [
            AnalysisSlice(
                file_path=slice_file,
                source_group="stream-a",
                source_name="live-window-001.ts",
                window_index=0,
            )
        ]
    )

    with pytest.raises(RuntimeError, match="before connect"):
        list(loader.iter_slices())


def test_http_hls_loader_collects_media_playlist_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The concrete loader should fetch a media playlist and materialize segment slices."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"ts-000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"ts-001", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-media")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts", "segment_001.ts"]
    assert [slice_.window_index for slice_ in slices] == [0, 1]
    assert all(slice_.file_path.exists() for slice_ in slices)
    cleanup_api_stream_temp_session_dir("session-http-media")


def test_http_hls_loader_selects_first_master_playlist_variant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The first real loader should apply the explicit first-variant master-playlist policy."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    master_text = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
            "low/index.m3u8",
            '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
            "high/index.m3u8",
        ]
    )
    media_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:10",
            "#EXTINF:1.0,",
            "segment_low_010.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/low/index.m3u8": (200, media_text, "application/vnd.apple.mpegurl"),
        "/high/index.m3u8": (
            200,
            media_text.replace("segment_low_010.ts", "segment_high_010.ts"),
            "application/vnd.apple.mpegurl",
        ),
        "/low/segment_low_010.ts": (200, b"low", "video/mp2t"),
        "/high/segment_high_010.ts": (200, b"high", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_low_010.ts"]
    assert [slice_.window_index for slice_ in slices] == [10]
    cleanup_api_stream_temp_session_dir("session-http-master")


def test_http_hls_loader_uses_first_master_variant_even_when_it_is_weak_but_playable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """First-variant selection should remain predictable even for a low-quality playable stream."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    master_text = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=180000,RESOLUTION=320x180',
            "weak/index.m3u8",
            '#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1920x1080',
            "strong/index.m3u8",
        ]
    )
    weak_media = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:2",
            "#EXT-X-MEDIA-SEQUENCE:20",
            "#EXTINF:2.0,",
            "segment_weak_020.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    strong_media = weak_media.replace("segment_weak_020.ts", "segment_strong_020.ts")
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/weak/index.m3u8": (200, weak_media, "application/vnd.apple.mpegurl"),
        "/strong/index.m3u8": (200, strong_media, "application/vnd.apple.mpegurl"),
        "/weak/segment_weak_020.ts": (200, b"weak", "video/mp2t"),
        "/strong/segment_strong_020.ts": (200, b"strong", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master-weak-first")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_weak_020.ts"]
    cleanup_api_stream_temp_session_dir("session-http-master-weak-first")


def test_http_hls_loader_resolves_nested_master_playlist_variants(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Nested master playlists should still resolve to a reachable media playlist."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    outer_master = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
            "variant/master.m3u8",
        ]
    )
    inner_master = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=750000,RESOLUTION=960x540',
            "media/index.m3u8",
        ]
    )
    media_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:12",
            "#EXTINF:1.0,",
            "segment_012.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/master.m3u8": (200, outer_master, "application/vnd.apple.mpegurl"),
        "/variant/master.m3u8": (200, inner_master, "application/vnd.apple.mpegurl"),
        "/variant/media/index.m3u8": (200, media_playlist, "application/vnd.apple.mpegurl"),
        "/variant/media/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-nested-master")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [12]
    cleanup_api_stream_temp_session_dir("session-http-nested-master")


def test_http_hls_loader_ignores_malformed_master_variant_entries_and_uses_first_valid_one(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed master entry without a URI should not prevent using the next valid variant."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    master_text = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
            "# malformed first variant entry has no URI",
            '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=960x540',
            "valid/index.m3u8",
        ]
    )
    media_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:15",
            "#EXTINF:1.0,",
            "segment_valid_015.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/valid/index.m3u8": (200, media_text, "application/vnd.apple.mpegurl"),
        "/valid/segment_valid_015.ts": (200, b"015", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master-malformed-entry")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [15]
    assert [slice_.source_name for slice_ in slices] == ["segment_valid_015.ts"]
    cleanup_api_stream_temp_session_dir("session-http-master-malformed-entry")


def test_http_hls_loader_polls_playlist_and_emits_only_new_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Playlist refresh should discover only new segments on later polls."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:3",
            "#EXTINF:1.0,",
            "segment_003.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:3",
            "#EXTINF:1.0,",
            "segment_003.ts",
            "#EXTINF:1.0,",
            "segment_004.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_003.ts": (200, b"003", "video/mp2t"),
        "/live/segment_004.ts": (200, b"004", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [3, 4]
    assert [slice_.source_name for slice_ in slices] == ["segment_003.ts", "segment_004.ts"]
    cleanup_api_stream_temp_session_dir("session-http-refresh")


def test_http_hls_loader_handles_sliding_window_playlist_histories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Sliding HLS windows should allow old segments to disappear without duplicating survivors."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:10",
            "#EXTINF:1.0,",
            "segment_010.ts",
            "#EXTINF:1.0,",
            "segment_011.ts",
            "#EXTINF:1.0,",
            "segment_012.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:12",
            "#EXTINF:1.0,",
            "segment_012.ts",
            "#EXTINF:1.0,",
            "segment_013.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
        "/live/segment_011.ts": (200, b"011", "video/mp2t"),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
        "/live/segment_013.ts": (200, b"013", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-sliding")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [10, 11, 12, 13]
    assert [slice_.source_name for slice_ in slices] == [
        "segment_010.ts",
        "segment_011.ts",
        "segment_012.ts",
        "segment_013.ts",
    ]
    cleanup_api_stream_temp_session_dir("session-http-sliding")


def test_http_hls_loader_handles_longer_sliding_runs_without_replay_cache_growth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Longer HLS runs should keep replay tracking bounded to the visible window."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    playlist_specs = [
        (300, 301, False),
        (301, 302, False),
        (302, 303, False),
        (303, 304, False),
        (304, 305, False),
        (305, 306, False),
        (306, 307, True),
    ]
    playlists = []
    for first_index, second_index, is_endlist in playlist_specs:
        lines = [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            f"#EXT-X-MEDIA-SEQUENCE:{first_index}",
            "#EXTINF:1.0,",
            f"segment_{first_index}.ts",
            "#EXTINF:1.0,",
            f"segment_{second_index}.ts",
        ]
        if is_endlist:
            lines.append("#EXT-X-ENDLIST")
        playlists.append("\n".join(lines))

    routes: dict[str, object] = {
        "/live/index.m3u8": [
            (200, playlist_text, "application/vnd.apple.mpegurl")
            for playlist_text in playlists
        ],
    }
    for index in range(300, 308):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-long-run")
        loader.connect(source)
        try:
            slices = list(loader.iter_slices())
            assert [slice_.window_index for slice_ in slices] == list(range(300, 308))
            assert loader._emitted_segment_keys == {
                (306, "segment_306.ts"),
                (307, "segment_307.ts"),
            }
        finally:
            loader.close()

    cleanup_api_stream_temp_session_dir("session-http-long-run")


def test_http_hls_loader_resumes_after_window_advance_when_missed_segments_are_gone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When the live window advances past missed segments, the loader should resume from the next visible segment."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:40",
            "#EXTINF:1.0,",
            "segment_040.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:43",
            "#EXTINF:1.0,",
            "segment_043.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_040.ts": (200, b"040", "video/mp2t"),
        "/live/segment_043.ts": (200, b"043", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-window-advance")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [40, 43]
    assert [slice_.source_name for slice_ in slices] == ["segment_040.ts", "segment_043.ts"]
    cleanup_api_stream_temp_session_dir("session-http-window-advance")


def test_http_hls_loader_tolerates_incomplete_refresh_and_keeps_progressing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A dangling EXTINF without a URI should be ignored as an incomplete live refresh."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "segment_060.ts",
        ]
    )
    incomplete_refresh = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
        ]
    )
    final_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "segment_060.ts",
            "#EXTINF:1.0,",
            "segment_061.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, incomplete_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_060.ts": (200, b"060", "video/mp2t"),
        "/live/segment_061.ts": (200, b"061", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-incomplete-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [60, 61]
    cleanup_api_stream_temp_session_dir("session-http-incomplete-refresh")


def test_http_hls_loader_tolerates_media_playlist_missing_target_duration_tag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A media playlist missing TARGETDURATION should still progress when EXTINF entries are present."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-MEDIA-SEQUENCE:62",
            "#EXTINF:1.0,",
            "segment_062.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_062.ts": (200, b"062", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-missing-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [62]
    cleanup_api_stream_temp_session_dir("session-http-missing-target-duration")


def test_http_hls_loader_stops_after_repeated_no_new_live_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Non-endlist live playlists should stop cleanly after a bounded idle poll budget."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 2)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:21",
            "#EXTINF:1.0,",
            "segment_021.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_021.ts": (200, b"021", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-idle")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [21]
    assert len(sleep_calls) == 2
    cleanup_api_stream_temp_session_dir("session-http-idle")


def test_http_hls_loader_stops_immediately_after_endlist_segments_are_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ENDLIST should stop the live loop without falling back to idle polling."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:80",
            "#EXTINF:1.0,",
            "segment_080.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_080.ts": (200, b"080", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-endlist-stop")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [80]
    assert sleep_calls == []
    cleanup_api_stream_temp_session_dir("session-http-endlist-stop")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_idle_polling(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during idle polling should stop the live loop without hanging."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []

    def cancel_on_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        request_session_cancel("session-http-cancel-idle")

    monkeypatch.setattr(stream_loader.time, "sleep", cancel_on_sleep)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:81",
            "#EXTINF:1.0,",
            "segment_081.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_081.ts": (200, b"081", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-idle")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [81]
    assert len(sleep_calls) == 1
    cleanup_api_stream_temp_session_dir("session-http-cancel-idle")


def test_http_hls_loader_prunes_replay_cache_when_playlist_window_slides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Older replay keys should not grow forever once the visible playlist window advances."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:10",
            "#EXTINF:1.0,",
            "segment_010.ts",
            "#EXTINF:1.0,",
            "segment_011.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:12",
            "#EXTINF:1.0,",
            "segment_012.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
        "/live/segment_011.ts": (200, b"011", "video/mp2t"),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cache-prune")
        loader.connect(source)
        iterator = loader.iter_slices()

        first = next(iterator)
        second = next(iterator)
        third = next(iterator)

        assert [first.window_index, second.window_index, third.window_index] == [10, 11, 12]
        assert (10, "segment_010.ts") not in loader._emitted_segment_keys
        assert (11, "segment_011.ts") not in loader._emitted_segment_keys
        assert (12, "segment_012.ts") in loader._emitted_segment_keys
        loader.close()

    cleanup_api_stream_temp_session_dir("session-http-cache-prune")


def test_http_hls_loader_adapts_polling_to_target_duration_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Target-duration drift should change the next live refresh wait without breaking loading."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 2.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 3)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:4",
            "#EXT-X-MEDIA-SEQUENCE:30",
            "#EXTINF:4.0,",
            "segment_030.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:30",
            "#EXTINF:4.0,",
            "segment_030.ts",
        ]
    )
    third_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:30",
            "#EXTINF:4.0,",
            "segment_030.ts",
            "#EXTINF:1.0,",
            "segment_031.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
            (200, third_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_030.ts": (200, b"030", "video/mp2t"),
        "/live/segment_031.ts": (200, b"031", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-drift")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [30, 31]
    assert sleep_calls == [2.0, 1.0]
    cleanup_api_stream_temp_session_dir("session-http-drift")


def test_http_hls_loader_treats_temporarily_malformed_refresh_as_retryable_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed 200 OK refresh should be skipped so later valid media can still continue."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)
    warning_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
        "warning",
        lambda message, *args: warning_logs.append((message, args)),
    )

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:90",
            "#EXTINF:1.0,",
            "segment_090.ts",
        ]
    )
    final_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:90",
            "#EXTINF:1.0,",
            "segment_090.ts",
            "#EXTINF:1.0,",
            "segment_091.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, "temporary html error", "text/plain"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_090.ts": (200, b"090", "video/mp2t"),
        "/live/segment_091.ts": (200, b"091", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [90, 91]
    assert any(message == "Retryable api_stream failure [%s]" for message, _ in warning_logs)
    assert any(
        "session_id='session-http-malformed-refresh'" in str(args[0])
        and "reconnect_attempt=1" in str(args[0])
        for message, args in warning_logs
        if message == "Retryable api_stream failure [%s]"
    )
    cleanup_api_stream_temp_session_dir("session-http-malformed-refresh")


def test_http_hls_loader_treats_invalid_target_duration_tag_as_retryable_refresh_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A refresh with a malformed TARGETDURATION tag should be skipped until a valid playlist appears."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:92",
            "#EXTINF:1.0,",
            "segment_092.ts",
        ]
    )
    malformed_refresh = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:not-a-number",
            "#EXT-X-MEDIA-SEQUENCE:92",
            "#EXTINF:1.0,",
            "segment_092.ts",
        ]
    )
    final_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:92",
            "#EXTINF:1.0,",
            "segment_092.ts",
            "#EXTINF:1.0,",
            "segment_093.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, malformed_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_092.ts": (200, b"092", "video/mp2t"),
        "/live/segment_093.ts": (200, b"093", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [92, 93]
    cleanup_api_stream_temp_session_dir("session-http-malformed-target-duration")


def test_http_hls_loader_recovers_from_partial_refresh_missing_segment_uri(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A partial refresh with a dangling EXTINF should recover once the next valid playlist arrives."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:94",
            "#EXTINF:1.0,",
            "segment_094.ts",
        ]
    )
    partial_refresh = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:94",
            "#EXTINF:1.0,",
            "segment_094.ts",
            "#EXTINF:1.0,",
        ]
    )
    final_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:94",
            "#EXTINF:1.0,",
            "segment_094.ts",
            "#EXTINF:1.0,",
            "segment_095.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, partial_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_094.ts": (200, b"094", "video/mp2t"),
        "/live/segment_095.ts": (200, b"095", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-partial-refresh-recovery")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [94, 95]
    cleanup_api_stream_temp_session_dir("session-http-partial-refresh-recovery")


def test_http_hls_loader_continues_when_missing_segment_disappears_from_later_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A missing segment that falls out of the live window should not block later visible segments."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:400",
            "#EXTINF:1.0,",
            "segment_400.ts",
            "#EXTINF:1.0,",
            "segment_401.ts",
        ]
    )
    advanced_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:402",
            "#EXTINF:1.0,",
            "segment_402.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, advanced_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_400.ts": (200, b"400", "video/mp2t"),
        "/live/segment_401.ts": (503, "busy", "text/plain"),
        "/live/segment_402.ts": (200, b"402", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-disappearing-segment")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [400, 402]
    cleanup_api_stream_temp_session_dir("session-http-disappearing-segment")


def test_http_hls_loader_accepts_uppercase_playlist_and_segment_suffixes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Uppercase playlist paths and segment suffixes should still load cleanly."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:210",
            "#EXTINF:1.0,",
            "SEGMENT_210.TS",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/LIVE/INDEX.M3U8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/LIVE/SEGMENT_210.TS": (200, b"210", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/LIVE/INDEX.M3U8")
        loader = HttpHlsApiStreamLoader("session-http-uppercase-suffixes")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["SEGMENT_210.TS"]
    assert [slice_.window_index for slice_ in slices] == [210]
    cleanup_api_stream_temp_session_dir("session-http-uppercase-suffixes")


def test_http_hls_loader_retries_playlist_fetch_before_succeeding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Retryable playlist failures should be retried inside the loader seam."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (503, "upstream busy", "text/plain"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_000.ts": (200, b"ok", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts"]
    cleanup_api_stream_temp_session_dir("session-http-retry")


def test_http_hls_loader_retries_playlist_fetch_after_http_429(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 429 responses should be treated like retryable provider throttling."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (429, "slow down", "text/plain"),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                        "#EXT-X-ENDLIST",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
        "/live/segment_000.ts": (200, b"ok", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry-429")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts"]
    assert loader.telemetry_snapshot().reconnect_attempt_count == 1
    cleanup_api_stream_temp_session_dir("session-http-retry-429")


def test_http_hls_loader_surfaces_http_403_as_explicit_terminal_provider_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 403 stays terminal today and should surface a clear provider-facing reason."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    routes = {
        "/live/index.m3u8": [
            (403, "forbidden", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-403")
        with pytest.raises(ValueError, match="HTTP 403"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream upstream returned HTTP 403"
    cleanup_api_stream_temp_session_dir("session-http-403")


def test_http_hls_loader_follows_playlist_redirects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Provider-style playlist redirects should resolve before normal polling begins."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    routes = {
        "/entry.m3u8": (302, "", "text/plain", {"Location": "/live/index.m3u8"}),
        "/live/index.m3u8": (
            200,
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-TARGETDURATION:1",
                    "#EXT-X-MEDIA-SEQUENCE:10",
                    "#EXTINF:1.0,",
                    "segment_010.ts",
                    "#EXT-X-ENDLIST",
                ]
            ),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/entry.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-redirect")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [10]
    cleanup_api_stream_temp_session_dir("session-http-redirect")


def test_http_hls_loader_tolerates_playlist_with_odd_content_type(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Some providers serve playlists with generic content types; parsing should stay text-based."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    routes = {
        "/live/index.m3u8": (
            200,
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-TARGETDURATION:1",
                    "#EXT-X-MEDIA-SEQUENCE:12",
                    "#EXTINF:1.0,",
                    "segment_012.ts",
                    "#EXT-X-ENDLIST",
                ]
            ),
            "text/plain",
        ),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-odd-content-type")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [12]
    cleanup_api_stream_temp_session_dir("session-http-odd-content-type")


def test_http_hls_loader_enforces_playlist_refresh_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded refresh budget should stop unbounded provider churn explicitly."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_PLAYLIST_REFRESHES", 1)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 10)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-refresh-limit")
        with pytest.raises(ValueError, match="playlist refresh limit exceeded"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream playlist refresh limit exceeded"
    cleanup_api_stream_temp_session_dir("session-http-refresh-limit")


def test_http_hls_loader_enforces_session_runtime_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded runtime should fail explicitly instead of polling forever."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 10)
    monkeypatch.setattr(config, "API_STREAM_MAX_SESSION_RUNTIME_SEC", 5.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    ticks = iter([0.0, 6.0, 6.0, 6.0])
    monkeypatch.setattr(stream_loader.time, "monotonic", lambda: next(ticks))

    routes = {
        "/live/index.m3u8": (
            200,
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-TARGETDURATION:1",
                    "#EXT-X-MEDIA-SEQUENCE:0",
                    "#EXTINF:1.0,",
                    "segment_000.ts",
                ]
            ),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-runtime-limit")
        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream session runtime exceeded max duration"
    cleanup_api_stream_temp_session_dir("session-http-runtime-limit")


def test_http_hls_loader_keeps_session_temp_dirs_isolated_under_concurrent_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Concurrent live runs should keep temp materialization isolated per session."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")

        def run_loader(session_id: str) -> tuple[list[AnalysisSlice], Path]:
            loader = HttpHlsApiStreamLoader(session_id)
            slices = collect_api_stream_slices(loader, source)
            return slices, build_api_stream_temp_session_dir(session_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_slices, first_dir = pool.submit(run_loader, "session-http-concurrent-a").result()
            second_slices, second_dir = pool.submit(run_loader, "session-http-concurrent-b").result()

    assert first_dir != second_dir
    assert all(first_dir in slice_.file_path.parents for slice_ in first_slices)
    assert all(second_dir in slice_.file_path.parents for slice_ in second_slices)
    cleanup_api_stream_temp_session_dir("session-http-concurrent-a")
    cleanup_api_stream_temp_session_dir("session-http-concurrent-b")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_segment_download(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during segment download should stop before temp media is written."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:82",
            "#EXTINF:1.0,",
            "segment_082.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_082.ts": (200, b"082", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-download")

        original_fetch = loader._fetch_segment_bytes

        def cancelling_fetch(url: str, segment_name: str) -> bytes:
            request_session_cancel("session-http-cancel-download")
            return original_fetch(url, segment_name)

        monkeypatch.setattr(loader, "_fetch_segment_bytes", cancelling_fetch)
        slices = collect_api_stream_slices(loader, source)

        temp_dir = build_api_stream_temp_session_dir("session-http-cancel-download")

    assert slices == []
    assert not any(temp_dir.iterdir())
    cleanup_api_stream_temp_session_dir("session-http-cancel-download")


def test_http_hls_loader_resumes_after_outage_when_playlist_window_moves(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A reconnect should resume from the next visible segment when older ones disappeared."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:100",
            "#EXTINF:1.0,",
            "segment_100.ts",
        ]
    )
    resumed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:102",
            "#EXTINF:1.0,",
            "segment_102.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
            (200, resumed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_100.ts": (200, b"100", "video/mp2t"),
        "/live/segment_102.ts": (200, b"102", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-resume-gap")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [100, 102]
    assert any(message == "api_stream playlist window advanced [%s]" for message, _ in info_logs)
    cleanup_api_stream_temp_session_dir("session-http-resume-gap")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_just_after_reconnect(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during reconnect backoff should stop the live loop cleanly."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 1.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    def maybe_cancel_on_sleep(seconds: float) -> None:
        if seconds == 1.0:
            request_session_cancel("session-http-cancel-reconnect")

    monkeypatch.setattr(stream_loader.time, "sleep", maybe_cancel_on_sleep)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:150",
            "#EXTINF:1.0,",
            "segment_150.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
        ],
        "/live/segment_150.ts": (200, b"150", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-reconnect")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [150]
    cleanup_api_stream_temp_session_dir("session-http-cancel-reconnect")


def test_http_hls_loader_skips_replayed_segment_after_reconnect_and_keeps_new_work(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A replayed segment after reconnect should be skipped while the new segment still runs."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:200",
            "#EXTINF:1.0,",
            "segment_200.ts",
        ]
    )
    replayed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:200",
            "#EXTINF:1.0,",
            "segment_200.ts",
            "#EXTINF:1.0,",
            "segment_201.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
            (200, replayed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_200.ts": (200, b"200", "video/mp2t"),
        "/live/segment_201.ts": (200, b"201", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-resume-replay")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [200, 201]
    cleanup_api_stream_temp_session_dir("session-http-resume-replay")


def test_http_hls_loader_skips_temporarily_unavailable_segment_and_continues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A temporary segment outage should be skipped while later segments still progress."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXTINF:1.0,",
            "segment_002.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"ok-000", "video/mp2t"),
        "/live/segment_001.ts": (503, "temporarily busy", "text/plain"),
        "/live/segment_002.ts": (200, b"ok-002", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-temp-outage")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts", "segment_002.ts"]
    assert [slice_.window_index for slice_ in slices] == [0, 2]
    cleanup_api_stream_temp_session_dir("session-http-temp-outage")


def test_http_hls_loader_fails_when_reconnect_budget_is_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated retryable playlist failures should become terminal after the configured budget."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-budget")
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-budget")


def test_http_hls_loader_persists_identity_keys_and_skips_replayed_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Persisted de-dup keys should prevent replay after reconnect or repeated loader startup."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:5",
            "#EXTINF:1.0,",
            "segment_005.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_005.ts": (200, b"005", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        first_loader = HttpHlsApiStreamLoader("session-http-dedup")
        first_slices = collect_api_stream_slices(first_loader, source)
        second_loader = HttpHlsApiStreamLoader("session-http-dedup")
        second_slices = collect_api_stream_slices(second_loader, source)

    assert [slice_.window_index for slice_ in first_slices] == [5]
    assert second_slices == []
    assert read_api_stream_seen_chunk_keys("session-http-dedup") == {
        (source.input_path, 5, "segment_005.ts")
    }
    cleanup_api_stream_temp_session_dir("session-http-dedup")


def test_http_hls_loader_skips_duplicate_segment_replay_during_playlist_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Playlist replay should not duplicate already accepted live segments in one run."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:7",
            "#EXTINF:1.0,",
            "segment_007.ts",
        ]
    )
    replayed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:7",
            "#EXTINF:1.0,",
            "segment_007.ts",
            "#EXTINF:1.0,",
            "segment_008.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, replayed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_007.ts": (200, b"007", "video/mp2t"),
        "/live/segment_008.ts": (200, b"008", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-replay")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [7, 8]
    assert [slice_.source_name for slice_ in slices] == ["segment_007.ts", "segment_008.ts"]
    cleanup_api_stream_temp_session_dir("session-http-replay")


def test_http_hls_loader_logs_selected_variant_refresh_stats_and_replay_skips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Loader logs should expose variant choice, refresh counts, new segments, and replay skips."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    master_text = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
            "low/index.m3u8",
            '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
            "high/index.m3u8",
        ]
    )
    first_media = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:50",
            "#EXTINF:1.0,",
            "segment_050.ts",
        ]
    )
    second_media = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:50",
            "#EXTINF:1.0,",
            "segment_050.ts",
            "#EXTINF:1.0,",
            "segment_051.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/low/index.m3u8": [
            (200, first_media, "application/vnd.apple.mpegurl"),
            (200, second_media, "application/vnd.apple.mpegurl"),
        ],
        "/high/index.m3u8": (200, second_media, "application/vnd.apple.mpegurl"),
        "/low/segment_050.ts": (200, b"050", "video/mp2t"),
        "/low/segment_051.ts": (200, b"051", "video/mp2t"),
        "/high/segment_050.ts": (200, b"050", "video/mp2t"),
        "/high/segment_051.ts": (200, b"051", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-logs")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [50, 51]
    assert any(message == "Selected api_stream variant [%s]" for message, _ in info_logs)
    refresh_logs = [args[0] for message, args in info_logs if message == "Refreshed api_stream playlist [%s]"]
    assert refresh_logs
    assert any("session_id='session-http-logs'" in str(entry) for entry in refresh_logs)
    assert any("playlist_refresh_count=1" in str(entry) and "new_segment_count=1" in str(entry) for entry in refresh_logs)
    assert any("playlist_refresh_count=2" in str(entry) and "new_segment_count=1" in str(entry) and "skipped_replay_count=1" in str(entry) for entry in refresh_logs)
    cleanup_api_stream_temp_session_dir("session-http-logs")


def test_http_hls_loader_semi_soak_run_keeps_temp_cleanup_and_dedup_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer local HLS run should stay bounded in temp files, dedup state, and idle shutdown."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 2)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_specs = [
        (600, 601, False),
        (601, 602, False),
        (602, 603, False),
        (603, 604, False),
        (604, 605, False),
        (605, 606, False),
        (606, 607, False),
        (607, 608, False),
        (608, 609, False),
        (609, 610, False),
        (610, 611, False),
        (610, 611, False),
        (610, 611, False),
    ]
    playlist_responses = []
    for first_index, second_index, is_endlist in playlist_specs:
        lines = [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            f"#EXT-X-MEDIA-SEQUENCE:{first_index}",
            "#EXTINF:1.0,",
            f"segment_{first_index}.ts",
            "#EXTINF:1.0,",
            f"segment_{second_index}.ts",
        ]
        if is_endlist:
            lines.append("#EXT-X-ENDLIST")
        playlist_responses.append(
            (200, "\n".join(lines), "application/vnd.apple.mpegurl")
        )

    routes: dict[str, object] = {
        "/live/index.m3u8": playlist_responses,
    }
    for index in range(600, 612):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"segment-{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-semi-soak")
        temp_dir = build_api_stream_temp_session_dir("session-http-semi-soak")
        collected_indexes: list[int] = []

        for slice_ in iter_api_stream_slices(loader, source):
            assert slice_.window_index is not None
            collected_indexes.append(slice_.window_index)
            slice_.file_path.unlink()

        assert collected_indexes == list(range(600, 612))
        assert len(collected_indexes) == len(set(collected_indexes))
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(600, 612)
        }
        assert temp_dir.exists()
        assert not any(temp_dir.iterdir())

    assert len(sleep_calls) >= 2
    assert sleep_calls[-2:] == [0.0, 0.0]
    cleanup_api_stream_temp_session_dir("session-http-semi-soak")


def test_http_hls_loader_semi_soak_restart_keeps_persisted_dedup_and_temp_state_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer run across loader restarts should not replay persisted chunks or leak temp files."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 1)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:700",
                        "#EXTINF:1.0,",
                        "segment_700.ts",
                        "#EXTINF:1.0,",
                        "segment_701.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:701",
                        "#EXTINF:1.0,",
                        "segment_701.ts",
                        "#EXTINF:1.0,",
                        "segment_702.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:702",
                        "#EXTINF:1.0,",
                        "segment_702.ts",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:703",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                        "#EXTINF:1.0,",
                        "segment_704.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:703",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                        "#EXTINF:1.0,",
                        "segment_704.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    for index in range(700, 705):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"segment-{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        temp_dir = build_api_stream_temp_session_dir("session-http-semi-soak-restart")

        first_loader = HttpHlsApiStreamLoader("session-http-semi-soak-restart")
        first_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(first_loader, source):
            assert slice_.window_index is not None
            first_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
            if slice_.window_index == 702:
                break
        first_loader.close()

        assert first_indexes == [700, 701, 702]
        assert temp_dir.exists()
        assert not any(temp_dir.iterdir())
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(700, 703)
        }

        second_loader = HttpHlsApiStreamLoader("session-http-semi-soak-restart")
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

        assert second_indexes == [703, 704]
        assert not any(temp_dir.iterdir())
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(700, 705)
        }

    cleanup_api_stream_temp_session_dir("session-http-semi-soak-restart")


def test_http_hls_loader_recovers_from_interrupted_run_by_clearing_stale_temp_media(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restarted loader should drop orphaned temp media while preserving persisted dedup state."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"001", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        session_id = "session-http-interrupted-recovery"
        temp_dir = build_api_stream_temp_session_dir(session_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "orphan-segment.ts").write_bytes(b"stale")
        stream_loader.append_api_stream_seen_chunk_key(
            session_id,
            (source.input_path, 0, "segment_000.ts"),
        )

        loader = HttpHlsApiStreamLoader(session_id)
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [1]
    assert [slice_.source_name for slice_ in slices] == ["segment_001.ts"]
    assert not (temp_dir / "orphan-segment.ts").exists()
    cleanup_api_stream_temp_session_dir("session-http-interrupted-recovery")


def test_http_hls_loader_enforces_temp_storage_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Temp media materialization should stop when the configured disk budget is exceeded."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_TEMP_MAX_BYTES", 3)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"toolarge", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-temp-budget")
        with pytest.raises(ValueError, match="temp storage exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-temp-budget")


def test_http_hls_loader_enforces_fetch_timeout_budget_cleanly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated playlist fetch timeouts should exhaust the reconnect budget predictably."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_MAX_RECONNECT_ATTEMPTS", 1)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    monkeypatch.setattr(
        stream_loader,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(TimeoutError()),
    )

    loader = HttpHlsApiStreamLoader("session-http-timeout-budget")
    source = build_api_stream_source_contract("https://example.com/live/index.m3u8")

    with pytest.raises(ValueError, match="reconnect budget exhausted: api_stream fetch timed out"):
        collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-timeout-budget")


def test_http_hls_loader_enforces_max_fetch_byte_budget_on_large_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Oversized segment downloads should fail before they can run away in real-data tests."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_FETCH_BYTES", 3)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"toolarge", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-fetch-budget")
        with pytest.raises(ValueError, match="fetch exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-fetch-budget")


def test_collect_api_stream_slices_deletes_rejected_temp_media_before_persistence(
    tmp_path: Path,
) -> None:
    """A discarded live slice should not leave behind temp media outside session processing."""
    source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    accepted_file = tmp_path / "accepted-live.ts"
    rejected_file = tmp_path / "rejected-live.ts"
    accepted_file.write_bytes(b"ok")
    rejected_file.write_bytes(b"reject")

    slices = [
        build_api_stream_analysis_slice(
            source=source,
            file_path=accepted_file,
            chunk_index=0,
            current_item="live-window-000.ts",
            window_start_sec=0.0,
            window_duration_sec=1.0,
        ),
        AnalysisSlice(
            file_path=rejected_file,
            source_group=source.input_path,
            source_name="live-window-001.ts",
            window_index=0,
            window_start_sec=1.0,
            window_duration_sec=1.0,
        ),
    ]

    collected = collect_api_stream_slices(StaticApiStreamLoader(slices), source)

    assert [slice_.source_name for slice_ in collected] == ["live-window-000.ts"]
    assert accepted_file.exists()
    assert not rejected_file.exists()


@contextmanager
def _serve_local_hls(routes: dict[str, object]):
    route_state = _RouteState(routes)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status, body, content_type, headers = route_state.next_response(self.path)
            payload = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for header_name, header_value in headers.items():
                self.send_header(header_name, header_value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class _RouteState:
    def __init__(self, routes: dict[str, object]) -> None:
        self._routes = {
            path: (list(spec) if isinstance(spec, list) else [spec])
            for path, spec in routes.items()
        }
        self._counts = {path: 0 for path in routes}

    def next_response(
        self, path: str
    ) -> tuple[int, str | bytes, str, dict[str, str]]:
        sequence = self._routes.get(path)
        if not sequence:
            return (404, "not found", "text/plain", {})
        index = min(self._counts[path], len(sequence) - 1)
        self._counts[path] += 1
        response = sequence[index]
        assert isinstance(response, tuple)
        if len(response) == 3:
            status, body, content_type = response
            return status, body, content_type, {}
        status, body, content_type, headers = response
        return status, body, content_type, headers
