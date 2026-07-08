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
import {
  API_STREAM_MONITOR_SOURCE,
  buildDetectorOption,
  buildSessionProgress,
  buildSessionSummary,
  createContractBridge,
} from "./contract.testSupport";

describe("bridge contract success normalization", () => {
  it("filters malformed detector entries from the catalog response", () => {
    expect(
      normalizeDetectorOptions([
        buildDetectorOption(),
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
    const bridge = createContractBridge({
      listDetectors: vi.fn().mockResolvedValue({
        ok: true,
        data: { broken: true },
      }),
    });

    await expect(bridge.listDetectors("api_stream")).resolves.toEqual([]);
  });

  it("accepts a FastAPI-style startSession success payload", async () => {
    const bridge = createContractBridge({
      startSession: vi.fn().mockResolvedValue({
        ok: true,
        data: buildSessionSummary({
          session_id: "session-api-1",
          mode: "api_stream",
          input_path: API_STREAM_MONITOR_SOURCE.path,
          selected_detectors: ["video_metrics", "video_blur"],
          status: "pending",
        }),
      }),
    });

    await expect(
      bridge.startSession({
        source: API_STREAM_MONITOR_SOURCE,
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
    const bridge = createContractBridge({
      startSession: vi.fn().mockResolvedValue({
        ok: true,
        data: buildSessionSummary({
          session_id: "session-api-1",
          mode: "api_stream",
          input_path: API_STREAM_MONITOR_SOURCE.path,
          selected_detectors: ["video_metrics"],
          status: "done" as never,
        }),
      }),
    });

    await expect(
      bridge.startSession({
        source: API_STREAM_MONITOR_SOURCE,
        selectedDetectors: ["video_metrics"],
      }),
    ).rejects.toThrow("invalid bridge startSession response");
  });

  it("accepts a FastAPI-style cancelSession success payload", async () => {
    const bridge = createContractBridge({
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: buildSessionSummary({
          mode: "video_segments",
          input_path: "/data/streams/segments",
          status: "cancelling",
        }),
      }),
    });

    await expect(bridge.cancelSession("session-123")).resolves.toEqual({
      session_id: "session-123",
      mode: "video_segments",
      input_path: "/data/streams/segments",
      selected_detectors: ["video_blur"],
      status: "cancelling",
    });
  });

  it("normalizes a sparse readSession success payload into UI-safe collection defaults", async () => {
    const progress = buildSessionProgress({
      session_id: "session-sparse-read",
    });
    const bridge = createContractBridge({
      readSession: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          session: buildSessionSummary({
            session_id: "session-sparse-read",
            status: "running",
          }),
          progress,
        },
      }),
    });

    await expect(bridge.readSession("session-sparse-read")).resolves.toEqual({
      session: buildSessionSummary({
        session_id: "session-sparse-read",
        status: "running",
      }),
      progress,
      alerts: [],
      results: [],
      latest_result: null,
    });
  });

  it("rejects a cancelSession success envelope when it contains an invalid mode", async () => {
    const bridge = createContractBridge({
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: buildSessionSummary({
          mode: "remote_shell" as never,
          input_path: "/data/streams/segments",
          status: "cancelling",
        }),
      }),
    } as unknown as LocalBridge);

    await expect(bridge.cancelSession("session-123")).rejects.toThrow(
      "invalid bridge cancelSession response",
    );
  });

  it("accepts a null cancelSession success payload", async () => {
    const bridge = createContractBridge({
      cancelSession: vi.fn().mockResolvedValue({
        ok: true,
        data: null,
      }),
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
          ...API_STREAM_MONITOR_SOURCE,
          path: "https://example.com/live/playlist.m3u8",
        },
        currentItem: null,
      }),
    ).resolves.toBeNull();
  });
});
