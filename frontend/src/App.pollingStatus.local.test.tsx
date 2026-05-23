/**
 * App-level polling coverage for local session transitions that are easiest to
 * validate through the composed shell.
 */

// @vitest-environment jsdom

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  makeSnapshot,
  mockBridge,
  setMockPlaybackSegmentStarts,
} from "./testing/appHarness";
import {
  RUNNING_SESSION,
  startLocalMonitoringFlow,
  waitForStatusLabel,
  waitForPollingTick,
} from "./testing/pollingStatusTestSupport";

/**
 * Programs one deterministic polling sequence so each scenario can focus on
 * the composed operator-visible result instead of bridge mock plumbing.
 */
function mockLocalPollingSequence(...snapshots: ReturnType<typeof makeSnapshot>[]) {
  vi.mocked(mockBridge.startSession).mockResolvedValue(RUNNING_SESSION);
  const readSession = vi.mocked(mockBridge.readSession);
  for (const snapshot of snapshots) {
    readSession.mockResolvedValueOnce(snapshot);
  }
  const finalSnapshot = snapshots[snapshots.length - 1];
  if (finalSnapshot) {
    readSession.mockResolvedValue(finalSnapshot);
  }
}

describe("App polling and status integration (local)", () => {
  it("updates status from polling and shows completed state", async () => {
    const completedSnapshot = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-04-02 10:00:04",
      },
    });
    mockLocalPollingSequence(makeSnapshot(), completedSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Completed");
    expect(
      screen.getByText("Monitoring finished successfully for the current source."),
    ).toBeTruthy();
  });

  it("shows raised-versus-visible alerts from the active backend snapshot in the operator shell", async () => {
    const runningSnapshotWithAlerts = makeSnapshot({
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "running",
        processed_count: 3,
        total_count: 4,
        current_item: "segment_0002.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 2,
        last_updated_utc: "2026-05-20 10:00:02",
      },
      alerts: [
        {
          session_id: RUNNING_SESSION.session_id,
          timestamp_utc: "2026-05-20 10:00:00",
          detector_id: "video_blur",
          title: "Visible postgres-backed alert",
          message: "This alert should already be visible to the operator.",
          severity: "warning",
          source_name: "segment_0001.ts",
          window_index: 0,
          window_start_sec: 1,
        },
        {
          session_id: RUNNING_SESSION.session_id,
          timestamp_utc: "2026-05-20 10:00:02",
          detector_id: "video_blur",
          title: "Hidden postgres-backed alert",
          message: "This alert should stay hidden until playback reaches it.",
          severity: "warning",
          source_name: "segment_0004.ts",
          window_index: 3,
          window_start_sec: 4,
        },
      ],
    });
    mockLocalPollingSequence(makeSnapshot(), runningSnapshotWithAlerts);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Running");
    expect(screen.getByText("1 visible now / 2 raised")).toBeTruthy();
    expect(
      screen.getByText("Visible now follows playback. Raised follows backend analysis."),
    ).toBeTruthy();
    expect(
      screen.getByText("This alert should already be visible to the operator."),
    ).toBeTruthy();
    expect(
      screen.queryByText("This alert should stay hidden until playback reaches it."),
    ).toBeNull();
  });

  it("explains when alerts have been raised but playback has not reached them yet", async () => {
    const runningSnapshotWithHiddenAlert = makeSnapshot({
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "running",
        processed_count: 3,
        total_count: 4,
        current_item: "segment_0002.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-05-20 10:00:02",
      },
      alerts: [
        {
          session_id: RUNNING_SESSION.session_id,
          timestamp_utc: "2026-05-20 10:00:02",
          detector_id: "video_blur",
          title: "Future alert",
          message: "This alert should stay hidden until playback reaches it.",
          severity: "warning",
          source_name: "segment_0004.ts",
          window_index: 3,
          window_start_sec: 4,
        },
      ],
    });
    mockLocalPollingSequence(makeSnapshot(), runningSnapshotWithHiddenAlert);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Running");
    expect(screen.getByText("0 visible now / 1 raised")).toBeTruthy();
    expect(
      screen.getByText(
        "Alerts have already been raised and will appear here as playback reaches them.",
      ),
    ).toBeTruthy();
  });

  it("keeps only playback-revealed local alerts visible after the session completes", async () => {
    const completedSnapshotWithLaterAlert = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 2,
        last_updated_utc: "2026-05-20 10:00:04",
      },
      alerts: [
        {
          session_id: RUNNING_SESSION.session_id,
          timestamp_utc: "2026-05-20 10:00:00",
          detector_id: "video_blur",
          title: "Earlier alert",
          message: "This alert was raised before the current playback item.",
          severity: "warning",
          source_name: "segment_0001.ts",
          window_index: 0,
          window_start_sec: 1,
        },
        {
          session_id: RUNNING_SESSION.session_id,
          timestamp_utc: "2026-05-20 10:00:03",
          detector_id: "video_blur",
          title: "Later alert",
          message: "This alert should still be visible after completion.",
          severity: "warning",
          source_name: "segment_0004.ts",
          window_index: 3,
          window_start_sec: 4,
        },
      ],
    });
    mockLocalPollingSequence(makeSnapshot(), completedSnapshotWithLaterAlert);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Completed");
    expect(screen.getByText("1 visible now / 2 raised")).toBeTruthy();
    expect(
      screen.getByText("Visible now follows playback. Raised follows backend analysis."),
    ).toBeTruthy();
    expect(
      screen.getByText("This alert was raised before the current playback item."),
    ).toBeTruthy();
    expect(screen.queryByText("This alert should still be visible after completion.")).toBeNull();
  });

  it("shows a warning when a local playlist completes with partial analysis", async () => {
    const partialCompletionSnapshot = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "completed",
        processed_count: 9,
        total_count: 10,
        current_item: "segment_0009.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-05-20 10:00:09",
        status_reason: "completed",
        status_detail: null,
      },
    });
    mockLocalPollingSequence(makeSnapshot(), partialCompletionSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Completed");
    expect(screen.getByText("Completed with gaps")).toBeTruthy();
    expect(
      screen.getByText(
        "Monitoring finished, but one or more local playlist segments were missing or could not be analyzed.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Only 9 of 10 local playlist segments were analyzed. One or more items were missing or unreadable.",
      ),
    ).toBeTruthy();
  });

  it("shows a short playback warning when the local playlist references more segments than monitoring analyzed", async () => {
    setMockPlaybackSegmentStarts({
      "segment_0000.ts": 0,
      "segment_0001.ts": 1,
      "segment_0002.ts": 2,
      "segment_0003.ts": 3,
      "segment_0004.ts": 4,
      "segment_0005.ts": 5,
      "segment_0006.ts": 6,
      "segment_0007.ts": 7,
      "segment_0008.ts": 8,
      "segment_0009.ts": 9,
    });

    const malformedPlaylistSnapshot = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: RUNNING_SESSION.session_id,
        status: "completed",
        processed_count: 9,
        total_count: 9,
        current_item: "segment_0009.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-05-20 10:00:09",
        status_reason: "completed",
        status_detail: null,
      },
    });
    mockLocalPollingSequence(makeSnapshot(), malformedPlaylistSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Completed");
    expect(screen.getByText("Playback warning")).toBeTruthy();
    expect(screen.getByText("Playlist has gaps. Playback may be incomplete.")).toBeTruthy();
  });
});
