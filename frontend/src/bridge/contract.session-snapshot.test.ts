import { describe, expect, it, vi } from "vitest";

import { createNormalizedBridge, normalizeSessionSnapshot, ok } from "./contract";

describe("bridge contract session snapshot compatibility", () => {
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

  it("keeps the session and valid collections when a readSession success envelope has malformed nested progress", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        ok({
          session: {
            session_id: "session-progress-broken",
            mode: "api_stream",
            input_path: "https://example.com/live/index.m3u8",
            selected_detectors: ["video_metrics"],
            status: "running",
          },
          progress: {
            session_id: "session-progress-broken",
            status: "running",
            processed_count: "3",
            total_count: 8,
            current_item: "live-window-003.ts",
            latest_result_detector: "video_metrics",
            latest_result_detectors: ["video_metrics"],
            alert_count: 1,
            last_updated_utc: "2026-04-22 09:10:00",
          },
          alerts: [],
          results: [],
          latest_result: null,
        }),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-progress-broken")).resolves.toEqual({
      session: {
        session_id: "session-progress-broken",
        mode: "api_stream",
        input_path: "https://example.com/live/index.m3u8",
        selected_detectors: ["video_metrics"],
        status: "running",
      },
      progress: null,
      alerts: [],
      results: [],
      latest_result: null,
    });
  });

  it("drops malformed alerts, results, and latest_result while keeping the rest of a valid snapshot", () => {
    expect(
      normalizeSessionSnapshot({
        session: {
          session_id: "session-partial-corruption",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics"],
          status: "running",
        },
        progress: {
          session_id: "session-partial-corruption",
          status: "running",
          processed_count: 3,
          total_count: 8,
          current_item: "live-window-003.ts",
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 1,
          last_updated_utc: "2026-04-22 09:15:00",
          status_reason: "running",
          status_detail: null,
        },
        alerts: [
          {
            session_id: "session-partial-corruption",
            timestamp_utc: "2026-04-22 09:15:00",
            detector_id: "video_metrics",
            title: "Valid alert",
            message: "Still valid",
            severity: "warning",
            source_name: "live-window-003.ts",
            window_index: 3,
            window_start_sec: 6.0,
          },
          { detector_id: "broken" },
        ],
        results: [
          {
            session_id: "session-partial-corruption",
            detector_id: "video_metrics",
            payload: { black_ratio: 0.4 },
          },
          {
            session_id: "session-partial-corruption",
            detector_id: "video_metrics",
            payload: null,
          },
        ],
        latest_result: {
          session_id: "session-partial-corruption",
          detector_id: "video_metrics",
          payload: null,
        },
      }),
    ).toEqual({
      session: {
        session_id: "session-partial-corruption",
        mode: "api_stream",
        input_path: "https://example.com/live/index.m3u8",
        selected_detectors: ["video_metrics"],
        status: "running",
      },
      progress: {
        session_id: "session-partial-corruption",
        status: "running",
        processed_count: 3,
        total_count: 8,
        current_item: "live-window-003.ts",
        latest_result_detector: "video_metrics",
        latest_result_detectors: ["video_metrics"],
        alert_count: 1,
        last_updated_utc: "2026-04-22 09:15:00",
        status_reason: "running",
        status_detail: null,
      },
      alerts: [
        {
          session_id: "session-partial-corruption",
          timestamp_utc: "2026-04-22 09:15:00",
          detector_id: "video_metrics",
          title: "Valid alert",
          message: "Still valid",
          severity: "warning",
          source_name: "live-window-003.ts",
          window_index: 3,
          window_start_sec: 6.0,
        },
      ],
      results: [
        {
          session_id: "session-partial-corruption",
          detector_id: "video_metrics",
          payload: { black_ratio: 0.4 },
        },
      ],
      latest_result: null,
    });
  });

  it("keeps cancelled snapshot lifecycle detail fields when they are present", () => {
    expect(
      normalizeSessionSnapshot({
        session: {
          session_id: "session-cancelled-1",
          mode: "video_segments",
          input_path: "/tmp/segments",
          selected_detectors: ["video_blur"],
          status: "cancelled",
        },
        progress: {
          session_id: "session-cancelled-1",
          status: "cancelled",
          processed_count: 2,
          total_count: 10,
          current_item: null,
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-22 09:00:00",
          status_reason: "cancelled_by_user",
          status_detail: "Stop requested from the desktop UI",
        },
        alerts: [],
        results: [],
        latest_result: null,
      }).progress,
    ).toMatchObject({
      status: "cancelled",
      status_reason: "cancelled_by_user",
      status_detail: "Stop requested from the desktop UI",
    });
  });

  it("keeps completed-with-warning api_stream lifecycle fields for idle poll exhaustion", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        ok({
          session: {
            session_id: "session-idle-1",
            mode: "api_stream",
            input_path: "https://example.com/live/index.m3u8",
            selected_detectors: ["video_metrics"],
            status: "completed",
          },
          progress: {
            session_id: "session-idle-1",
            status: "completed",
            processed_count: 5,
            total_count: 5,
            current_item: null,
            latest_result_detector: "video_metrics",
            latest_result_detectors: ["video_metrics"],
            alert_count: 0,
            last_updated_utc: "2026-04-22 09:05:00",
            status_reason: "idle_poll_budget_exhausted",
            status_detail: "Idle poll budget exhausted",
          },
          alerts: [],
          results: [],
          latest_result: null,
        }),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-idle-1")).resolves.toMatchObject({
      session: {
        session_id: "session-idle-1",
        status: "completed",
      },
      progress: {
        status: "completed",
        status_reason: "idle_poll_budget_exhausted",
        status_detail: "Idle poll budget exhausted",
      },
    });
  });

  it("fails closed on invalid nested enum values inside readSession snapshots", () => {
    expect(
      normalizeSessionSnapshot({
        session: {
          session_id: "session-invalid-enums",
          mode: "api_stream",
          input_path: "https://example.com/live/index.m3u8",
          selected_detectors: ["video_metrics"],
          status: "running",
        },
        progress: {
          session_id: "session-invalid-enums",
          status: "done",
          processed_count: 2,
          total_count: 4,
          current_item: "live-window-002.ts",
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_metrics"],
          alert_count: 1,
          last_updated_utc: "2026-04-22 10:10:00",
          status_reason: "running",
          status_detail: null,
        },
        alerts: [
          {
            session_id: "session-invalid-enums",
            timestamp_utc: "2026-04-22 10:10:00",
            detector_id: "video_metrics",
            title: "Alert",
            message: "Broken severity should be dropped",
            severity: "critical",
            source_name: "live-window-002.ts",
          },
        ],
        results: [],
        latest_result: null,
      }),
    ).toEqual({
      session: {
        session_id: "session-invalid-enums",
        mode: "api_stream",
        input_path: "https://example.com/live/index.m3u8",
        selected_detectors: ["video_metrics"],
        status: "running",
      },
      progress: null,
      alerts: [],
      results: [],
      latest_result: null,
    });
  });
});
