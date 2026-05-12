/**
 * Session-snapshot compatibility tests for malformed nested payloads that must
 * fail closed without corrupting the outer session shell.
 */

import { describe, expect, it } from "vitest";

import { normalizeSessionSnapshot } from "./contract";
import {
  readNormalizedSession,
} from "./contract.sessionSnapshotTestSupport";

describe("bridge contract session snapshot malformed nested payload handling", () => {
  it("keeps the session and valid collections when a readSession success envelope has malformed nested progress", async () => {
    await expect(
      readNormalizedSession(
        "session-progress-broken",
        {
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
        },
      ),
    ).resolves.toEqual({
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
