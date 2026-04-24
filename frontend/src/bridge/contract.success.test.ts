/**
 * Success-path tests for the public bridge contract facade and the positive
 * normalization paths delegated to detector and playback-source helpers.
 */

import { describe, expect, it, vi } from "vitest";

import type { LocalBridge } from "../types";
import {
  createNormalizedBridge,
  normalizeDetectorOptions,
  normalizePlaybackSource,
} from "./contract";

describe("bridge contract success normalization", () => {
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

  it("normalizes playback source values to non-empty strings or null", () => {
    expect(normalizePlaybackSource(" https://example.com/live.m3u8 ")).toBe(
      "https://example.com/live.m3u8",
    );
    expect(normalizePlaybackSource("   ")).toBeNull();
    expect(normalizePlaybackSource({ source: "https://example.com" })).toBeNull();
  });

  it("returns an empty detector list when a success envelope contains malformed detector data", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn().mockResolvedValue({
        ok: true,
        data: { broken: true },
      }),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.listDetectors("api_stream")).resolves.toEqual([]);
  });

  it("accepts a FastAPI-style startSession success payload", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session_id: "session-api-1",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics", "video_blur"],
          status: "pending",
        },
      }),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(
      bridge.startSession({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/index.m3u8",
          access: "api_stream",
        },
        selectedDetectors: ["video_metrics", "video_blur"],
      }),
    ).resolves.toEqual({
      session_id: "session-api-1",
      mode: "api_stream",
      input_path: "https://example.com/live/index.m3u8",
      selected_detectors: ["video_metrics", "video_blur"],
      status: "pending",
    });
  });

  it("rejects a success envelope when startSession returns an invalid status value", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session_id: "session-api-1",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics"],
          status: "done",
        },
      }),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(
      bridge.startSession({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/index.m3u8",
          access: "api_stream",
        },
        selectedDetectors: ["video_metrics"],
      }),
    ).rejects.toThrow("invalid bridge startSession response");
  });

  it("accepts a FastAPI-style cancelSession success payload", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session_id: "session-123",
          mode: "video_segments",
          input_path: "/data/streams/segments",
          selected_detectors: ["video_blur"],
          status: "cancelling",
        },
      }),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).resolves.toEqual({
      session_id: "session-123",
      mode: "video_segments",
      input_path: "/data/streams/segments",
      selected_detectors: ["video_blur"],
      status: "cancelling",
    });
  });

  it("rejects a cancelSession success envelope when it contains an invalid mode", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session_id: "session-123",
          mode: "remote_shell",
          input_path: "/data/streams/segments",
          selected_detectors: ["video_blur"],
          status: "cancelling",
        },
      }),
      resolvePlaybackSource: vi.fn(),
    } as unknown as LocalBridge);

    await expect(bridge.cancelSession("session-123")).rejects.toThrow(
      "invalid bridge cancelSession response",
    );
  });

  it("accepts a null cancelSession success payload", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: null,
      }),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).resolves.toBeNull();
  });

  it("normalizes a blank playback source inside an explicit success envelope to null", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn().mockResolvedValue({
        ok: true,
        data: "   ",
      }),
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
    ).resolves.toBeNull();
  });

  it("normalizes malformed readSession data inside an explicit success envelope", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session: { session_id: "broken" },
          alerts: "broken",
          results: null,
        },
      }),
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

  it("normalizes a real FastAPI-style session snapshot payload without losing fields", async () => {
    const bridgeSnapshot = {
      session: {
        session_id: "session-1",
        mode: "api_stream",
        input_path: "https://example.com/live/index.m3u8",
        selected_detectors: ["video_metrics", "video_blur"],
        status: "running",
      },
      progress: {
        session_id: "session-1",
        status: "running",
        processed_count: 3,
        total_count: 8,
        current_item: "live-window-003.ts",
        latest_result_detector: "video_metrics",
        latest_result_detectors: ["video_metrics", "video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-04-18 10:00:00",
        status_reason: "running",
        status_detail: null,
      },
      alerts: [
        {
          session_id: "session-1",
          timestamp_utc: "2026-04-18 10:00:00",
          detector_id: "video_metrics",
          title: "Black screen detected",
          message: "Long black segment exceeded threshold.",
          severity: "warning",
          source_name: "live-window-003.ts",
          window_index: 3,
          window_start_sec: 6.0,
        },
      ],
      results: [
        {
          session_id: "session-1",
          detector_id: "video_metrics",
          payload: {
            black_ratio: 0.8,
            longest_black_sec: 2.4,
          },
        },
      ],
      latest_result: {
        session_id: "session-1",
        detector_id: "video_metrics",
        payload: {
          black_ratio: 0.8,
          longest_black_sec: 2.4,
        },
      },
    };

    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue({
        ok: true,
        data: bridgeSnapshot,
      }),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-1")).resolves.toEqual({
      session: {
        session_id: "session-1",
        mode: "api_stream",
        input_path: "https://example.com/live/index.m3u8",
        selected_detectors: ["video_metrics", "video_blur"],
        status: "running",
      },
      progress: {
        session_id: "session-1",
        status: "running",
        processed_count: 3,
        total_count: 8,
        current_item: "live-window-003.ts",
        latest_result_detector: "video_metrics",
        latest_result_detectors: ["video_metrics", "video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-04-18 10:00:00",
        status_reason: "running",
        status_detail: null,
      },
      alerts: [
        {
          session_id: "session-1",
          timestamp_utc: "2026-04-18 10:00:00",
          detector_id: "video_metrics",
          title: "Black screen detected",
          message: "Long black segment exceeded threshold.",
          severity: "warning",
          source_name: "live-window-003.ts",
          window_index: 3,
          window_start_sec: 6.0,
        },
      ],
      results: [
        {
          session_id: "session-1",
          detector_id: "video_metrics",
          payload: {
            black_ratio: 0.8,
            longest_black_sec: 2.4,
          },
        },
      ],
      latest_result: {
        session_id: "session-1",
        detector_id: "video_metrics",
        payload: {
          black_ratio: 0.8,
          longest_black_sec: 2.4,
        },
      },
    });
  });
});
