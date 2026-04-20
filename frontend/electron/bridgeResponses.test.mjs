import { describe, expect, it } from "vitest";

import { ApiHttpError } from "./fastApiFallback.mjs";
import { handleBridgeOperation } from "./bridgeResponses.mjs";

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
});
