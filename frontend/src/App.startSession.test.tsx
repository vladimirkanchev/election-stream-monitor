/**
 * App-level coverage for start-session behavior that still needs the full UI
 * shell.
 *
 * These tests intentionally stay narrow: one happy-path integration check and
 * one operator-facing start-error contract. Broader validation lives in the
 * bridge and hook suites.
 */

// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { fail } from "./bridge/contract";
import type { RunSessionInput } from "./types";
import {
  enterApiStreamSource,
  enterLocalSource,
  makeSnapshot,
  mockBridge,
  renderApp,
  startMonitoring,
  toggleFirstDetector,
} from "./testing/appHarness";

describe("App start-session integration", () => {
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
          "This link opens a webpage, not the video stream itself. Paste the direct video link (.m3u8 or .mp4) instead.",
        ),
      ).toBeTruthy();
    });
  });

  it("keeps monitoring active when the first local snapshot read is briefly missing", async () => {
    const delayedStartSession = {
      session_id: "session-1",
      mode: "video_segments" as const,
      input_path: "/data/streams/segments",
      selected_detectors: ["video_blur"],
      status: "running" as const,
    };

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(delayedStartSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
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
      expect(
        (screen.getByRole("button", { name: "End Monitoring" }) as HTMLButtonElement).disabled,
      ).toBe(false);
    });
  });
});
