/**
 * Component-level coverage for operator-facing session and playback wording.
 *
 * The goal here is not to re-test the monitoring hooks. These checks protect
 * the copy and ordering that turn normalized backend state into the status
 * panel the operator actually reads.
 */

// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { SessionStatusPanel } from "./SessionStatusPanel";
import type { MonitorSource, PlaybackStatus, SessionProgress } from "../types";

const API_STREAM_SOURCE: MonitorSource = {
  kind: "api_stream",
  path: "https://streams.example.com/live.m3u8",
  access: "api_stream",
};

const VIDEO_SEGMENTS_SOURCE: MonitorSource = {
  kind: "video_segments",
  path: "/tmp/segments",
  access: "local_path",
};

const BASE_PROGRESS: SessionProgress = {
  session_id: "session-1",
  status: "running",
  processed_count: 2,
  total_count: 4,
  current_item: "live-window-002",
  latest_result_detector: "video_blur",
  latest_result_detectors: ["video_blur"],
  alert_count: 0,
  last_updated_utc: "2026-04-06 10:00:00",
  status_reason: null,
  status_detail: null,
};
const RECONNECTING_MESSAGE =
  "The live stream dropped for a moment. Monitoring is trying to reconnect.";
const SOURCE_UNREACHABLE_DETAIL =
  "api_stream reconnect budget exhausted: upstream returned HTTP 503";

type RenderPanelArgs = {
  progress?: SessionProgress | null;
  sessionStatus?: "idle" | "starting" | "pending" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  playbackStatus?: PlaybackStatus;
  sessionError?: string | null;
  source?: MonitorSource;
  playbackLive?: boolean;
  playbackTime?: number;
  playbackDuration?: number | null;
  localPlaylistWarning?: string | null;
};

/**
 * Builds the panel props used across the status-wording scenarios.
 *
 * The suite varies one lifecycle or playback dimension at a time, so the
 * baseline props stay intentionally stable here.
 */
function buildPanelProps(args: RenderPanelArgs = {}) {
  return {
    source: args.source ?? API_STREAM_SOURCE,
    sessionStatus: args.sessionStatus ?? "running",
    progress: args.progress ?? BASE_PROGRESS,
    selectedDetectorCount: 1,
    visibleAlertCount: 0,
    playbackTime: args.playbackTime ?? 5,
    playbackDuration: args.playbackDuration ?? null,
    playbackLive: args.playbackLive ?? true,
    playbackStatus: args.playbackStatus ?? "playing",
    sessionError: args.sessionError ?? null,
    localPlaylistWarning: args.localPlaylistWarning ?? null,
  } satisfies React.ComponentProps<typeof SessionStatusPanel>;
}

/**
 * Creates a progress payload with only the lifecycle fields under test
 * overridden for the current scenario.
 */
function buildProgress(overrides: Partial<SessionProgress> = {}): SessionProgress {
  return {
    ...BASE_PROGRESS,
    ...overrides,
  };
}

/**
 * Renders the status panel with the common operator-facing defaults used by
 * this copy-contract suite.
 */
function renderPanel(args: RenderPanelArgs = {}) {
  return render(<SessionStatusPanel {...buildPanelProps(args)} />);
}

// Exact UI copy is a first-class contract here, so keep the repeated lookup
// terse and let the behavior cases stay easy to scan.
function expectVisibleText(text: string) {
  expect(screen.getByText(text)).toBeTruthy();
}

/**
 * Keeps absence checks terse when a scenario should suppress a specific copy
 * path entirely.
 */
function expectTextHidden(text: string) {
  expect(screen.queryByText(text)).toBeNull();
}

// Some diagnostics are easier to validate by rendered ordering than by a
// single exact text node.
function getDiagnosticItems(container: HTMLElement) {
  return Array.from(container.querySelectorAll(".session-diagnostics__item")).map((item) =>
    item.textContent?.trim(),
  );
}

/**
 * Verifies the diagnostic stack order without repeating the DOM query plumbing
 * in each precedence test.
 */
function expectDiagnosticOrder(container: HTMLElement, expected: string[]) {
  expect(getDiagnosticItems(container)).toEqual(expected);
}

afterEach(() => {
  cleanup();
});

