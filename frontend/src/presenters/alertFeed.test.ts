/**
 * Presenter-level coverage for the playback-aware alert feed filters and
 * timestamp labels shown to the operator.
 */

import { describe, expect, it } from "vitest";

import type { AlertEvent } from "../types";
import { buildAlertFeedItems, filterAlertsForPlayback } from "./alertFeed";

/**
 * Creates a minimal alert payload and lets each case vary only the playback
 * fields relevant to the current visibility rule.
 */
function buildAlert(overrides: Partial<AlertEvent> = {}): AlertEvent {
  return {
    session_id: "s1",
    timestamp_utc: "2026-04-02 10:00:00",
    detector_id: "video_blur",
    title: "Blur warning",
    message: "default",
    severity: "warning",
    source_name: "clip.mp4 @ 00:00",
    window_index: 0,
    ...overrides,
  };
}

/**
 * Projects the visible source names from the playback filter so the tests can
 * assert ordering and reveal boundaries without repeating the same mapping.
 */
function visibleAlertSources(
  args: Parameters<typeof filterAlertsForPlayback>[0],
) {
  return filterAlertsForPlayback(args).map((alert) => alert.source_name);
}

describe("filterAlertsForPlayback", () => {
  it("reveals mp4 alerts only after playback reaches their second", () => {
    const alerts: AlertEvent[] = [
      buildAlert({
        message: "first",
        source_name: "clip.mp4 @ 00:00",
        window_start_sec: 0,
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:01",
        message: "second",
        source_name: "clip.mp4 @ 00:01",
        window_index: 1,
        window_start_sec: 1,
      }),
    ];

    expect(
      filterAlertsForPlayback({
        alerts,
        sourceKind: "video_files",
        playbackTime: 0.4,
        playbackDuration: 10,
        playbackLive: false,
        totalAnalysisCount: 10,
        currentPlaybackItem: null,
        segmentStartTimes: {},
      }),
    ).toHaveLength(1);

    expect(
      filterAlertsForPlayback({
        alerts,
        sourceKind: "video_files",
        playbackTime: 1.2,
        playbackDuration: 10,
        playbackLive: false,
        totalAnalysisCount: 10,
        currentPlaybackItem: null,
        segmentStartTimes: {},
      }),
    ).toHaveLength(2);
  });

  it("reveals segment alerts by playback-aligned slice count", () => {
    const alerts: AlertEvent[] = [
      buildAlert({
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "first",
        source_name: "segment_0001.ts",
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:01",
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "second",
        source_name: "segment_0002.ts",
        window_index: 1,
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:02",
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "third",
        source_name: "segment_0003.ts",
        window_index: 2,
      }),
    ];

    expect(
      visibleAlertSources({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 1.1,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: "segment_0001.ts",
        segmentStartTimes: {
          "segment_0001.ts": 1,
          "segment_0002.ts": 2,
          "segment_0003.ts": 3,
        },
      }),
    ).toEqual(["segment_0001.ts"]);

    expect(
      visibleAlertSources({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 2.2,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: "segment_0002.ts",
        segmentStartTimes: {
          "segment_0001.ts": 1,
          "segment_0002.ts": 2,
          "segment_0003.ts": 3,
        },
      }),
    ).toEqual(["segment_0001.ts", "segment_0002.ts"]);
  });

  it("keeps segment alerts hidden until the current playback item is known", () => {
    const alerts: AlertEvent[] = [buildAlert({ source_name: "segment_0001.ts" })];

    expect(
      filterAlertsForPlayback({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 0.5,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: null,
        segmentStartTimes: {},
      }),
    ).toEqual([]);
  });

  it("still reveals segment alerts from segment timing when the current item is unknown", () => {
    const alerts: AlertEvent[] = [
      buildAlert({
        detector_id: "video_metrics",
        title: "Black screen detected",
        source_name: "segment_0001.ts",
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:01",
        detector_id: "video_metrics",
        title: "Black screen detected",
        source_name: "segment_0002.ts",
        window_index: 1,
      }),
    ];

    expect(
      visibleAlertSources({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 1.1,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: null,
        segmentStartTimes: {
          "segment_0001.ts": 1,
          "segment_0002.ts": 2,
        },
      }),
    ).toEqual(["segment_0001.ts"]);
  });

  it("reveals all alerts immediately during live playback", () => {
    const alerts: AlertEvent[] = [
      buildAlert({ message: "live-first", source_name: "live-window-001" }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:01",
        message: "live-second",
        source_name: "live-window-002",
        window_index: 1,
      }),
    ];

    expect(
      filterAlertsForPlayback({
        alerts,
        sourceKind: "api_stream",
        playbackTime: 0.2,
        playbackDuration: null,
        playbackLive: true,
        totalAnalysisCount: 2,
        currentPlaybackItem: "live-window-001",
        segmentStartTimes: {},
      }),
    ).toEqual(alerts);
  });

  it("reveals segment alerts exactly at their mapped playback boundary", () => {
    const alerts: AlertEvent[] = [
      buildAlert({
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "boundary",
        source_name: "segment_0002.ts",
        window_index: 1,
      }),
    ];

    expect(
      visibleAlertSources({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 2.0,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: "segment_0002.ts",
        segmentStartTimes: {
          "segment_0001.ts": 1,
          "segment_0002.ts": 2,
        },
      }),
    ).toEqual(["segment_0002.ts"]);
  });

  it("falls back to segment numbering when a segment start map is not available", () => {
    const alerts: AlertEvent[] = [
      buildAlert({
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "first",
        source_name: "segment_0001.ts",
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:01",
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "second",
        source_name: "segment_0002.ts",
        window_index: 1,
      }),
      buildAlert({
        timestamp_utc: "2026-04-02 10:00:02",
        detector_id: "video_metrics",
        title: "Black screen detected",
        message: "third",
        source_name: "segment_0003.ts",
        window_index: 2,
      }),
    ];

    expect(
      visibleAlertSources({
        alerts,
        sourceKind: "video_segments",
        playbackTime: 0.1,
        playbackDuration: 6,
        playbackLive: false,
        totalAnalysisCount: 6,
        currentPlaybackItem: "segment_0002.ts",
        segmentStartTimes: {},
      }),
    ).toEqual(["segment_0001.ts", "segment_0002.ts"]);
  });

  it("uses playback moment labels in feed items", () => {
    const segmentItem = buildAlertFeedItems(
      [
        buildAlert({
          message: "segment",
          source_name: "segment_0206.ts",
          window_index: 206,
        }),
      ],
      [],
      "video_segments",
      {
        "segment_0206.ts": 206,
      },
    )[0];

    const fileItem = buildAlertFeedItems(
      [
        buildAlert({
          message: "file",
          source_name: "clip.mp4 @ 00:12",
          window_start_sec: 12,
        }),
      ],
      [],
      "video_files",
      {},
    )[0];

    if (!segmentItem || !fileItem) {
      throw new Error("Expected alert feed items to be present");
    }

    expect(segmentItem.timestampLabel).toBe("03:26");
    expect(fileItem.timestampLabel).toBe("00:12");
  });
});
