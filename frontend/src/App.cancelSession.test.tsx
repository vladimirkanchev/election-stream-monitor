// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { fail } from "./bridge/contract";
import type { RunSessionInput, SessionSummary } from "./types";
import {
  endMonitoring,
  enterLocalSource,
  makeSnapshot,
  mockBridge,
  renderApp,
  RUNNING_SESSION,
  startMonitoring,
  toggleFirstDetector,
} from "./testing/appHarness";

describe("App cancel-session integration", () => {
  it("starts monitoring, freezes detector selection, and can end the session", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        ...RUNNING_SESSION,
        selected_detectors: input.selectedDetectors,
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);

    startMonitoring();

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "video_segments",
          path: "/data/streams/segments",
          access: "local_path",
        },
        selectedDetectors: ["video_blur"],
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });

    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);

    endMonitoring();
    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledWith("session-1");
    });
  });

  it("shows a stop error message when the cancel request fails", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("cancel failed"));

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be ended cleanly. Try ending the session again.")).toBeTruthy();
    });
  });

  it("shows a stop error message when the bridge returns a malformed cancel payload", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      session_id: "session-1",
    } as unknown as SessionSummary);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText("Monitoring could not be ended cleanly. The local bridge returned an invalid response."),
      ).toBeTruthy();
    });
  });

  it("shows a bridge-specific stop error message for typed cancel failures", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail("SESSION_CANCEL_FAILED", "Session cancel request failed", "cli crashed"),
    );

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be ended cleanly. The local monitoring bridge reported a request failure.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows the bridge-aware stop message for backend-style cancel failures", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail(
        "SESSION_CANCEL_FAILED",
        "Session cancel request failed",
        "No persisted session snapshot found for session_id=session-1",
        {
          backend_error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found for session_id=session-1",
        },
      ),
    );

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be ended cleanly. The local monitoring bridge reported a request failure.",
        ),
      ).toBeTruthy();
    });
  });

  it("suppresses a stop request after polling has already settled the UI into Completed", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          ...RUNNING_SESSION,
          status: "completed",
        },
        progress: {
          session_id: "session-1",
          status: "completed",
          processed_count: 4,
          total_count: 4,
          current_item: null,
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-21 12:30:00",
          status_reason: "completed",
          status_detail: null,
        },
      }),
    );

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
    });

    endMonitoring();

    expect(mockBridge.cancelSession).not.toHaveBeenCalled();
    expect(
      screen.queryByText("Monitoring was already ending or had already finished."),
    ).toBeNull();
    expect(
      screen.getByText("Monitoring finished successfully for the current source."),
    ).toBeTruthy();
  });

  it("does not show a stop error when cancelSession resolves with null", async () => {
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();

    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledWith("session-1");
    });

    expect(screen.queryByText(/Monitoring could not be ended cleanly\./)).toBeNull();
  });

  it("keeps a single in-flight cancel request when End Monitoring is clicked repeatedly", async () => {
    let resolveCancel: ((value: SessionSummary | null) => void) | null = null;

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCancel = resolve;
        }),
    );

    await renderApp();

    await enterLocalSource();
    await toggleFirstDetector();
    startMonitoring();

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    endMonitoring();
    endMonitoring();
    endMonitoring();

    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledTimes(1);
    });

    const completeCancel = resolveCancel as ((value: SessionSummary | null) => void) | null;
    expect(completeCancel).not.toBeNull();
    completeCancel?.({
      ...RUNNING_SESSION,
      status: "cancelling",
    });
  });
});
