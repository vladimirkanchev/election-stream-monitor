from tests.api_boundary_test_support import request


def test_playback_resolve_with_payload() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": None,
        },
    )
    assert response.status_code == 200
    assert "source" in response.json()


def test_playback_resolve_validation_failure(monkeypatch) -> None:
    def fake_validate_source_input(mode: str, input_path: str) -> str:
        raise OSError("Input path does not exist: missing.mp4")

    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        fake_validate_source_input,
    )

    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "missing.mp4",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Input path does not exist: missing.mp4",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "Input path does not exist: missing.mp4",
    }


def test_playback_resolve_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        lambda mode, input_path: input_path,
    )

    def fake_resolve_playback_source(
        mode: str,
        input_path: str,
        current_item: str | None = None,
    ) -> str | None:
        _ = (mode, input_path, current_item)
        raise ValueError("Playable source missing for current item")

    monkeypatch.setattr(
        "api.routers.playback.resolve_playback_source",
        fake_resolve_playback_source,
    )

    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": "black_trigger.mp4",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Playback source could not be resolved",
        "error_code": "playback_unavailable",
        "status_reason": "playback_unavailable",
        "status_detail": "Playable source missing for current item",
    }


def test_playback_resolve_unexpected_failure_returns_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        lambda mode, input_path: input_path,
    )

    def fake_resolve_playback_source(
        mode: str,
        input_path: str,
        current_item: str | None = None,
    ) -> str | None:
        _ = (mode, input_path, current_item)
        raise RuntimeError("playback backend exploded")

    monkeypatch.setattr(
        "api.routers.playback.resolve_playback_source",
        fake_resolve_playback_source,
    )

    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": "black_trigger.mp4",
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unexpected backend error",
        "error_code": "internal_error",
        "status_reason": "internal_error",
        "status_detail": "playback backend exploded",
    }
