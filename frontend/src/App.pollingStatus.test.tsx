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
    toggleFirstDetector();
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
    toggleFirstDetector();
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
    toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(
        screen.getByText("The live stream is temporarily unavailable. Monitoring is reconnecting."),
      ).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(
        screen.queryByText("The live stream is temporarily unavailable. Monitoring is reconnecting."),
      ).toBeNull();
      expect(screen.getByText("Live monitoring is active and currently analyzing live-window-001.")).toBeTruthy();
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
      expect(
        screen.getByText("The live stream monitoring run stopped after hitting a runtime safety limit."),
      ).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });
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
    toggleFirstDetector();
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
    toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
      expect(screen.getByText("Live, 4 chunks analyzed")).toBeTruthy();
      expect(
        screen.getByText(
          "Live monitoring ended with an error. The stream may be unavailable or the reconnect budget may have been exhausted.",
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
    toggleFirstDetector();
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
