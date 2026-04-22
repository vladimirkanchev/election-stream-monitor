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

describe("App polling and status integration", () => {
  it("updates status from polling and shows completed state", async () => {
    const completedSnapshot = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: "session-1",
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
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(completedSnapshot)
      .mockResolvedValue(completedSnapshot);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => expect(screen.getByText("Running")).toBeTruthy());

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

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
      .mockResolvedValue(makeSnapshot());

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a reconnecting message for api stream polling failures and clears it on recovery", async () => {
    const liveSession: SessionSummary = {
      session_id: "session-api-reconnect",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const liveSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-reconnect",
        status: "running",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:00",
      },
    });
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(liveSnapshot)
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(liveSnapshot);

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Recovering")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.queryByText("Recovering")).toBeNull();
      expect(screen.getByText("Running")).toBeTruthy();
    });
  });

  it("shows a safety-limit message when a running api stream snapshot turns terminal", async () => {
    const liveSession: SessionSummary = {
      session_id: "session-api-failed-runtime",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const runningSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-failed-runtime",
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
    });
    const failedSnapshot = makeSnapshot({
      session: { ...liveSession, status: "failed" },
      progress: {
        session_id: "session-api-failed-runtime",
        status: "failed",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:01",
        status_reason: "terminal_failure",
        status_detail: "api_stream session runtime exceeded max duration",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(runningSnapshot)
      .mockResolvedValue(failedSnapshot);

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText(/taking too long/i)).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });
  });

  it("switches from reconnecting to a terminal retry-budget message when api stream recovery finally fails", async () => {
    const liveSession: SessionSummary = {
      session_id: "session-api-retry-exhausted",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const runningSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-retry-exhausted",
        status: "running",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:10:00",
        status_reason: null,
        status_detail: null,
      },
    });
    const failedSnapshot = makeSnapshot({
      session: { ...liveSession, status: "failed" },
      progress: {
        session_id: "session-api-retry-exhausted",
        status: "failed",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:10:02",
        status_reason: "source_unreachable",
        status_detail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(runningSnapshot)
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(failedSnapshot);

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Recovering")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Needs attention")).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    expect(screen.queryByText("Recovering")).toBeNull();
  });

  it("shows an idle-budget warning when a bounded api stream run completes after going quiet", async () => {
    const liveSession: SessionSummary = {
      session_id: "session-api-idle-completed",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const runningSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-idle-completed",
        status: "running",
        processed_count: 2,
        total_count: 4,
        current_item: "live-window-002",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:20:00",
        status_reason: null,
        status_detail: null,
      },
    });
    const completedSnapshot = makeSnapshot({
      session: { ...liveSession, status: "completed" },
      progress: {
        session_id: "session-api-idle-completed",
        status: "completed",
        processed_count: 2,
        total_count: 4,
        current_item: "live-window-002",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:20:03",
        status_reason: "idle_poll_budget_exhausted",
        status_detail: "Idle poll budget exhausted",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(runningSnapshot)
      .mockResolvedValue(completedSnapshot);

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    });
  });

  it("moves from cancelling to stopped after polling returns a cancelled snapshot", async () => {
    const cancelledSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "cancelled" },
      progress: {
        session_id: "session-1",
        status: "cancelled",
        processed_count: 2,
        total_count: 4,
        current_item: null,
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-21 11:00:01",
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

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });
  });

  it("does not regress back to Running after polling reaches a cancelled terminal state", async () => {
    const cancelledSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "cancelled" },
      progress: {
        session_id: "session-1",
        status: "cancelled",
        processed_count: 2,
        total_count: 4,
        current_item: null,
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-21 11:00:01",
        status_reason: "cancel_requested",
        status_detail: "Cancellation requested by client",
      },
    });
    const staleRunningSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "running" },
      progress: {
        session_id: "session-1",
        status: "running",
        processed_count: 2,
        total_count: 4,
        current_item: "segment_0002.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-21 10:59:59",
        status_reason: "running",
        status_detail: null,
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(cancelledSnapshot)
      .mockResolvedValueOnce(staleRunningSnapshot)
      .mockResolvedValue(staleRunningSnapshot);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Stopped")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

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

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
      expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);
    });

    resolvePoll?.(
      makeSnapshot({
        session: { ...RUNNING_SESSION, status: "cancelled" },
        progress: {
          session_id: "session-1",
          status: "cancelled",
          processed_count: 2,
          total_count: 4,
          current_item: null,
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
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
    const failedSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "failed" },
      progress: {
        session_id: "session-1",
        status: "failed",
        processed_count: 2,
        total_count: 4,
        current_item: "segment_0002.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-21 12:10:01",
        status_reason: "terminal_failure",
        status_detail: "session runtime exceeded max duration",
      },
    });
    const staleRunningSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "running" },
      progress: {
        session_id: "session-1",
        status: "running",
        processed_count: 2,
        total_count: 4,
        current_item: "segment_0002.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-21 12:09:59",
        status_reason: "running",
        status_detail: null,
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(failedSnapshot)
      .mockResolvedValueOnce(staleRunningSnapshot)
      .mockResolvedValue(staleRunningSnapshot);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

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

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });

    expect(
      screen.queryByText(/The local monitoring bridge reported a request failure\./i),
    ).toBeNull();
  });

  it("recovers from a polling failure during cancelling and still settles on stopped", async () => {
    const cancelledSnapshot = makeSnapshot({
      session: { ...RUNNING_SESSION, status: "cancelled" },
      progress: {
        session_id: "session-1",
        status: "cancelled",
        processed_count: 2,
        total_count: 4,
        current_item: null,
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
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

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));
    await new Promise((resolve) => window.setTimeout(resolve, 1100));

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

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Ending")).toBeTruthy();
    });

    expect(
      screen.queryByText(/The local monitoring bridge reported a request failure\./i),
    ).toBeNull();
  });

  it("shows live session status details for api stream runs", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input) => ({
        session_id: "session-api-live",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-live",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "running",
        },
        progress: {
          session_id: "session-api-live",
          status: "running",
          processed_count: 1,
          total_count: 4,
          current_item: "live-window-001",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-04 09:00:00",
        },
      }),
    );

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

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
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input) => ({
        session_id: "session-api-failed",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "failed",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-failed",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "failed",
        },
        progress: {
          session_id: "session-api-failed",
          status: "failed",
          processed_count: 4,
          total_count: 6,
          current_item: "live-window-004",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 1,
          last_updated_utc: "2026-04-04 09:00:04",
        },
      }),
    );

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

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
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input) => ({
        session_id: "session-api-long",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-long",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "running",
        },
        progress: {
          session_id: "session-api-long",
          status: "running",
          processed_count: 6,
          total_count: 9,
          current_item: "live-window-006",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 1,
          last_updated_utc: "2026-04-04 09:00:06",
        },
      }),
    );

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Live, 6 chunks analyzed")).toBeTruthy();
      expect(screen.getByText("6 chunks analyzed, 9 discovered")).toBeTruthy();
      expect(
        screen.getByText("Live monitoring is active and currently analyzing live-window-006."),
      ).toBeTruthy();
    });
  });
});
