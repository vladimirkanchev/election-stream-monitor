/**
 * Hook-level coverage for api_stream monitoring-session polling semantics.
 *
 * The App polling suite owns the user-facing status wording. This file keeps
 * the hook-level reconnect, recovery, and terminal-state transitions explicit
 * without paying for full App rendering.
 */

// @vitest-environment jsdom

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  advancePollingTick,
  API_STREAM_RUNNING_SESSION,
  API_STREAM_SOURCE,
  getProbeState,
  makeApiStreamCompletedSnapshot,
  makeApiStreamFailedSnapshot,
  makeApiStreamSnapshot,
  mockBridge,
  startProbeMonitoring,
} from "./useMonitoringSession.test.helpers";

describe("useMonitoringSession api_stream polling semantics", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("keeps polling failures as a warning-only running state until a terminal snapshot arrives", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(API_STREAM_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeApiStreamSnapshot())
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(makeApiStreamSnapshot());

    await startProbeMonitoring(API_STREAM_SOURCE);
    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "running",
      sessionError:
        "The live stream dropped for a moment. Monitoring is trying to reconnect.",
    });
  });

  it("does not regress back to running after an idle-complete terminal snapshot settles", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(API_STREAM_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeApiStreamSnapshot())
      .mockResolvedValueOnce(makeApiStreamCompletedSnapshot())
      .mockResolvedValueOnce(makeApiStreamSnapshot())
      .mockResolvedValue(makeApiStreamSnapshot());

    await startProbeMonitoring(API_STREAM_SOURCE);
    await advancePollingTick();

    expect(getProbeState().sessionStatus).toBe("completed");

    await advancePollingTick();

    expect(mockBridge.readSession).toHaveBeenCalledTimes(2);
    expect(getProbeState()).toMatchObject({
      monitoringStatus: "completed",
      sessionStatus: "completed",
    });
  });

  it("can recover from reconnecting and still later settle on a terminal source failure", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(API_STREAM_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeApiStreamSnapshot())
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValueOnce(
        makeApiStreamSnapshot({
          progress: {
            session_id: API_STREAM_RUNNING_SESSION.session_id,
            status: "running",
            processed_count: 2,
            total_count: 4,
            current_item: "live-window-002",
            latest_result_detector: "video_blur",
            latest_result_detectors: ["video_blur"],
            alert_count: 0,
            last_updated_utc: "2026-04-04 09:30:02",
            status_reason: null,
            status_detail: null,
          },
        }),
      )
      .mockResolvedValueOnce(makeApiStreamFailedSnapshot())
      .mockResolvedValue(makeApiStreamFailedSnapshot());

    await startProbeMonitoring(API_STREAM_SOURCE);
    await advancePollingTick();

    expect(getProbeState().sessionError).toBe(
      "The live stream dropped for a moment. Monitoring is trying to reconnect.",
    );

    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });

    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "failed",
      sessionStatus: "failed",
      sessionError: "Monitoring could not reconnect to the live stream, so it has ended.",
    });
  });
});
