/**
 * App-level coverage for cancel-session behavior that still needs the full UI
 * shell.
 *
 * This file keeps one end-to-end stop flow and one backend-shaped cancel
 * failure case. Lower-level request/cancel state mechanics live at the hook
 * and bridge seams.
 */

// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { fail } from "./bridge/contract";
import type { RunSessionInput } from "./types";
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

});
