import { describe, expect, it } from "vitest";

import { ApiHttpError } from "./apiErrors.mjs";
import { handleBridgeOperation } from "./bridgeResponses.mjs";
import { FastApiUnavailableError } from "./fastApiRuntimePolicy.mjs";

describe("Electron bridge response mapping", () => {
  it("wraps start-session success with the expected bridge payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_START_FAILED",
      "Session start request failed",
      async () => ({
        session_id: "session-1",
        mode: "video_files",
        input_path: "/tmp/input.mp4",
        selected_detectors: ["video_metrics"],
        status: "pending",
      }),
    );

    expect(result).toEqual({
      ok: true,
      data: {
        session_id: "session-1",
        mode: "video_files",
        input_path: "/tmp/input.mp4",
        selected_detectors: ["video_metrics"],
        status: "pending",
      },
    });
  });

  it("maps start-session validation failures into the bridge error payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_START_FAILED",
      "Session start request failed",
      async () => {
        throw new ApiHttpError("Request validation failed", {
          status: 422,
          apiPayload: {
            detail: "Request validation failed",
            error_code: "validation_failed",
            status_reason: "validation_failed",
            status_detail: "body.input_path: Field required",
          },
        });
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_START_FAILED",
        message: "Session start request failed",
        details: "body.input_path: Field required",
        backend_error_code: "validation_failed",
        status_reason: "validation_failed",
        status_detail: "body.input_path: Field required",
      },
    });
  });

  it("maps start-session backend failures into the bridge error payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_START_FAILED",
      "Session start request failed",
      async () => {
        throw new ApiHttpError("Session start failed", {
          status: 500,
          apiPayload: {
            detail: "Session start failed",
            error_code: "session_start_failed",
            status_reason: "session_start_failed",
            status_detail: "Failed to spawn detached monitoring process.",
          },
        });
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_START_FAILED",
        message: "Session start request failed",
        details: "Failed to spawn detached monitoring process.",
        backend_error_code: "session_start_failed",
        status_reason: "session_start_failed",
        status_detail: "Failed to spawn detached monitoring process.",
      },
    });
  });

  it("maps transport unavailability into a generic bridge failure payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_START_FAILED",
      "Session start request failed",
      async () => {
        throw new TypeError("fetch failed");
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_START_FAILED",
        message: "Session start request failed",
        details: "fetch failed",
        backend_error_code: null,
        status_reason: null,
        status_detail: null,
      },
    });
  });

  it("maps cancel-session missing-session failures into the bridge error payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_CANCEL_FAILED",
      "Session cancel request failed",
      async () => {
        throw new ApiHttpError("Session not found", {
          status: 404,
          apiPayload: {
            detail: "Session not found",
            error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-123",
          },
        });
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_CANCEL_FAILED",
        message: "Session cancel request failed",
        details: "No persisted session snapshot found for session_id=session-123",
        backend_error_code: "session_not_found",
        status_reason: "session_not_found",
        status_detail: "No persisted session snapshot found for session_id=session-123",
      },
    });
  });

  it("maps cancel-session invalid-state failures into the bridge error payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_CANCEL_FAILED",
      "Session cancel request failed",
      async () => {
        throw new ApiHttpError("Session cannot be cancelled from its current state", {
          status: 409,
          apiPayload: {
            detail: "Session cannot be cancelled from its current state",
            error_code: "cancel_failed",
            status_reason: "cancel_failed",
            status_detail: "Session session-123 is already completed.",
          },
        });
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_CANCEL_FAILED",
        message: "Session cancel request failed",
        details: "Session session-123 is already completed.",
        backend_error_code: "cancel_failed",
        status_reason: "cancel_failed",
        status_detail: "Session session-123 is already completed.",
      },
    });
  });

  it("wraps cancel-session success with the expected bridge payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_CANCEL_FAILED",
      "Session cancel request failed",
      async () => ({
        session_id: "session-123",
        mode: "video_segments",
        input_path: "/data/streams/segments",
        selected_detectors: ["video_blur"],
        status: "cancelling",
      }),
    );

    expect(result).toEqual({
      ok: true,
      data: {
        session_id: "session-123",
        mode: "video_segments",
        input_path: "/data/streams/segments",
        selected_detectors: ["video_blur"],
        status: "cancelling",
      },
    });
  });

  it("wraps terminal read-session snapshots as normal bridge success payloads", async () => {
    const result = await handleBridgeOperation(
      "SESSION_READ_FAILED",
      "Session read request failed",
      async () => ({
        session: {
          session_id: "session-123",
          mode: "video_files",
          input_path: "/tmp/input.mp4",
          selected_detectors: ["video_metrics"],
          status: "completed",
        },
        progress: {
          session_id: "session-123",
          status: "completed",
          processed_count: 4,
          total_count: 4,
          current_item: null,
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 0,
          last_updated_utc: "2026-04-21 10:00:00",
          status_reason: "completed",
          status_detail: null,
        },
        alerts: [],
        results: [],
        latest_result: null,
      }),
    );

    expect(result).toEqual({
      ok: true,
      data: {
        session: {
          session_id: "session-123",
          mode: "video_files",
          input_path: "/tmp/input.mp4",
          selected_detectors: ["video_metrics"],
          status: "completed",
        },
        progress: {
          session_id: "session-123",
          status: "completed",
          processed_count: 4,
          total_count: 4,
          current_item: null,
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 0,
          last_updated_utc: "2026-04-21 10:00:00",
          status_reason: "completed",
          status_detail: null,
        },
        alerts: [],
        results: [],
        latest_result: null,
      },
    });
  });

  it("wraps failed terminal read-session snapshots as normal bridge success payloads", async () => {
    const result = await handleBridgeOperation(
      "SESSION_READ_FAILED",
      "Session read request failed",
      async () => ({
        session: {
          session_id: "session-456",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics"],
          status: "failed",
        },
        progress: {
          session_id: "session-456",
          status: "failed",
          processed_count: 3,
          total_count: 8,
          current_item: "live-window-003.ts",
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 1,
          last_updated_utc: "2026-04-21 10:05:00",
          status_reason: "source_unreachable",
          status_detail: "api_stream reconnect budget exhausted: upstream returned HTTP 503",
        },
        alerts: [],
        results: [],
        latest_result: null,
      }),
    );

    expect(result).toEqual({
      ok: true,
      data: {
        session: {
          session_id: "session-456",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics"],
          status: "failed",
        },
        progress: {
          session_id: "session-456",
          status: "failed",
          processed_count: 3,
          total_count: 8,
          current_item: "live-window-003.ts",
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 1,
          last_updated_utc: "2026-04-21 10:05:00",
          status_reason: "source_unreachable",
          status_detail: "api_stream reconnect budget exhausted: upstream returned HTTP 503",
        },
        alerts: [],
        results: [],
        latest_result: null,
      },
    });
  });

  it("maps read-session missing-session failures into the bridge error payload", async () => {
    const result = await handleBridgeOperation(
      "SESSION_READ_FAILED",
      "Session read request failed",
      async () => {
        throw new ApiHttpError("Session not found", {
          status: 404,
          apiPayload: {
            detail: "Session not found",
            error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-456",
          },
        });
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_READ_FAILED",
        message: "Session read request failed",
        details: "No persisted session snapshot found for session_id=session-456",
        backend_error_code: "session_not_found",
        status_reason: "session_not_found",
        status_detail: "No persisted session snapshot found for session_id=session-456",
      },
    });
  });

  it("maps runtime-policy unavailable failures into a clear bridge failure", async () => {
    const result = await handleBridgeOperation(
      "SESSION_READ_FAILED",
      "Session read request failed",
      async () => {
        throw new FastApiUnavailableError();
      },
    );

    expect(result).toEqual({
      ok: false,
      error: {
        code: "SESSION_READ_FAILED",
        message: "Session read request failed",
        details: "Local FastAPI backend is unavailable",
        backend_error_code: null,
        status_reason: null,
        status_detail: null,
      },
    });
  });
});
