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

  it("raises a typed bridge error when cancelSession returns an explicit backend failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_CANCEL_FAILED",
          "Session cancel request failed",
          "No persisted session snapshot found for session_id=session-123",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-123",
          },
        ),
      ),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_CANCEL_FAILED",
      message: "Session cancel request failed",
      details: "No persisted session snapshot found for session_id=session-123",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-123",
    });
  });

  it("preserves invalid cancel-state failures as typed bridge transport errors", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_CANCEL_FAILED",
          "Session cancel request failed",
          "Session session-123 is already completed.",
          {
            backend_error_code: "cancel_failed",
            status_reason: "cancel_failed",
            status_detail: "Session session-123 is already completed.",
          },
        ),
      ),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_CANCEL_FAILED",
      backendErrorCode: "cancel_failed",
      statusReason: "cancel_failed",
      statusDetail: "Session session-123 is already completed.",
    });
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

  it("normalizes a terminal completed session snapshot from the bridge", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        ok({
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
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-123")).resolves.toEqual({
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
    });
  });

  it("normalizes a terminal failed session snapshot from the bridge without losing lifecycle details", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        ok({
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
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-456")).resolves.toEqual({
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
    });
  });

  it("raises a typed bridge error when readSession returns a missing-session failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-123",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-123",
          },
        ),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_READ_FAILED",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-123",
    });
  });

  it("preserves typed lifecycle metadata for explicit readSession bridge failures", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-456",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-456",
          },
        ),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-456")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_READ_FAILED",
      message: "Session read request failed",
      details: "No persisted session snapshot found for session_id=session-456",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-456",
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
          status_reason: "source_unreachable",
          status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
        },
        alerts: [],
        results: [],
        latest_result: null,
      }).progress,
    ).toMatchObject({
      status_reason: "source_unreachable",
      status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
    });
  });

  it("normalizes a real FastAPI-style session snapshot payload without losing fields", () => {
    expect(
      normalizeSessionSnapshot({
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
      }),
    ).toEqual({
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

  it("keeps optional backend error metadata on typed bridge failures", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn().mockResolvedValue(
        fail(
          "PLAYBACK_SOURCE_RESOLUTION_FAILED",
          "Playback source resolution failed",
          "backend reported a structured error",
          {
            backend_error_code: "playback_unavailable",
            status_reason: "playback_unavailable",
            status_detail: "Renderer-safe playback source could not be prepared",
          },
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
      backendErrorCode: "playback_unavailable",
      statusReason: "playback_unavailable",
      statusDetail: "Renderer-safe playback source could not be prepared",
    });
  });
});
