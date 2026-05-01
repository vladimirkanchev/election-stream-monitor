/**
 * Hook-level coverage for local monitoring-session lifecycle behavior after
 * bridge-contract normalization.
 *
 * This suite keeps the cheaper local lifecycle and cancel-state matrix close
 * to the hook seam, where fake timers make polling checks stable and fast.
 */

// @vitest-environment jsdom

import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionSnapshot } from "../types";
import {
  advancePollingTick,
  getProbeState,
  LOCAL_RUNNING_SESSION,
  makeCancelledSnapshot,
  makeFailedSnapshot,
  makeLocalSnapshot,
  makeMissingSessionFailure,
  mockBridge,
  renderHookProbe,
  requestCancel,
  startProbeMonitoring,
} from "./useMonitoringSession.test.helpers";

describe("useMonitoringSession lifecycle guards", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not issue repeated cancel requests while a previous cancel request is still pending", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession).mockResolvedValue(makeLocalSnapshot());
    vi.mocked(mockBridge.cancelSession).mockImplementation(
      () =>
        new Promise(() => {}),
    );

    renderHookProbe();

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => {
      expect(getProbeState()).toMatchObject({
        monitoringStatus: "running",
        snapshotStatus: "running",
        sessionError: "none",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "End" }));
    fireEvent.click(screen.getByRole("button", { name: "End" }));
    fireEvent.click(screen.getByRole("button", { name: "End" }));

    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);
      expect(getProbeState().sessionError).toBe("none");
    });
  });
});

describe("useMonitoringSession local polling stability", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("keeps the last good session state when a polling read fails", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(makeLocalSnapshot());

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });
  });

  it("moves from cancelling to stopped after polling returns a cancelled snapshot", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValue(makeCancelledSnapshot());
    vi.mocked(mockBridge.cancelSession).mockResolvedValue({
      ...LOCAL_RUNNING_SESSION,
      status: "cancelling",
    });

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });

  it("stops polling after a cancelled terminal snapshot lands", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValueOnce(makeCancelledSnapshot())
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValue(makeLocalSnapshot());

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState().sessionStatus).toBe("cancelled");

    await advancePollingTick();

    expect(mockBridge.readSession).toHaveBeenCalledTimes(2);
    expect(getProbeState().sessionStatus).toBe("cancelled");
  });

  it("stops polling after a failed terminal snapshot lands", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValueOnce(makeFailedSnapshot())
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValue(makeLocalSnapshot());

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState().sessionStatus).toBe("failed");

    await advancePollingTick();

    expect(mockBridge.readSession).toHaveBeenCalledTimes(2);
    expect(getProbeState().sessionStatus).toBe("failed");
  });

  it("keeps the last good session state when polling returns session_not_found", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValueOnce(makeMissingSessionFailure())
      .mockResolvedValue(makeLocalSnapshot());

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });
  });

  it("keeps the started session active when the first read is temporarily missing", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeMissingSessionFailure())
      .mockResolvedValue(makeLocalSnapshot());

    renderHookProbe();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Start" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "none",
      sessionError: "none",
    });

    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });
  });

  it("recovers from a polling failure during cancelling and still settles on stopped", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockRejectedValueOnce(new Error("poll failed during cancel"))
      .mockResolvedValue(makeCancelledSnapshot());
    vi.mocked(mockBridge.cancelSession).mockResolvedValue({
      ...LOCAL_RUNNING_SESSION,
      status: "cancelling",
    });

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick(2);

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });

  it("keeps the last good ending state when a post-cancel poll reports session_not_found", async () => {
    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockResolvedValueOnce(makeMissingSessionFailure());
    vi.mocked(mockBridge.cancelSession).mockResolvedValue({
      ...LOCAL_RUNNING_SESSION,
      status: "cancelling",
    });

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick();

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "cancelling",
      sessionStatus: "cancelling",
      sessionError: "none",
    });
  });

  it("settles cleanly when an in-flight poll resolves after cancel is requested", async () => {
    let resolvePoll: ((value: SessionSnapshot) => void) | null = null;

    vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
    vi.mocked(mockBridge.readSession)
      .mockResolvedValueOnce(makeLocalSnapshot())
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePoll = resolve;
          }),
      );
    vi.mocked(mockBridge.cancelSession).mockResolvedValue({
      ...LOCAL_RUNNING_SESSION,
      status: "cancelling",
    });

    await startProbeMonitoring();
    await advancePollingTick();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");
    expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);

    expect(resolvePoll).not.toBeNull();
    await act(async () => {
      resolvePoll?.(makeCancelledSnapshot());
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getProbeState()).toMatchObject({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });
});
