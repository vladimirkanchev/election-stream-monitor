/**
 * Session-snapshot compatibility tests for required top-level shape and valid
 * lifecycle field preservation.
 */

import { describe, expect, it } from "vitest";

import { normalizeSessionSnapshot } from "./contract";
import {
  readNormalizedSession,
} from "./contract.sessionSnapshotTestSupport";

describe("bridge contract session snapshot shape compatibility", () => {
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
    await expect(
      readNormalizedSession(
        "session-123",
        {
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
        },
      ),
    ).resolves.toEqual({
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
    await expect(
      readNormalizedSession(
        "session-456",
        {
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
            status_detail:
              "api_stream reconnect budget exhausted: upstream returned HTTP 503",
          },
        },
      ),
    ).resolves.toEqual({
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
        status_detail:
          "api_stream reconnect budget exhausted: upstream returned HTTP 503",
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
          status_detail:
            "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
        },
        alerts: [],
        results: [],
        latest_result: null,
      }).progress,
    ).toMatchObject({
      status_reason: "source_unreachable",
      status_detail:
        "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
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
    await expect(
      readNormalizedSession(
        "session-idle-1",
        {
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
        },
      ),
    ).resolves.toMatchObject({
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
});
