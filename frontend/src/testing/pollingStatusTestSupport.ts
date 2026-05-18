/**
 * Shared setup and polling helpers for App-level session status tests.
 *
 * These tests intentionally stay one seam above the hook layer so they can
 * validate composed operator wording while still reusing one small harness.
 */

import { screen, waitFor } from "@testing-library/react";
import { expect, vi } from "vitest";

import type { SessionSummary } from "../types";
import {
  enterApiStreamSource,
  enterLocalSource,
  makeSnapshot,
  mockBridge,
  renderApp,
  RUNNING_SESSION,
  startMonitoring,
  toggleFirstDetector,
} from "./appHarness";

export const API_STREAM_URL = "https://example.com/live/playlist.m3u8";
export const POLLING_TICK_MS = 1100;
export const RUNNING_STATUS_LABEL = "Running";

type PollSnapshot = ReturnType<typeof makeSnapshot>;
type PollResult = PollSnapshot | Error;

const BASE_API_STREAM_PROGRESS = {
  processed_count: 1,
  total_count: 4,
  current_item: "live-window-001",
  latest_result_detector: "video_blur",
  latest_result_detectors: ["video_blur"],
  alert_count: 0,
  last_updated_utc: "2026-04-04 09:00:00",
  status_reason: null,
  status_detail: null,
};

/**
 * Builds the canonical running `api_stream` session shape used by the polling
 * UI tests, with narrow overrides for the cases under test.
 */
export function makeApiStreamSession(
  overrides: Partial<SessionSummary> = {},
): SessionSummary {
  return {
    session_id: "session-api-live",
    mode: "api_stream",
    input_path: API_STREAM_URL,
    selected_detectors: ["video_blur"],
    status: "running",
    ...overrides,
  };
}

/**
 * Creates one polling snapshot on top of the shared live-session baseline so
 * tests can override only the progress fields they care about.
 */
export function makeApiStreamSnapshot(args: {
  session?: Partial<SessionSummary>;
  progress?: Partial<NonNullable<PollSnapshot["progress"]>>;
} = {}) {
  const session = makeApiStreamSession(args.session);
  return makeSnapshot({
    session,
    progress: {
      session_id: session.session_id,
      status: session.status,
      ...BASE_API_STREAM_PROGRESS,
      ...args.progress,
    },
  });
}

/**
 * Programs the mocked bridge to return one session start result followed by a
 * deterministic polling sequence, optionally including transient failures.
 */
export function mockApiStreamPolling(args: {
  session?: Partial<SessionSummary>;
  polls: PollResult[];
}) {
  const session = makeApiStreamSession(args.session);
  vi.mocked(mockBridge.startSession).mockResolvedValue(session);

  const readSession = vi.mocked(mockBridge.readSession);
  for (const poll of args.polls) {
    if (poll instanceof Error) {
      readSession.mockRejectedValueOnce(poll);
    } else {
      readSession.mockResolvedValueOnce(poll);
    }
  }

  const finalPoll = args.polls[args.polls.length - 1];
  if (finalPoll && !(finalPoll instanceof Error)) {
    readSession.mockResolvedValue(finalPoll);
  }

  return session;
}

/**
 * Advances enough real time for the polling loop to perform one or more
 * scheduled reads without exposing timer details in every test.
 */
export async function waitForPollingTick(count = 1) {
  for (let index = 0; index < count; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, POLLING_TICK_MS));
  }
}

/**
 * Waits for the composed App shell to render the requested session status
 * label, which keeps the test files focused on the behavior transition.
 */
export async function waitForStatusLabel(
  label: string = RUNNING_STATUS_LABEL,
) {
  await waitFor(() => {
    expect(screen.getByText(label)).toBeTruthy();
  });
}

async function startMonitoringFlow(sourceKind: "local" | "api_stream", args: {
  url?: string;
  selectDetector?: boolean;
  expectedStatusLabel?: string;
} = {}) {
  await renderApp();
  if (sourceKind === "local") {
    await enterLocalSource();
  } else {
    await enterApiStreamSource(args.url ?? API_STREAM_URL);
  }
  if (args.selectDetector ?? true) {
    await toggleFirstDetector();
  }
  startMonitoring();
  await waitForStatusLabel(args.expectedStatusLabel);
}

// Local-mode polling coverage is intentionally light here. The hook suites own
// the denser lifecycle matrix, while the App suite keeps the composed operator
// messaging that is harder to validate one seam lower.
/**
 * Starts a local-mode monitoring flow through the full App shell. The hook
 * suites own the denser lifecycle matrix; this helper exists for the
 * operator-visible wording that only appears one seam higher.
 */
export async function startLocalMonitoringFlow() {
  await startMonitoringFlow("local");
}

/**
 * Starts an `api_stream` monitoring flow through the full App shell with
 * optional URL, detector, and initial status overrides.
 */
export async function startApiStreamMonitoringFlow(args: {
  url?: string;
  selectDetector?: boolean;
  expectedStatusLabel?: string;
} = {}) {
  await startMonitoringFlow("api_stream", args);
}

/**
 * Asserts that the operator-visible reconnecting eyebrow is currently shown.
 */
export function expectRecoveringBanner() {
  expect(screen.getByText("Recovering")).toBeTruthy();
}

/**
 * Asserts that the transient or terminal status eyebrow labels are absent.
 * This is useful after recovery or when the UI should stay neutral.
 */
export function expectStatusSignalsAbsent() {
  expect(screen.queryByText("Recovering")).toBeNull();
  expect(screen.queryByText("Needs attention")).toBeNull();
  expect(screen.queryByText("Failed")).toBeNull();
}

/**
 * Asserts that the API-stream status panel is still neutral: no reconnecting,
 * no terminal labels, and no idle-complete warning.
 */
export function expectNoRecoveryOrTerminalSignals() {
  expectStatusSignalsAbsent();
  expect(screen.queryByText("Ended after going quiet")).toBeNull();
}

export { RUNNING_SESSION };
