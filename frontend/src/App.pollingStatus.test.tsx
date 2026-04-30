/**
 * App-level polling coverage for operator-visible session status wording.
 *
 * This suite keeps the cases that benefit from rendering the composed App
 * shell: session-status labels, reconnecting banners, and terminal live-stream
 * messaging. Local lifecycle-state polling cases live in the
 * `useMonitoringSession` hook suites, where they run faster at the hook seam.
 */

// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import type { SessionSummary } from "./types";
import {
  enterApiStreamSource,
  enterLocalSource,
  makeSnapshot,
  mockBridge,
  renderApp,
  RUNNING_SESSION,
  startMonitoring,
  toggleFirstDetector,
} from "./testing/appHarness";

const API_STREAM_URL = "https://example.com/live/playlist.m3u8";
const POLLING_TICK_MS = 1100;
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

function makeApiStreamSession(
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

function makeApiStreamSnapshot(args: {
  session?: Partial<SessionSummary>;
  progress?: Partial<NonNullable<ReturnType<typeof makeSnapshot>["progress"]>>;
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

function mockApiStreamPolling(args: {
  session?: Partial<SessionSummary>;
  polls: Array<ReturnType<typeof makeSnapshot> | Error>;
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

async function waitForPollingTick(count = 1) {
  for (let index = 0; index < count; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, POLLING_TICK_MS));
  }
}

// Local-mode polling coverage is intentionally light here. The hook suites own
// the denser lifecycle matrix, while the App suite keeps the composed operator
// messaging that is harder to validate one seam lower.
async function startLocalMonitoringFlow() {
  await renderApp();
  await enterLocalSource();
  await toggleFirstDetector();
  startMonitoring();

  await waitFor(() => {
    expect(screen.getByText("Running")).toBeTruthy();
  });
}

async function startApiStreamMonitoringFlow(args: {
  url?: string;
  selectDetector?: boolean;
  expectedStatusLabel?: string;
} = {}) {
  await renderApp();
  await enterApiStreamSource(args.url ?? API_STREAM_URL);
  if (args.selectDetector ?? true) {
    await toggleFirstDetector();
  }
  startMonitoring();

  await waitFor(() => {
    expect(screen.getByText(args.expectedStatusLabel ?? "Running")).toBeTruthy();
  });
}

function expectRecoveringBanner() {
  expect(screen.getByText("Recovering")).toBeTruthy();
}

function expectNoRecoveryOrTerminalSignals() {
  expect(screen.queryByText("Recovering")).toBeNull();
  expect(screen.queryByText("Needs attention")).toBeNull();
  expect(screen.queryByText("Ended after going quiet")).toBeNull();
  expect(screen.queryByText("Failed")).toBeNull();
}

describe("App polling and status integration", () => {
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

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Monitoring finished successfully for the current source.")).toBeTruthy();
    });
  });

  it("shows a reconnecting message for api stream polling failures and clears it on recovery", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-reconnect" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-reconnect" },
        }),
        new Error("poll failed"),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-reconnect" },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expectRecoveringBanner();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.queryByText("Recovering")).toBeNull();
      expect(screen.getByText("Running")).toBeTruthy();
    });
  });

  it("shows a safety-limit message when a running api stream snapshot turns terminal", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-failed-runtime" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-failed-runtime" },
        }),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-failed-runtime", status: "failed" },
          progress: {
            last_updated_utc: "2026-04-04 09:00:01",
            status_reason: "terminal_failure",
            status_detail: "api_stream session runtime exceeded max duration",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow({ selectDetector: false });
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText(/taking too long/i)).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });
  });

  it("switches from reconnecting to a terminal retry-budget message when api stream recovery finally fails", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-retry-exhausted" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-retry-exhausted" },
          progress: { last_updated_utc: "2026-04-04 09:10:00" },
        }),
        new Error("poll failed"),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-retry-exhausted", status: "failed" },
          progress: {
            last_updated_utc: "2026-04-04 09:10:02",
            status_reason: "source_unreachable",
            status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expectRecoveringBanner();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Needs attention")).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    expect(screen.queryByText("Recovering")).toBeNull();
  });

  it("shows an idle-budget warning when a bounded api stream run completes after going quiet", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-idle-completed" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-idle-completed" },
          progress: {
            processed_count: 2,
            current_item: "live-window-002",
          },
        }),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-idle-completed", status: "completed" },
          progress: {
            processed_count: 2,
            current_item: "live-window-002",
            last_updated_utc: "2026-04-04 09:20:03",
            status_reason: "idle_poll_budget_exhausted",
            status_detail: "Idle poll budget exhausted",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    });
  });

  it("replaces reconnecting with the idle-complete warning when a recovering api stream settles after going quiet", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-reconnect-then-idle-complete" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-reconnect-then-idle-complete" },
          progress: {
            processed_count: 2,
            current_item: "live-window-002",
          },
        }),
        new Error("poll failed"),
        makeApiStreamSnapshot({
          session: {
            session_id: "session-api-reconnect-then-idle-complete",
            status: "completed",
          },
          progress: {
            processed_count: 2,
            current_item: "live-window-002",
            last_updated_utc: "2026-04-04 09:25:03",
            status_reason: "idle_poll_budget_exhausted",
            status_detail: "Idle poll budget exhausted",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expectRecoveringBanner();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    });

    expect(screen.queryByText("Recovering")).toBeNull();
    expect(screen.queryByText("Needs attention")).toBeNull();
    expect(screen.queryByText("Failed")).toBeNull();
  });

  it("keeps a running api stream without progress in a neutral state until real warnings appear", async () => {
    mockApiStreamPolling({
      session: { session_id: "session-api-no-progress-yet" },
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-no-progress-yet" },
          progress: {
            processed_count: 0,
            total_count: 0,
            current_item: null,
            latest_result_detector: null,
            latest_result_detectors: [],
            status_reason: null,
            status_detail: null,
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    expectNoRecoveryOrTerminalSignals();
  });

  // API stream transition and status-detail rendering

  it("shows live session status details for api stream runs", async () => {
    mockApiStreamPolling({
      polls: [makeApiStreamSnapshot()],
    });

    await startApiStreamMonitoringFlow();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("API stream")).toBeTruthy();
      expect(screen.getByText("Live, 1 chunk analyzed")).toBeTruthy();
      expect(screen.getByText("1 chunk analyzed, 4 discovered")).toBeTruthy();
      expect(screen.getByText("00:02 live")).toBeTruthy();
      expect(
        screen.getByText("Live monitoring is active and currently analyzing live-window-001."),
      ).toBeTruthy();
    });
  });

  it("shows failed live-session status details for api stream runs", async () => {
    mockApiStreamPolling({
      session: {
        session_id: "session-api-failed",
        status: "failed",
      },
      polls: [
        makeApiStreamSnapshot({
          session: {
            session_id: "session-api-failed",
            status: "failed",
          },
          progress: {
            processed_count: 4,
            total_count: 6,
            current_item: "live-window-004",
            alert_count: 1,
            last_updated_utc: "2026-04-04 09:00:04",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow({ expectedStatusLabel: "Failed" });

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
      expect(screen.getByText("Live, 4 chunks analyzed")).toBeTruthy();
      expect(
        screen.getByText(
          "Live monitoring ended before this stream finished. Check the details below for more information.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows longer-run live progress wording for api stream runs", async () => {
    mockApiStreamPolling({
      session: {
        session_id: "session-api-long",
      },
      polls: [
        makeApiStreamSnapshot({
          session: {
            session_id: "session-api-long",
          },
          progress: {
            processed_count: 6,
            total_count: 9,
            current_item: "live-window-006",
            alert_count: 1,
            last_updated_utc: "2026-04-04 09:00:06",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();

    await waitFor(() => {
      expect(screen.getByText("Live, 6 chunks analyzed")).toBeTruthy();
      expect(screen.getByText("6 chunks analyzed, 9 discovered")).toBeTruthy();
      expect(
        screen.getByText("Live monitoring is active and currently analyzing live-window-006."),
      ).toBeTruthy();
    });
  });
});
