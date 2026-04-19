import { describe, expect, it, vi } from "vitest";

import {
  ApiHttpError,
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

  it("does not fall back to CLI on structured FastAPI business errors", async () => {
    const state = createFastApiReadinessState();
    const apiGetHealth = vi.fn().mockResolvedValue({ ok: true });
    const apiOperation = vi.fn().mockRejectedValue(
      new ApiHttpError("Session not found", {
        status: 404,
        apiPayload: {
          detail: "Session not found",
          error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found for session_id=abc123",
        },
      }),
    );
    const cliOperation = vi.fn();
    const warn = vi.fn();

    await expect(
      withFastApiFallback({
        state,
        apiGetHealth,
        operationName: "bridge:read-session",
        apiOperation,
        cliOperation,
        warn,
      }),
    ).rejects.toMatchObject({
      name: "ApiHttpError",
      status: 404,
      apiPayload: {
        error_code: "session_not_found",
      },
    });

    expect(cliOperation).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalledWith(
      expect.stringContaining("falling back to CLI"),
      expect.anything(),
    );
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
