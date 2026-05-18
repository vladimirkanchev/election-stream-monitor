/**
 * Session-snapshot compatibility tests for alert/result normalization and
 * compatibility when nested collections are partially corrupt.
 */

import { describe, expect, it } from "vitest";

import { normalizeSessionSnapshot } from "./contract";

describe("bridge contract session snapshot collection compatibility", () => {
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
});
