"""Tests for `api_stream` loader contracts, helper builders, and seam loaders.

This file keeps the lightweight source-of-truth checks separate from the
heavier concrete HTTP HLS runtime behavior tests.
"""

from pathlib import Path

import pytest

import stream_loader
from analyzer_contract import AnalysisSlice
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
    PlaceholderApiStreamLoader,
    StaticApiStreamLoader,
    build_api_stream_analysis_slice,
    build_api_stream_chunk_identity,
    build_api_stream_dedup_policy,
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
    collect_api_stream_slices,
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
    assert any(
        "processed_chunk_count=1" in str(args[0])
        for message, args in info_logs
        if message == "Accepted api_stream slice [%s]"
    )
    assert any(
        message == "Skipping temporary api_stream failure [%s]"
        for message, _ in warning_logs
    )
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
