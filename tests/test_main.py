"""Tiny legacy smoke checks for the old `main.py` entrypoint.

The canonical runtime path is Electron -> FastAPI -> session service ->
session runner. These tests only protect the leftover `main.py` wiring so it
does not break accidentally while the legacy local-only harness still exists.
Keep this suite intentionally small; it should only guard the leftover wrapper
shape and should not grow into a second runtime-behavior suite.
"""

from functools import partial

import pytest

import main


@pytest.mark.parametrize("mode", ["video_segments", "video_files"])
def test_main_keeps_legacy_local_routing_shape(monkeypatch, mode: str) -> None:
    """The legacy entrypoint should still dispatch through `stream_local_prefix`."""
    recorded: dict[str, object] = {}

    monkeypatch.setattr(main.config, "DATA_SOURCE", mode)
    monkeypatch.setattr(main, "stream_local_prefix", lambda **kwargs: recorded.update(kwargs))
    monkeypatch.setattr(main.black_frame_store, "flush", lambda: None)
    monkeypatch.setattr(main.blur_metrics_store, "flush", lambda: None)

    main.main()

    assert recorded["prefix"] == "segments"
    assert isinstance(recorded["on_segment"], partial)
    assert recorded["on_segment"].func is main.process_video_file
    assert recorded["on_segment"].keywords == {"mode": mode}


def test_main_rejects_non_local_modes_with_legacy_harness_guidance(monkeypatch) -> None:
    """Unsupported modes should point callers back to the canonical runtime."""
    monkeypatch.setattr(main.config, "DATA_SOURCE", "api_stream")

    with pytest.raises(ValueError, match="legacy local analysis harness"):
        main.main()
