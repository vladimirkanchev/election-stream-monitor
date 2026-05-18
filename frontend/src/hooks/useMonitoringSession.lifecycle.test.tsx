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

function mockRunningLocalPolling(...responses: SessionSnapshot[]) {
  vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
  const readSession = vi.mocked(mockBridge.readSession);
  for (const response of responses) {
    readSession.mockResolvedValueOnce(response);
  }
  const lastResponse = responses[responses.length - 1];
  if (lastResponse) {
    readSession.mockResolvedValue(lastResponse);
  }
}

/**
 * Keeps state-shape assertions compact in this lifecycle suite, where the
 * contract is about coarse hook transitions rather than every returned field.
 */
function expectProbeState(expected: {
  monitoringStatus?: string;
  sessionStatus?: string;
  snapshotStatus?: string;
  sessionError?: string;
}) {
  expect(getProbeState()).toMatchObject(expected);
}

/**
 * Sets the cancel bridge reply to the canonical in-flight cancelling summary
 * used by the local hook tests.
 */
function mockCancellingSessionSummary() {
  vi.mocked(mockBridge.cancelSession).mockResolvedValue({
    ...LOCAL_RUNNING_SESSION,
    status: "cancelling",
  });
}

/**
 * Seeds the initial local polling responses after `startSession` succeeds.
 *
 * Unlike `mockRunningLocalPolling`, this helper intentionally leaves the final
 * default read behavior unset so individual tests can append their own steady
 * state or failure behavior.
 */
function mockStartThenRead(...responses: Array<SessionSnapshot | ReturnType<typeof makeMissingSessionFailure>>) {
  vi.mocked(mockBridge.startSession).mockResolvedValue(LOCAL_RUNNING_SESSION);
  const readSession = vi.mocked(mockBridge.readSession);
  for (const response of responses) {
    readSession.mockResolvedValueOnce(response);
  }
}

describe("useMonitoringSession lifecycle guards", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not issue repeated cancel requests while a previous cancel request is still pending", async () => {
    mockRunningLocalPolling(makeLocalSnapshot());
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
      expectProbeState({ sessionError: "none" });
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
    mockStartThenRead(makeLocalSnapshot());
    vi.mocked(mockBridge.readSession)
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
    mockRunningLocalPolling(makeLocalSnapshot(), makeCancelledSnapshot());
    mockCancellingSessionSummary();

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick();

    expectProbeState({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });

  it("stops polling after a cancelled terminal snapshot lands", async () => {
    mockRunningLocalPolling(
      makeLocalSnapshot(),
      makeCancelledSnapshot(),
      makeLocalSnapshot(),
    );

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState().sessionStatus).toBe("cancelled");

    await advancePollingTick();

    expect(mockBridge.readSession).toHaveBeenCalledTimes(2);
    expect(getProbeState().sessionStatus).toBe("cancelled");
  });

  it("stops polling after a failed terminal snapshot lands", async () => {
    mockRunningLocalPolling(
      makeLocalSnapshot(),
      makeFailedSnapshot(),
      makeLocalSnapshot(),
    );

    await startProbeMonitoring();
    await advancePollingTick();

    expect(getProbeState().sessionStatus).toBe("failed");

    await advancePollingTick();

    expect(mockBridge.readSession).toHaveBeenCalledTimes(2);
    expect(getProbeState().sessionStatus).toBe("failed");
  });

  it("keeps the last good session state when polling returns session_not_found", async () => {
    mockStartThenRead(makeLocalSnapshot(), makeMissingSessionFailure());
    vi.mocked(mockBridge.readSession)
      .mockResolvedValue(makeLocalSnapshot());

    await startProbeMonitoring();
    await advancePollingTick();

    expectProbeState({
      monitoringStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });
  });

  it("keeps the started session active when the first read is temporarily missing", async () => {
    mockStartThenRead(makeMissingSessionFailure());
    vi.mocked(mockBridge.readSession).mockResolvedValue(makeLocalSnapshot());

    renderHookProbe();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Start" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expectProbeState({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "none",
      sessionError: "none",
    });

    await advancePollingTick();

    expectProbeState({
      monitoringStatus: "running",
      sessionStatus: "running",
      snapshotStatus: "running",
      sessionError: "none",
    });
  });

  it("recovers from a polling failure during cancelling and still settles on stopped", async () => {
    mockStartThenRead(makeLocalSnapshot());
    vi.mocked(mockBridge.readSession)
      .mockRejectedValueOnce(new Error("poll failed during cancel"))
      .mockResolvedValue(makeCancelledSnapshot());
    mockCancellingSessionSummary();

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick(2);

    expectProbeState({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });

  it("keeps the last good ending state when a post-cancel poll reports session_not_found", async () => {
    mockStartThenRead(makeLocalSnapshot(), makeMissingSessionFailure());
    mockCancellingSessionSummary();

    await startProbeMonitoring();

    await requestCancel();
    expect(getProbeState().sessionStatus).toBe("cancelling");

    await advancePollingTick();

    expectProbeState({ sessionStatus: "cancelling", sessionError: "none" });
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
    mockCancellingSessionSummary();

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

    expectProbeState({
      monitoringStatus: "cancelled",
      sessionStatus: "cancelled",
      snapshotStatus: "cancelled",
    });
  });
});
