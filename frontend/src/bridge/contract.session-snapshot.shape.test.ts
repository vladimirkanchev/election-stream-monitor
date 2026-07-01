/**
 * Session-snapshot compatibility tests for the bridge normalization contract.
 *
 * The suite keeps the required top-level shape stable and verifies that
 * lifecycle fields, latest-only progress, and ordered result history survive
 * normalization without overfitting timestamp formatting details.
 */

import { describe, expect, it } from "vitest";

import { normalizeSessionSnapshot } from "./contract";
import {
  readNormalizedSession,
} from "./contract.sessionSnapshotTestSupport";

const PROGRESS_CONTRACT_KEYS = [
  "alert_count",
  "current_item",
  "last_updated_utc",
  "latest_result_detector",
  "latest_result_detectors",
  "processed_count",
  "session_id",
  "status",
  "status_detail",
  "status_reason",
  "total_count",
].sort();

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

  it("keeps the frontend-visible snapshot shape stable when ordered results come from the store seam", () => {
    const normalized = normalizeSessionSnapshot({
      session: {
        session_id: "session-store-results",
        mode: "video_segments",
        input_path: "/tmp/segments",
        selected_detectors: ["video_metrics", "video_blur"],
        status: "running",
      },
      progress: {
        session_id: "session-store-results",
        status: "running",
        processed_count: 2,
        total_count: 8,
        current_item: "segment_0001.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_metrics", "video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-07-01 10:00:05",
        status_reason: "running",
        status_detail: null,
      },
      alerts: [],
      results: [
        {
          session_id: "session-store-results",
          detector_id: "video_metrics",
          payload: {
            timestamp_utc: "2026-07-01 10:00:00",
            source_name: "segment_0000.ts",
            window_index: 0,
            black_ratio: 0.12,
          },
        },
        {
          session_id: "session-store-results",
          detector_id: "video_blur",
          payload: {
            timestamp_utc: "2026-07-01 10:00:00",
            source_name: "segment_0001.ts",
            window_index: 1,
            blur_score: 0.91,
          },
        },
      ],
      latest_result: {
        session_id: "session-store-results",
        detector_id: "video_blur",
        payload: {
          timestamp_utc: "2026-07-01 10:00:00",
          source_name: "segment_0001.ts",
          window_index: 1,
          blur_score: 0.91,
        },
      },
    });

    expect(Object.keys(normalized)).toEqual([
      "session",
      "progress",
      "alerts",
      "results",
      "latest_result",
    ]);
    expect(normalized.results.map((row) => row.detector_id)).toEqual([
      "video_metrics",
      "video_blur",
    ]);
    expect(normalized.latest_result).toEqual(normalized.results.at(-1) ?? null);
    expect(normalized.latest_result?.payload).toMatchObject({
      source_name: "segment_0001.ts",
      blur_score: 0.91,
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

  it("keeps the polling progress contract stable without depending on timestamp formatting", async () => {
    const snapshot = await readNormalizedSession(
      "session-polling-1",
      {
        session: {
          session_id: "session-polling-1",
          mode: "video_segments",
          input_path: "/tmp/segments",
          selected_detectors: ["video_blur", "video_metrics"],
          status: "running",
        },
        progress: {
          session_id: "session-polling-1",
          status: "running",
          processed_count: 7,
          total_count: 12,
          current_item: "segment_0007.ts",
          latest_result_detector: "video_metrics",
          latest_result_detectors: ["video_blur", "video_metrics"],
          alert_count: 2,
          last_updated_utc: "2026-06-30T14:15:16.789123+03:00",
          status_reason: "running",
          status_detail: null,
        },
      },
    );

    expect(snapshot).toMatchObject({
      session: {
        session_id: "session-polling-1",
        status: "running",
      },
      progress: {
        session_id: "session-polling-1",
        status: "running",
        processed_count: 7,
        total_count: 12,
        current_item: "segment_0007.ts",
        latest_result_detector: "video_metrics",
        latest_result_detectors: ["video_blur", "video_metrics"],
        alert_count: 2,
        status_reason: "running",
        status_detail: null,
      },
    });
    expect(snapshot.progress).not.toBeNull();
    expect(typeof snapshot.progress?.last_updated_utc).toBe("string");
    expect(Object.keys(snapshot.progress ?? {}).sort()).toEqual(PROGRESS_CONTRACT_KEYS);
  });
});
