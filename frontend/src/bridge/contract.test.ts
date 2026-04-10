import { describe, expect, it, vi } from "vitest";

import type { LocalBridge } from "../types";
import {
  BridgeTransportError,
  createNormalizedBridge,
  fail,
  normalizeDetectorOptions,
  normalizePlaybackSource,
  normalizeSessionSnapshot,
  ok,
} from "./contract";

describe("bridge contract normalization", () => {
  it("filters malformed detector entries from the catalog response", () => {
    expect(
      normalizeDetectorOptions([
        {
          id: "video_blur",
          display_name: "Blur Check",
          description: "Blur detector",
          category: "quality",
          origin: "built_in",
          status: "optional",
          default_rule_id: "video_blur.default_rule",
          default_selected: false,
          produces_alerts: true,
          supported_modes: ["video_segments", "video_files", "api_stream"],
          supported_suffixes: [".ts", ".mp4"],
        },
        {
          id: "broken",
          display_name: "Broken detector",
        },
      ]),
    ).toEqual([
      {
        id: "video_blur",
        display_name: "Blur Check",
        description: "Blur detector",
        category: "quality",
        origin: "built_in",
        status: "optional",
        default_rule_id: "video_blur.default_rule",
        default_selected: false,
        produces_alerts: true,
        supported_modes: ["video_segments", "video_files", "api_stream"],
        supported_suffixes: [".ts", ".mp4"],
      },
    ]);
  });

  it("normalizes malformed session snapshots into a stable empty shape", () => {
    expect(
      normalizeSessionSnapshot({
        session: { session_id: "session-1" },
        alerts: "broken",
      }),
    ).toEqual({
      session: null,
      progress: null,
      alerts: [],
      results: [],
      latest_result: null,
    });
  });

  it("normalizes playback source values to non-empty strings or null", () => {
    expect(normalizePlaybackSource(" https://example.com/live.m3u8 ")).toBe(
      "https://example.com/live.m3u8",
    );
    expect(normalizePlaybackSource("   ")).toBeNull();
    expect(normalizePlaybackSource({ source: "https://example.com" })).toBeNull();
  });

  it("raises when startSession returns a malformed summary", async () => {
    const rawBridge: LocalBridge = {
      listDetectors: vi.fn().mockResolvedValue([]),
      startSession: vi.fn().mockResolvedValue({
        mode: "video_segments",
        status: "running",
      }),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    };

    const bridge = createNormalizedBridge(rawBridge);

    await expect(
      bridge.startSession({
        source: {
          kind: "video_segments",
          path: "/tmp/source",
          access: "local_path",
        },
        selectedDetectors: [],
      }),
    ).rejects.toThrow("invalid bridge startSession response");
  });

  it("raises a typed bridge error when the transport returns an explicit start failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn().mockResolvedValue(
        fail("SESSION_START_FAILED", "Session start request failed", "cli crashed"),
      ),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(
      bridge.startSession({
        source: {
          kind: "video_segments",
          path: "/tmp/source",
          access: "local_path",
        },
        selectedDetectors: [],
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "cli crashed",
    });
  });

  it("normalizes malformed readSession data inside an explicit success envelope", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        ok({
          session: { session_id: "broken" },
          alerts: "broken",
          results: null,
        }),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-1")).resolves.toEqual({
      session: null,
      progress: null,
      alerts: [],
      results: [],
      latest_result: null,
    });
  });

  it("keeps optional session progress reason fields when a snapshot includes them", () => {
    expect(
      normalizeSessionSnapshot({
        session: {
          session_id: "session-1",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_blur"],
          status: "failed",
        },
        progress: {
          session_id: "session-1",
          status: "failed",
          processed_count: 1,
          total_count: 4,
          current_item: "live-window-001.ts",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-06 10:00:00",
          status_reason: "terminal_failure",
          status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
        },
        alerts: [],
        results: [],
        latest_result: null,
      }).progress,
    ).toMatchObject({
      status_reason: "terminal_failure",
      status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
    });
  });

  it("raises when cancelSession returns a malformed non-null summary", async () => {
    const rawBridge: LocalBridge = {
      listDetectors: vi.fn().mockResolvedValue([]),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        session_id: "session-1",
      }),
      resolvePlaybackSource: vi.fn(),
    };

    const bridge = createNormalizedBridge(rawBridge);

    await expect(bridge.cancelSession("session-1")).rejects.toThrow(
      "invalid bridge cancelSession response",
    );
  });

  it("raises a typed bridge error when playback resolution returns an explicit failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn().mockResolvedValue(
        fail(
          "PLAYBACK_SOURCE_RESOLUTION_FAILED",
          "Playback source resolution failed",
          "remote source unreachable",
        ),
      ),
    });

    await expect(
      bridge.resolvePlaybackSource({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        },
        currentItem: null,
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "PLAYBACK_SOURCE_RESOLUTION_FAILED",
      message: "Playback source resolution failed",
      details: "remote source unreachable",
    });
  });
});
