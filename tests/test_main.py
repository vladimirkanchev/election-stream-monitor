"""Tests for top-level mode routing in the application entrypoint."""

from functools import partial

import main


def test_main_routes_video_segments_mode(monkeypatch) -> None:
    """Main should wire segment mode to the video processor with the right prefix."""
    recorded: dict = {}

    monkeypatch.setattr(main.config, "DATA_SOURCE", "video_segments")
    monkeypatch.setattr(
        main,
        "stream_local_prefix",
        lambda **kwargs: recorded.update(kwargs),
    )
    monkeypatch.setattr(main.black_frame_store, "flush", lambda: None)
    monkeypatch.setattr(main.blur_metrics_store, "flush", lambda: None)

    main.main()

    assert recorded["prefix"] == "segments"
    assert isinstance(recorded["on_segment"], partial)
    assert recorded["on_segment"].func is main.process_video_file
    assert recorded["on_segment"].keywords == {"mode": "video_segments"}


def test_main_routes_video_files_mode(monkeypatch) -> None:
    """Main should wire video file mode to the video processor with the right mode."""
    recorded: dict = {}

    monkeypatch.setattr(main.config, "DATA_SOURCE", "video_files")
    monkeypatch.setattr(
        main,
        "stream_local_prefix",
        lambda **kwargs: recorded.update(kwargs),
    )
    monkeypatch.setattr(main.black_frame_store, "flush", lambda: None)
    monkeypatch.setattr(main.blur_metrics_store, "flush", lambda: None)

    main.main()

    assert recorded["prefix"] == "segments"
    assert isinstance(recorded["on_segment"], partial)
    assert recorded["on_segment"].func is main.process_video_file
    assert recorded["on_segment"].keywords == {"mode": "video_files"}
