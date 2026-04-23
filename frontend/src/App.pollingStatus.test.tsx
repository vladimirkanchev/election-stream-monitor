// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { fail } from "./bridge/contract";
import type { SessionSummary } from "./types";
import {
  endMonitoring,
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

function makeLocalSession(
  overrides: Partial<SessionSummary> = {},
): SessionSummary {
  return {
    ...RUNNING_SESSION,
    ...overrides,
  };
}

function makeLocalSnapshot(args: {
  session?: Partial<SessionSummary>;
  progress?: Partial<NonNullable<ReturnType<typeof makeSnapshot>["progress"]>>;
} = {}) {
  const session = makeLocalSession(args.session);
  return makeSnapshot({
    session,
    progress: {
      session_id: session.session_id,
      status: session.status,
      processed_count: 2,
      total_count: 4,
      current_item: session.status === "cancelled" ? null : "segment_0002.ts",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-21 11:00:01",
      status_reason: session.status === "running" ? "running" : null,
      status_detail: null,
      ...args.progress,
    },
  });
}

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
      processed_count: 1,
      total_count: 4,
      current_item: "live-window-001",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-04 09:00:00",
      status_reason: null,
      status_detail: null,
      ...args.progress,
    },
  });
}

function mockApiStreamPolling(args: {
  session?: Partial<SessionSummary>;
  polls: Array<ReturnType<typeof makeSnapshot> | Error>;
}) {
  const session = makeApiStreamSession(args.session);
  (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(session);

  const readSession = mockBridge.readSession as ReturnType<typeof vi.fn>;
  for (const poll of args.polls) {
    if (poll instanceof Error) {
      readSession.mockRejectedValueOnce(poll);
    } else {
      readSession.mockResolvedValueOnce(poll);
    }
  }

  const finalPoll = args.polls.at(-1);
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

async function startLocalMonitoringFlow(path = "/data/streams/segments") {
  await renderApp();
  await enterLocalSource(path);
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

describe("App polling and status integration", () => {
  // Local session polling and terminal-state stability

  it("updates status from polling and shows completed state", async () => {
    const completedSnapshot = makeLocalSnapshot({
      session: { status: "completed" },
      progress: {
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
        alert_count: 1,
        last_updated_utc: "2026-04-02 10:00:04",
      },
    });
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
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

  it("keeps the last good session state when a polling read fails", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(makeLocalSnapshot());

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a reconnecting message for api stream polling failures and clears it on recovery", async () => {
    const liveSession = mockApiStreamPolling({
      session_id: "session-api-reconnect",
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
      expect(screen.getByText("Recovering")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.queryByText("Recovering")).toBeNull();
      expect(screen.getByText("Running")).toBeTruthy();
    });
  });

  it("keeps reconnecting as a warning-only state until an api stream actually becomes terminal", async () => {
    mockApiStreamPolling({
      session_id: "session-api-reconnecting-only",
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-reconnecting-only" },
        }),
        new Error("poll failed"),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-reconnecting-only" },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Recovering")).toBeTruthy();
      expect(screen.getByText("Running")).toBeTruthy();
    });

    expect(screen.queryByText("Needs attention")).toBeNull();
    expect(screen.queryByText("Failed")).toBeNull();
    expect(screen.queryByText("Ended after going quiet")).toBeNull();
  });

  it("shows a safety-limit message when a running api stream snapshot turns terminal", async () => {
    const liveSession = mockApiStreamPolling({
      session_id: "session-api-failed-runtime",
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
    const liveSession = mockApiStreamPolling({
      session_id: "session-api-retry-exhausted",
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
      expect(screen.getByText("Recovering")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Needs attention")).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    expect(screen.queryByText("Recovering")).toBeNull();
  });

  it("shows an idle-budget warning when a bounded api stream run completes after going quiet", async () => {
    const liveSession = mockApiStreamPolling({
      session_id: "session-api-idle-completed",
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

  it("does not regress back to Running after an idle-complete terminal state receives a stale older snapshot", async () => {
    const liveSession = makeApiStreamSession({
      session_id: "session-api-idle-terminal",
    });
    const completedSnapshot = makeApiStreamSnapshot({
      session: { session_id: "session-api-idle-terminal", status: "completed" },
      progress: {
        processed_count: 2,
        current_item: "live-window-002",
        last_updated_utc: "2026-04-04 09:22:03",
        status_reason: "idle_poll_budget_exhausted",
        status_detail: "Idle poll budget exhausted",
      },
    });
    const staleRunningSnapshot = makeApiStreamSnapshot({
      session: { session_id: "session-api-idle-terminal" },
      progress: {
        processed_count: 2,
        current_item: "live-window-002",
        last_updated_utc: "2026-04-04 09:21:59",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        makeApiStreamSnapshot({
          session: { session_id: "session-api-idle-terminal" },
          progress: {
            processed_count: 2,
            current_item: "live-window-002",
            last_updated_utc: "2026-04-04 09:22:00",
          },
        }),
      )
      .mockResolvedValueOnce(completedSnapshot)
      .mockResolvedValueOnce(staleRunningSnapshot)
      .mockResolvedValue(staleRunningSnapshot);

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    });

    expect(screen.queryByText("Running")).toBeNull();
    expect(screen.queryByText("Recovering")).toBeNull();
  });

  it("replaces reconnecting with the idle-complete warning when a recovering api stream settles after going quiet", async () => {
    mockApiStreamPolling({
      session_id: "session-api-reconnect-then-idle-complete",
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
      expect(screen.getByText("Recovering")).toBeTruthy();
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

  it("can recover from reconnecting and still later settle on a terminal failure without stale recovery cues", async () => {
    mockApiStreamPolling({
      session_id: "session-api-recover-then-fail",
      polls: [
        makeApiStreamSnapshot({
          session: { session_id: "session-api-recover-then-fail" },
          progress: { last_updated_utc: "2026-04-04 09:30:00" },
        }),
        new Error("poll failed"),
        makeApiStreamSnapshot({
          session: { session_id: "session-api-recover-then-fail" },
          progress: {
            last_updated_utc: "2026-04-04 09:30:02",
            processed_count: 2,
            current_item: "live-window-002",
          },
        }),
        makeApiStreamSnapshot({
          session: {
            session_id: "session-api-recover-then-fail",
            status: "failed",
          },
          progress: {
            last_updated_utc: "2026-04-04 09:30:04",
            processed_count: 2,
            current_item: "live-window-002",
            status_reason: "source_unreachable",
            status_detail:
              "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
          },
        }),
      ],
    });

    await startApiStreamMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Recovering")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.queryByText("Recovering")).toBeNull();
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
      expect(screen.getByText("Needs attention")).toBeTruthy();
    });

    expect(screen.queryByText("Recovering")).toBeNull();
  });

  it("keeps a running api stream without progress in a neutral state until real warnings appear", async () => {
    mockApiStreamPolling({
      session_id: "session-api-no-progress-yet",
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

    expect(screen.queryByText("Recovering")).toBeNull();
    expect(screen.queryByText("Needs attention")).toBeNull();
    expect(screen.queryByText("Ended after going quiet")).toBeNull();
    expect(screen.queryByText("Failed")).toBeNull();
  });

  it("moves from cancelling to stopped after polling returns a cancelled snapshot", async () => {
    const cancelledSnapshot = makeLocalSnapshot({
      session: { status: "cancelled" },
      progress: {
        status_reason: "cancel_requested",
        status_detail: "Cancellation requested by client",
      },
    });
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValue(cancelledSnapshot);
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...RUNNING_SESSION,
      status: "cancelling",
    });

    await startLocalMonitoringFlow();

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });
  });

  it("does not regress back to Running after polling reaches a cancelled terminal state", async () => {
    const cancelledSnapshot = makeLocalSnapshot({
      session: { status: "cancelled" },
      progress: {
        status_reason: "cancel_requested",
        status_detail: "Cancellation requested by client",
      },
    });
    const staleRunningSnapshot = makeLocalSnapshot({
      progress: {
        last_updated_utc: "2026-04-21 10:59:59",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(cancelledSnapshot)
      .mockResolvedValueOnce(staleRunningSnapshot)
      .mockResolvedValue(staleRunningSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });

    expect(screen.queryByText("Running")).toBeNull();
  });

  it("keeps ending state coherent when cancel is requested while a poll is still in flight", async () => {
    let resolvePoll: ((value: ReturnType<typeof makeSnapshot>) => void) | null = null;

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePoll = resolve;
          }),
      );
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...RUNNING_SESSION,
      status: "cancelling",
    });

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
      expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);
    });

    resolvePoll?.(
      makeLocalSnapshot({
        session: { status: "cancelled" },
        progress: {
          last_updated_utc: "2026-04-21 12:00:01",
          status_reason: "cancel_requested",
          status_detail: "Cancellation requested by client",
        },
      }),
    );

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });
  });

  it("does not regress back to Failed after polling reaches a failed terminal state", async () => {
    const failedSnapshot = makeLocalSnapshot({
      session: { status: "failed" },
      progress: {
        last_updated_utc: "2026-04-21 12:10:01",
        status_reason: "terminal_failure",
        status_detail: "session runtime exceeded max duration",
      },
    });
    const staleRunningSnapshot = makeLocalSnapshot({
      progress: {
        last_updated_utc: "2026-04-21 12:09:59",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(failedSnapshot)
      .mockResolvedValueOnce(staleRunningSnapshot)
      .mockResolvedValue(staleRunningSnapshot);

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    expect(screen.queryByText("Running")).toBeNull();
  });

  it("keeps the last good session state when polling returns a missing-session bridge failure", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-1",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-1",
          },
        ),
      )
      .mockResolvedValue(makeSnapshot());

    await startLocalMonitoringFlow();
    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });

    expect(
      screen.queryByText(/The local monitoring bridge reported a request failure\./i),
    ).toBeNull();
  });

  it("recovers from a polling failure during cancelling and still settles on stopped", async () => {
    const cancelledSnapshot = makeLocalSnapshot({
      session: { status: "cancelled" },
      progress: {
        last_updated_utc: "2026-04-21 12:20:02",
        status_reason: "cancel_requested",
        status_detail: "Cancellation requested by client",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockRejectedValueOnce(new Error("poll failed during cancel"))
      .mockResolvedValue(cancelledSnapshot);
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...RUNNING_SESSION,
      status: "cancelling",
    });

    await startLocalMonitoringFlow();

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await waitForPollingTick(2);

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });
  });

  it("keeps the last good ending state when a post-cancel poll reports session_not_found", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-1",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-1",
          },
        ),
      );
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...RUNNING_SESSION,
      status: "cancelling",
    });

    await startLocalMonitoringFlow();

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await waitForPollingTick();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    expect(
      screen.queryByText(/The local monitoring bridge reported a request failure\./i),
    ).toBeNull();
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
