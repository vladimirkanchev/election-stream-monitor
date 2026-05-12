/**
 * App-level polling coverage for local session transitions that are easiest to
 * validate through the composed shell.
 */

// @vitest-environment jsdom

import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeSnapshot, mockBridge } from "./testing/appHarness";
import {
  RUNNING_SESSION,
  startLocalMonitoringFlow,
  waitForStatusLabel,
  waitForPollingTick,
} from "./testing/pollingStatusTestSupport";

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
    vi.mocked(mockBridge.startSession).mockResolvedValue(RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(completedSnapshot)
      .mockResolvedValue(completedSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitForStatusLabel("Completed");
    expect(
      screen.getByText("Monitoring finished successfully for the current source."),
    ).toBeTruthy();
  });
});
