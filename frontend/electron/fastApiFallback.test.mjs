/**
 * Legacy fallback/readiness tests for the Electron FastAPI bridge helpers.
 *
 * These cases now complement the extracted `fastApiClient.mjs` and
 * `playbackSourcePolicy.mjs` tests by covering the older fallback seam that is
 * still useful for transport-level behavior and migration safety checks.
 */

import { describe, expect, it, vi } from "vitest";

import { ApiHttpError } from "./apiErrors.mjs";
import {
  createFastApiReadinessState,
  isFastApiAvailable,
  resolvePlaybackSourceWithFallback,
  withFastApiFallback,
} from "./fastApiFallback.mjs";

describe("FastAPI readiness and fallback helpers", () => {
  it("falls back to CLI when FastAPI health check fails", async () => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    const apiOperation = vi.fn();
    const cliOperation = vi.fn().mockResolvedValue([{ id: "video_metrics" }]);
    const warn = vi.fn();

    const result = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:list-detectors",
      apiOperation,
      cliOperation,
      warn,
    });

    expect(result).toEqual([{ id: "video_metrics" }]);
    expect(apiGetHealth).toHaveBeenCalledTimes(1);
    expect(apiOperation).not.toHaveBeenCalled();
    expect(cliOperation).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(
      "[bridge] FastAPI unavailable, falling back to CLI for bridge:list-detectors",
    );
  });

  it.each([
    {
      label: "business errors",
      operationName: "bridge:read-session",
      error: new ApiHttpError("Session not found", {
        status: 404,
        apiPayload: {
          detail: "Session not found",
          error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found for session_id=abc123",
        },
      }),
      expectedStatus: 404,
      expectedErrorCode: "session_not_found",
      expectedStatusReason: "session_not_found",
    },
    {
      label: "validation errors for start-session",
      operationName: "bridge:start-session",
      error: new ApiHttpError("Request validation failed", {
        status: 422,
        apiPayload: {
          detail: "Request validation failed",
          error_code: "validation_failed",
          status_reason: "validation_failed",
          status_detail: "body.input_path: Field required",
        },
      }),
      expectedStatus: 422,
      expectedErrorCode: "validation_failed",
      expectedStatusReason: "validation_failed",
    },
    {
      label: "structured start-session failures",
      operationName: "bridge:start-session",
      error: new ApiHttpError("Session start failed", {
        status: 500,
        apiPayload: {
          detail: "Session start failed",
          error_code: "session_start_failed",
          status_reason: "session_start_failed",
          status_detail: "Failed to spawn detached monitoring process.",
        },
      }),
      expectedStatus: 500,
      expectedErrorCode: "session_start_failed",
      expectedStatusReason: "session_start_failed",
    },
    {
      label: "missing-session errors for cancel-session",
      operationName: "bridge:cancel-session",
      error: new ApiHttpError("Session not found", {
        status: 404,
        apiPayload: {
          detail: "Session not found",
          error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found for session_id=session-123",
        },
      }),
      expectedStatus: 404,
      expectedErrorCode: "session_not_found",
      expectedStatusReason: "session_not_found",
    },
  ])("does not fall back to CLI on structured FastAPI $label", async ({
    operationName,
    error,
    expectedStatus,
    expectedErrorCode,
    expectedStatusReason,
  }) => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockResolvedValue({ ok: true });
    const apiOperation = vi.fn().mockRejectedValue(error);
    const cliOperation = vi.fn();
    const warn = vi.fn();

    await expect(
      withFastApiFallback({
        state,
        apiGetHealth,
        operationName,
        apiOperation,
        cliOperation,
        warn,
      }),
    ).rejects.toMatchObject({
      name: "ApiHttpError",
      status: expectedStatus,
      apiPayload: {
        error_code: expectedErrorCode,
        status_reason: expectedStatusReason,
      },
    });

    expect(cliOperation).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining("falling back to CLI"),
      expect.anything(),
    );
  });

  it("falls back to CLI on FastAPI unavailability for start-session", async () => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    const apiOperation = vi.fn();
    const cliOperation = vi.fn().mockResolvedValue({
      session_id: "session-123",
      mode: "video_files",
      input_path: "/tmp/input.mp4",
      selected_detectors: ["video_metrics"],
      status: "pending",
    });

    const result = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:start-session",
      apiOperation,
      cliOperation,
      warn: vi.fn(),
    });

    expect(result).toEqual({
      session_id: "session-123",
      mode: "video_files",
      input_path: "/tmp/input.mp4",
      selected_detectors: ["video_metrics"],
      status: "pending",
    });
    expect(apiOperation).not.toHaveBeenCalled();
    expect(cliOperation).toHaveBeenCalledTimes(1);
  });

  it("falls back to CLI on FastAPI unavailability for cancel-session", async () => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    const apiOperation = vi.fn();
    const cliOperation = vi.fn().mockResolvedValue({
      session_id: "session-123",
      mode: "video_files",
      input_path: "/tmp/input.mp4",
      selected_detectors: ["video_metrics"],
      status: "cancelling",
    });

    const result = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:cancel-session",
      apiOperation,
      cliOperation,
      warn: vi.fn(),
    });

    expect(result).toEqual({
      session_id: "session-123",
      mode: "video_files",
      input_path: "/tmp/input.mp4",
      selected_detectors: ["video_metrics"],
      status: "cancelling",
    });
    expect(apiOperation).not.toHaveBeenCalled();
    expect(cliOperation).toHaveBeenCalledTimes(1);
  });

  it("rechecks FastAPI readiness after an unavailable result and uses the API once health recovers", async () => {
    let currentTime = 10_000;
    const now = () => currentTime;

    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce({ ok: true });

    const firstCliOperation = vi.fn().mockResolvedValue([{ id: "video_metrics" }]);
    const secondApiOperation = vi.fn().mockResolvedValue([{ id: "video_blur" }]);

    const firstResult = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:list-detectors",
      apiOperation: vi.fn(),
      cliOperation: firstCliOperation,
      ttlMs: 1500,
      now,
      warn: vi.fn(),
    });

    expect(firstResult).toEqual([{ id: "video_metrics" }]);
    expect(state.available).toBe(false);

    currentTime += 1600;

    const secondResult = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:list-detectors",
      apiOperation: secondApiOperation,
      cliOperation: vi.fn(),
      ttlMs: 1500,
      now,
      warn: vi.fn(),
    });

    expect(secondResult).toEqual([{ id: "video_blur" }]);
    expect(secondApiOperation).toHaveBeenCalledTimes(1);
    expect(state.available).toBe(true);
    expect(apiGetHealth).toHaveBeenCalledTimes(2);
  });

  it("reuses readiness within TTL and marks state unavailable after transport failure", async () => {
    let currentTime = 10_000;
    const now = () => currentTime;

    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockResolvedValue({ ok: true });

    expect(
      await isFastApiAvailable({
        state,
        apiGetHealth,
        ttlMs: 1500,
        now,
      }),
    ).toBe(true);

    expect(
      await isFastApiAvailable({
        state,
        apiGetHealth,
        ttlMs: 1500,
        now,
      }),
    ).toBe(true);

    expect(apiGetHealth).toHaveBeenCalledTimes(1);

    const apiOperation = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    const cliOperation = vi.fn().mockResolvedValue({ session_id: "abc123" });
    const warn = vi.fn();

    const result = await withFastApiFallback({
      state,
      apiGetHealth,
      operationName: "bridge:read-session",
      apiOperation,
      cliOperation,
      ttlMs: 1500,
      now,
      warn,
    });

    expect(result).toEqual({ session_id: "abc123" });
    expect(state.available).toBe(false);
    expect(cliOperation).toHaveBeenCalledTimes(1);
  });

  it("adapts FastAPI playback resolution results through toRendererMediaUrl", async () => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockResolvedValue({ ok: true });
    const apiResolvePlaybackSource = vi.fn().mockResolvedValue({
      source: "/tmp/session/segment_0001.ts",
    });
    const cliResolvePlaybackSource = vi.fn();
    const toRendererMediaUrl = vi.fn().mockImplementation(
      (source) => `local-media://media${source}`,
    );

    const result = await resolvePlaybackSourceWithFallback({
      state,
      apiGetHealth,
      apiResolvePlaybackSource,
      cliResolvePlaybackSource,
      input: {
        source: {
          kind: "video_segments",
          path: "/tmp/session/index.m3u8",
        },
        currentItem: "segment_0001.ts",
      },
      toRendererMediaUrl,
      warn: vi.fn(),
    });

    expect(result).toBe("local-media://media/tmp/session/segment_0001.ts");
    expect(apiResolvePlaybackSource).toHaveBeenCalledTimes(1);
    expect(cliResolvePlaybackSource).not.toHaveBeenCalled();
    expect(toRendererMediaUrl).toHaveBeenCalledWith("/tmp/session/segment_0001.ts");
  });
});
