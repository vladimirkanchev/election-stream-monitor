/**
 * App-level polling coverage for api_stream operator messaging: reconnecting,
 * terminal live-stream outcomes, and live progress wording.
 */

// @vitest-environment jsdom

import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  expectNoRecoveryOrTerminalSignals,
  expectRecoveringBanner,
  expectStatusSignalsAbsent,
  makeApiStreamSnapshot,
  mockApiStreamPolling,
  startApiStreamMonitoringFlow,
  waitForPollingTick,
} from "./testing/pollingStatusTestSupport";

describe("App polling and status integration (api_stream)", () => {
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
            status_detail:
              "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
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

    expectStatusSignalsAbsent();
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
      expect(screen.getByText("Live monitoring is active.")).toBeTruthy();
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
      expect(screen.getByText("Live monitoring is active.")).toBeTruthy();
    });
  });
});