describe("SessionStatusPanel monitoring UX", () => {
  it("keeps live stop and terminal summaries distinct", () => {
    const { rerender } = renderPanel({
      sessionStatus: "cancelling",
      progress: buildProgress({ status: "cancelling" }),
    });

    expectVisibleText("Stopping now");
    expectVisibleText("The current monitoring run is settling a stop request.");
    expectVisibleText("A stop request is settling for the current live stream.");

    rerender(
      <SessionStatusPanel
        {...buildPanelProps({
          sessionStatus: "cancelled",
          progress: buildProgress({ status: "cancelled", current_item: null }),
          playbackStatus: "stopped",
        })}
      />,
    );

    expectVisibleText("Stopped by user");
    expectVisibleText("Monitoring was ended by the user.");
    expect(
      screen.getByText("Live monitoring was stopped by the user before the current stream completed."),
    ).toBeTruthy();

    rerender(
      <SessionStatusPanel
        {...buildPanelProps({
          sessionStatus: "failed",
          progress: buildProgress({
            status: "failed",
            status_reason: "source_unreachable",
            status_detail: SOURCE_UNREACHABLE_DETAIL,
          }),
          playbackStatus: "stopped",
        })}
      />,
    );

    expectVisibleText("Needs attention");
    expectVisibleText("Monitoring ended with a problem that needs review.");
    expect(
      screen.getByText(
        "Live monitoring ended before this stream finished. Check the details below for more information.",
      ),
    ).toBeTruthy();
  });

  it("shows completed live runs and idle-bounded completion warnings separately", () => {
    renderPanel({
      sessionStatus: "completed",
      playbackStatus: "stopped",
      progress: buildProgress({
        status: "completed",
        status_reason: "idle_poll_budget_exhausted",
        status_detail: "Idle poll budget exhausted",
      }),
    });

    expectVisibleText("Ended after going quiet");
    expect(
      screen.getByText("Monitoring stopped after the live stream stopped sending new video."),
    ).toBeTruthy();
    expectVisibleText("Monitoring ended.");
    expect(
      screen.getByText(
        "The live stream stopped sending new video, so monitoring has ended.",
      ),
    ).toBeTruthy();
  });

  it("keeps completed live messaging in progress until playback stops", () => {
    renderPanel({
      sessionStatus: "completed",
      playbackStatus: "playing",
      progress: buildProgress({
        status: "completed",
        status_reason: "completed",
        status_detail: null,
        current_item: null,
      }),
    });

    expectVisibleText("Current state");
    expectVisibleText("Monitoring is in progress.");
    expectTextHidden("Monitoring ended.");
  });

  it("shows simplified live completion once playback has stopped", () => {
    renderPanel({
      sessionStatus: "completed",
      playbackStatus: "stopped",
      progress: buildProgress({
        status: "completed",
        status_reason: "completed",
        status_detail: null,
        current_item: null,
      }),
    });

    expectVisibleText("Current state");
    expectVisibleText("Monitoring ended.");
    expectTextHidden("Ended after going quiet");
    expectTextHidden("Finished cleanly");
  });

  it("shows a short local playback warning when the playlist has gaps", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "completed",
      progress: buildProgress({
        status: "completed",
        processed_count: 9,
        total_count: 9,
        current_item: "segment_0009.ts",
      }),
      playbackLive: false,
      playbackDuration: 10,
      localPlaylistWarning: "Playlist has gaps. Playback may be incomplete.",
    });

    expectVisibleText("Playback warning");
    expectVisibleText("Playlist has gaps. Playback may be incomplete.");
    expectVisibleText("Monitoring finished, but playback may be incomplete.");
    expectTextHidden("Monitoring finished successfully for the current source.");
  });

  it("shows simplified local loading, running, and stopping messages", () => {
    const { rerender } = renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "starting",
      progress: buildProgress({
        status: "pending",
        current_item: null,
      }),
      playbackLive: false,
    });

    expectVisibleText("Monitoring is starting.");

    rerender(
      <SessionStatusPanel
        {...buildPanelProps({
          source: VIDEO_SEGMENTS_SOURCE,
          sessionStatus: "running",
          progress: buildProgress({
            status: "running",
            current_item: "segment_0002.ts",
          }),
          playbackLive: false,
        })}
      />,
    );

    expectVisibleText("Monitoring is in progress.");

    rerender(
      <SessionStatusPanel
        {...buildPanelProps({
          source: VIDEO_SEGMENTS_SOURCE,
          sessionStatus: "cancelling",
          progress: buildProgress({
            status: "cancelling",
            current_item: "segment_0002.ts",
          }),
          playbackLive: false,
        })}
      />,
    );

    expectVisibleText("Monitoring ended.");
  });

  it("keeps local completed messaging in a catch-up state until playback reaches the end", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "completed",
      progress: buildProgress({
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
      }),
      playbackLive: false,
      playbackTime: 5,
      playbackDuration: 10,
    });

    expectVisibleText("Current state");
    expectVisibleText("Monitoring is in progress.");
    expect(screen.queryByText("Monitoring is in progress.")).not.toBeNull();
    expectTextHidden("Monitoring ended.");
  });

  it("shows finished-local messaging once playback reaches the end", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "completed",
      progress: buildProgress({
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
      }),
      playbackLive: false,
      playbackTime: 10,
      playbackDuration: 10,
    });

    expectVisibleText("Monitoring ended.");
    expectVisibleText("Current state");
  });

  it("shows ended-local messaging after the user stops playback before the natural end", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "completed",
      progress: buildProgress({
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
      }),
      playbackLive: false,
      playbackTime: 5,
      playbackDuration: 10,
      playbackStatus: "stopped",
    });

    expectVisibleText("Current state");
    expectVisibleText("Monitoring ended.");
    expectTextHidden("Monitoring is in progress.");
  });

  it("renders a reconnecting cue separately from terminal diagnostics", () => {
    renderPanel({
      sessionError: RECONNECTING_MESSAGE,
    });

    expectVisibleText("Recovering");
    expectVisibleText("Trying to reconnect to the live stream.");
    expectVisibleText("Monitoring");
    expectVisibleText(RECONNECTING_MESSAGE);
  });

  it("does not show a reconnecting cue while a live session is running normally", () => {
    renderPanel({
      sessionStatus: "running",
      progress: buildProgress({
        status: "running",
        status_reason: "running",
        status_detail: null,
      }),
      sessionError: null,
    });

    expectTextHidden("Recovering");
    expectTextHidden("Trying to reconnect to the live stream.");
    expect(screen.getByText("Live monitoring is active.")).toBeTruthy();
  });

  it("renders terminal monitoring diagnostics from api stream failure metadata", () => {
    renderPanel({
      sessionStatus: "failed",
      progress: buildProgress({
        status: "failed",
        status_reason: "terminal_failure",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      }),
    });

    expect(
      screen.getByText(
        "Monitoring could not reconnect to the live stream, so it has ended.",
      ),
    ).toBeTruthy();
  });

  it("shows playback as a separate issue while monitoring keeps running", () => {
    renderPanel({
      sessionStatus: "running",
      playbackStatus: "error",
    });

    expect(
      screen.getByText(
        "Playback failed separately from monitoring. Monitoring may still be running; check the player panel for the playback-specific reason.",
      ),
    ).toBeTruthy();
  });

  it("keeps non-live cancelled wording distinct from live stopped-by-user messaging", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "cancelled",
      progress: buildProgress({
        status: "cancelled",
        current_item: null,
      }),
      playbackStatus: "stopped",
    });

    expectVisibleText("Stopped by user");
    expect(
      screen.getByText("Monitoring was stopped by the user. You can adjust the setup and start again."),
    ).toBeTruthy();
    expectTextHidden("Live monitoring was stopped by the user before the current stream completed.");
  });

  it("aligns non-live analysis progress with playback position for segment sources", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      playbackLive: false,
      playbackTime: 12,
      playbackDuration: 20,
      progress: buildProgress({
        processed_count: 9,
        total_count: 10,
      }),
    });

    expect(screen.getByText("Analysis")).toBeTruthy();
    expect(screen.getByText("6/10")).toBeTruthy();
  });

  it("warns when a local playlist completes with only partial segment analysis", () => {
    const { container } = renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      sessionStatus: "completed",
      playbackLive: false,
      playbackStatus: "stopped",
      progress: buildProgress({
        status: "completed",
        processed_count: 9,
        total_count: 10,
        current_item: "segment_0009.ts",
        status_reason: "completed",
        status_detail: null,
      }),
    });

    expectVisibleText("Completed with gaps");
    expect(
      screen.getByText(
        "Monitoring finished, but one or more local playlist segments were missing or could not be analyzed.",
      ),
    ).toBeTruthy();
    expectVisibleText("Monitoring finished with missing local items.");
    expectTextHidden("Monitoring finished successfully for the current source.");
    expectDiagnosticOrder(container, [
      "Monitoring Only 9 of 10 local playlist segments were analyzed. One or more items were missing or unreadable.",
    ]);
  });

  it("shows a waiting analysis label before the first live chunk is accepted", () => {
    renderPanel({
      sessionStatus: "running",
      progress: buildProgress({
        processed_count: 0,
        total_count: 0,
        current_item: null,
      }),
    });

    expect(screen.getByText("Live monitoring is active.")).toBeTruthy();
    expect(screen.getByText("Live, waiting for the first chunk")).toBeTruthy();
  });

  it("orders monitoring errors ahead of secondary playback diagnostics", () => {
    const { container } = renderPanel({
      sessionStatus: "failed",
      progress: buildProgress({
        status: "failed",
        status_reason: "source_unreachable",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      }),
      playbackStatus: "error",
    });

    expectDiagnosticOrder(container, [
      "Monitoring Monitoring could not reconnect to the live stream, so it has ended.",
      "Playback Playback is unavailable. Check the player panel for the playback-specific reason.",
    ]);
  });

  it("treats playback failure as terminal once monitoring is no longer running", () => {
    const { container } = renderPanel({
      sessionStatus: "completed",
      progress: buildProgress({
        status: "completed",
        status_reason: "completed",
        status_detail: null,
      }),
      playbackStatus: "error",
    });

    expectDiagnosticOrder(container, [
      "Playback Playback is unavailable. Check the player panel for the playback-specific reason.",
    ]);
  });

  it("shows raw lifecycle fields in the debug section when expanded", () => {
    renderPanel({
      sessionStatus: "failed",
      progress: buildProgress({
        status: "failed",
        status_reason: "source_unreachable",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      }),
    });

    expectVisibleText("Show debug info");
    expectVisibleText("Raw session status");
    expectVisibleText("failed");
    expectVisibleText("source_unreachable");
  });

  it("shows discovered live chunks separately in the debug section", () => {
    renderPanel({
      progress: buildProgress({
        processed_count: 2,
        total_count: 5,
      }),
    });

    expectVisibleText("Processed live chunks");
    expectVisibleText("2 chunks analyzed, 5 discovered");
  });
});
