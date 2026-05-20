/**
 * App-level polling coverage for local session transitions that are easiest to
 * validate through the composed shell.
 */

// @vitest-environment jsdom

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeSnapshot, mockBridge } from "./testing/appHarness";
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
    expect(screen.getByText("1 shown / 2 raised")).toBeTruthy();
    expect(
      screen.getByText("Shown follows playback. Raised follows backend analysis."),
    ).toBeTruthy();
    expect(
      screen.getByText("This alert should already be visible to the operator."),
    ).toBeTruthy();
    expect(
      screen.queryByText("This alert should stay hidden until playback reaches it."),
    ).toBeNull();
  });
});
