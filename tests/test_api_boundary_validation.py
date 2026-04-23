from tests.api_boundary_test_support import request


def test_detectors_invalid_mode() -> None:
    response = request("GET", "/detectors?mode=invalid_mode")
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "query.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_playback_resolve_requires_payload() -> None:
    response = request("POST", "/playback/resolve")
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body: Field required",
    }


def test_playback_resolve_api_stream_requires_direct_media_url() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "https://example.com/watch/live",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
    }


def test_playback_resolve_api_stream_rejects_private_host() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "http://127.0.0.1/live/index.m3u8",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream host is not allowed in local mode: 127.0.0.1",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream host is not allowed in local mode: 127.0.0.1",
    }


def test_playback_resolve_invalid_mode() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "invalid_mode",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": None,
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_sessions_start_requires_payload() -> None:
    response = request("POST", "/sessions")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body: Field required",
    }


def test_sessions_start_rejects_malformed_body() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "video_files",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    assert "body.input_path" in payload["status_detail"]


def test_sessions_start_invalid_mode() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "invalid_mode",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_sessions_start_api_stream_requires_direct_media_url() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "api_stream",
            "input_path": "https://example.com/watch/live",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
    }


def test_playback_resolve_api_stream_rejects_credentials_in_url() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "https://user:secret@example.com/live/index.m3u8",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream URLs must not include credentials.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream URLs must not include credentials.",
    }
