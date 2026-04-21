// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createNormalizedBridge } from "../bridge/contract";
import type {
  LocalBridge,
  MonitorSource,
  SessionSnapshot,
  SessionSummary,
} from "../types";
import { useMonitoringSession } from "./useMonitoringSession";

const { mockBridge } = vi.hoisted(() => ({
  mockBridge: {
    listDetectors: vi.fn(),
    startSession: vi.fn(),
    readSession: vi.fn(),
    cancelSession: vi.fn(),
    resolvePlaybackSource: vi.fn(),
  } satisfies LocalBridge,
}));

vi.mock("../bridge", () => ({
  localBridge: createNormalizedBridge(mockBridge),
}));

const SOURCE: MonitorSource = {
  kind: "video_segments",
  path: "/data/streams/segments",
  access: "local_path",
};

const RUNNING_SESSION: SessionSummary = {
  session_id: "session-1",
  mode: "video_segments",
  input_path: "/data/streams/segments",
  selected_detectors: ["video_blur"],
  status: "running",
};

function makeSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    session: RUNNING_SESSION,
    progress: {
      session_id: "session-1",
      status: "running",
      processed_count: 1,
      total_count: 4,
      current_item: "segment_0001.ts",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-21 12:00:00",
    },
    alerts: [],
    results: [],
    latest_result: null,
    ...overrides,
  };
}

function HookProbe({ source = SOURCE }: { source?: MonitorSource }) {
  const state = useMonitoringSession({ source });

  return (
    <div>
      <button onClick={() => void state.startMonitoring(["video_blur"])}>Start</button>
      <button onClick={() => void state.endMonitoring()}>End</button>
      <dl>
        <dt>status</dt>
        <dd data-testid="monitoring-status">{state.monitoringSessionStatus}</dd>
        <dt>session</dt>
        <dd data-testid="session-status">{state.sessionSummary?.status ?? "none"}</dd>
        <dt>snapshot</dt>
        <dd data-testid="snapshot-status">{state.sessionSnapshot.session?.status ?? "none"}</dd>
        <dt>error</dt>
        <dd data-testid="session-error">{state.sessionError ?? "none"}</dd>
      </dl>
    </div>
  );
}

describe("useMonitoringSession lifecycle guards", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not issue repeated cancel requests while a previous cancel request is still pending", async () => {
    let resolveCancel: ((value: SessionSummary | null) => void) | null = null;

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCancel = resolve;
        }),
    );

    render(<HookProbe />);

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => {
      expect(screen.getByTestId("monitoring-status").textContent).toBe("running");
      expect(screen.getByTestId("snapshot-status").textContent).toBe("running");
    });

    fireEvent.click(screen.getByRole("button", { name: "End" }));
    fireEvent.click(screen.getByRole("button", { name: "End" }));
    fireEvent.click(screen.getByRole("button", { name: "End" }));

    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("session-error").textContent).toBe("none");
    });

    resolveCancel?.({
      ...RUNNING_SESSION,
      status: "cancelling",
    });
  });
});
