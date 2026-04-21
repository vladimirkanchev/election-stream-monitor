// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { fail } from "./bridge/contract";
import type { RunSessionInput, SessionSnapshot, SessionSummary } from "./types";
import {
  enterApiStreamSource,
  enterLocalSource,
  mockBridge,
  renderApp,
  RUNNING_SESSION,
  startMonitoring,
  toggleFirstDetector,
} from "./testing/appHarness";

describe("App start-session integration", () => {
  it("shows a start error message when monitoring cannot be started", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));

    await renderApp();

    await enterLocalSource();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be started. Check the selected source and try again.")).toBeTruthy();
    });
  });

  it("shows a start error message when the initial session read fails after start", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("read failed"));

    await renderApp();

    await enterLocalSource();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be started. Check the selected source and try again.")).toBeTruthy();
    });
  });

  it("shows a start error message when the bridge returns a malformed start payload", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      mode: "video_segments",
      input_path: "/data/streams/segments",
      selected_detectors: ["video_blur"],
      status: "running",
    } as unknown as SessionSummary);

    await renderApp();

    await enterLocalSource();
    startMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be started. The local bridge returned an invalid response.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows a bridge-specific start error message for typed transport failures", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail("SESSION_START_FAILED", "Session start request failed", "cli crashed"),
    );

    await renderApp();

    await enterLocalSource();
    startMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be started. The local monitoring bridge reported a request failure.",
        ),
      ).toBeTruthy();
    });
  });

  it("normalizes missing snapshot collections from backend reads", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      session: null,
      progress: null,
    } as unknown as SessionSnapshot);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("starts api stream sessions with remote source payloads", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        session_id: "session-api-1",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      session: {
        session_id: "session-api-1",
        mode: "api_stream",
        input_path: "https://example.com/live/playlist.m3u8",
        selected_detectors: ["video_blur"],
        status: "running",
      },
      progress: {
        session_id: "session-api-1",
        status: "running",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:00",
      },
      alerts: [],
      results: [],
      latest_result: null,
    });

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        },
        selectedDetectors: ["video_blur"],
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("API stream")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a remote-source start error when the api stream cannot be reached", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("remote source unreachable"),
    );

    await renderApp();

    await enterApiStreamSource("https://example.com/live/unreachable.m3u8");
    startMonitoring();

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/unreachable.m3u8",
          access: "api_stream",
        },
        selectedDetectors: [],
      });
      expect(
        screen.getByText("Monitoring could not be started. Check the selected live stream and try again."),
      ).toBeTruthy();
    });
  });

  it("shows a retry-budget-exhausted start message for typed api stream bridge failures", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail(
        "SESSION_START_FAILED",
        "Session start request failed",
        "api_stream reconnect budget exhausted",
      ),
    );

    await renderApp();

    await enterApiStreamSource("https://example.com/live/playlist.m3u8");
    startMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "The live stream could not be reconnected. Monitoring ended after the retry budget was exhausted.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows direct-media guidance for unsupported webpage-style api stream inputs", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail(
        "SESSION_START_FAILED",
        "Session start request failed",
        "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
      ),
    );

    await renderApp();

    await enterApiStreamSource("https://video-platform.example/live/channel");
    startMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "This looks like a webpage URL, not a direct media stream. Paste a direct .m3u8 or .mp4 URL instead.",
        ),
      ).toBeTruthy();
    });
  });
});
