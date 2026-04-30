/**
 * Shared monitoring-hook test fixtures and probe helpers.
 *
 * The monitoring hook coverage is intentionally split by responsibility, so
 * the common bridge mock, probe renderer, and snapshot builders live here
 * instead of being duplicated across the lifecycle and api_stream suites.
 */

import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, vi } from "vitest";

import { createNormalizedBridge, fail } from "../bridge/contract";
import type {
  LocalBridge,
  MonitorSource,
  SessionProgress,
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

export { mockBridge };

export const LOCAL_SOURCE: MonitorSource = {
  kind: "video_segments",
  path: "/data/streams/segments",
  access: "local_path",
};

export const API_STREAM_SOURCE: MonitorSource = {
  kind: "api_stream",
  path: "https://example.com/live/playlist.m3u8",
  access: "api_stream",
};

export const LOCAL_RUNNING_SESSION: SessionSummary = {
  session_id: "session-1",
  mode: "video_segments",
  input_path: "/data/streams/segments",
  selected_detectors: ["video_blur"],
  status: "running",
};

export const API_STREAM_RUNNING_SESSION: SessionSummary = {
  session_id: "session-api-1",
  mode: "api_stream",
  input_path: "https://example.com/live/playlist.m3u8",
  selected_detectors: ["video_blur"],
  status: "running",
};

// Session snapshots are repeated throughout the lifecycle and api_stream
// suites, so this helper keeps them consistent while still allowing focused
// per-test overrides.
function buildSnapshot(
  session: SessionSummary,
  progress: SessionProgress,
  overrides: Partial<SessionSnapshot> = {},
): SessionSnapshot {
  return {
    session,
    progress,
    alerts: [],
    results: [],
    latest_result: null,
    ...overrides,
  };
}

export function makeLocalSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return buildSnapshot(
    LOCAL_RUNNING_SESSION,
    {
      session_id: LOCAL_RUNNING_SESSION.session_id,
      status: "running",
      processed_count: 1,
      total_count: 4,
      current_item: "segment_0001.ts",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-21 12:00:00",
    },
    overrides,
  );
}

export function makeCancelledSnapshot(): SessionSnapshot {
  return makeLocalSnapshot({
    session: {
      ...LOCAL_RUNNING_SESSION,
      status: "cancelled",
    },
    progress: {
      session_id: LOCAL_RUNNING_SESSION.session_id,
      status: "cancelled",
      processed_count: 1,
      total_count: 4,
      current_item: null,
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-21 12:00:01",
      status_reason: "cancel_requested",
      status_detail: "Cancellation requested by client",
    },
  });
}

export function makeFailedSnapshot(): SessionSnapshot {
  return makeLocalSnapshot({
    session: {
      ...LOCAL_RUNNING_SESSION,
      status: "failed",
    },
    progress: {
      session_id: LOCAL_RUNNING_SESSION.session_id,
      status: "failed",
      processed_count: 1,
      total_count: 4,
      current_item: "segment_0001.ts",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-21 12:10:01",
      status_reason: "terminal_failure",
      status_detail: "session runtime exceeded max duration",
    },
  });
}

export function makeMissingSessionFailure(): SessionSnapshot {
  return fail(
    "SESSION_READ_FAILED",
    "Session read request failed",
    "No persisted session snapshot found for session_id=session-1",
    {
      backend_error_code: "session_not_found",
      status_reason: "session_not_found",
      status_detail: "No persisted session snapshot found for session_id=session-1",
    },
  ) as unknown as SessionSnapshot;
}

export function makeApiStreamSnapshot(
  overrides: Partial<SessionSnapshot> = {},
): SessionSnapshot {
  return buildSnapshot(
    API_STREAM_RUNNING_SESSION,
    {
      session_id: API_STREAM_RUNNING_SESSION.session_id,
      status: "running",
      processed_count: 1,
      total_count: 4,
      current_item: "live-window-001",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-04 09:00:00",
      status_reason: null,
      status_detail: null,
    },
    overrides,
  );
}

export function makeApiStreamCompletedSnapshot(): SessionSnapshot {
  return makeApiStreamSnapshot({
    session: {
      ...API_STREAM_RUNNING_SESSION,
      status: "completed",
    },
    progress: {
      session_id: API_STREAM_RUNNING_SESSION.session_id,
      status: "completed",
      processed_count: 2,
      total_count: 4,
      current_item: "live-window-002",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-04 09:22:03",
      status_reason: "idle_poll_budget_exhausted",
      status_detail: "Idle poll budget exhausted",
    },
  });
}

export function makeApiStreamFailedSnapshot(): SessionSnapshot {
  return makeApiStreamSnapshot({
    session: {
      ...API_STREAM_RUNNING_SESSION,
      status: "failed",
    },
    progress: {
      session_id: API_STREAM_RUNNING_SESSION.session_id,
      status: "failed",
      processed_count: 2,
      total_count: 4,
      current_item: "live-window-002",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-04 09:30:04",
      status_reason: "source_unreachable",
      status_detail:
        "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
    },
  });
}

function HookProbe({ source = LOCAL_SOURCE }: { source?: MonitorSource }) {
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

export function renderHookProbe(source: MonitorSource = LOCAL_SOURCE) {
  return render(<HookProbe source={source} />);
}

// Starting monitoring is asynchronous because the hook issues a start request
// and then reads the first snapshot immediately.
export async function startProbeMonitoring(source: MonitorSource = LOCAL_SOURCE) {
  renderHookProbe(source);

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(getProbeState()).toMatchObject({
    monitoringStatus: "running",
    sessionStatus: "running",
    snapshotStatus: "running",
  });
}

// Polling tests advance the real hook interval, but do it under fake timers so
// the suites stay deterministic and cheap.
export async function advancePollingTick(count = 1) {
  for (let index = 0; index < count; index += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
  }
}

export async function requestCancel() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "End" }));
    await Promise.resolve();
    await Promise.resolve();
  });
}

// Keep probe reads centralized so the tests describe behavior in state terms
// instead of repeatedly reaching into the DOM.
export function getProbeState() {
  return {
    monitoringStatus: screen.getByTestId("monitoring-status").textContent,
    sessionStatus: screen.getByTestId("session-status").textContent,
    snapshotStatus: screen.getByTestId("snapshot-status").textContent,
    sessionError: screen.getByTestId("session-error").textContent,
  };
}
