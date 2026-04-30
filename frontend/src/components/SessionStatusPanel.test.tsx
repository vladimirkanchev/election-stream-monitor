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
};

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
  } satisfies React.ComponentProps<typeof SessionStatusPanel>;
}

function renderPanel(args: RenderPanelArgs = {}) {
  return render(<SessionStatusPanel {...buildPanelProps(args)} />);
}

// Exact UI copy is a first-class contract here, so keep the repeated lookup
// terse and let the behavior cases stay easy to scan.
function expectVisibleText(text: string) {
  expect(screen.getByText(text)).toBeTruthy();
}

// Some diagnostics are easier to validate by rendered ordering than by a
// single exact text node.
function getDiagnosticItems(container: HTMLElement) {
  return Array.from(container.querySelectorAll(".session-diagnostics__item")).map((item) =>
    item.textContent?.trim(),
  );
}

afterEach(() => {
  cleanup();
});

describe("SessionStatusPanel monitoring UX", () => {
  it("keeps live stop and terminal summaries distinct", () => {
    const { rerender } = renderPanel({
      sessionStatus: "cancelling",
      progress: { ...BASE_PROGRESS, status: "cancelling" },
    });

    expectVisibleText("Stopping now");
    expectVisibleText("The current monitoring run is settling a stop request.");
    expectVisibleText("A stop request is settling for the current live stream.");

    rerender(
      <SessionStatusPanel
        {...buildPanelProps({
          sessionStatus: "cancelled",
          progress: { ...BASE_PROGRESS, status: "cancelled", current_item: null },
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
          progress: {
            ...BASE_PROGRESS,
            status: "failed",
            status_reason: "source_unreachable",
            status_detail: SOURCE_UNREACHABLE_DETAIL,
          },
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
      progress: {
        ...BASE_PROGRESS,
        status: "completed",
        status_reason: "idle_poll_budget_exhausted",
        status_detail: "Idle poll budget exhausted",
      },
    });

    expectVisibleText("Ended after going quiet");
    expect(
      screen.getByText("Monitoring stopped after the live stream stopped sending new video."),
    ).toBeTruthy();
    expectVisibleText("The bounded live monitoring run completed for the current stream.");
    expect(
      screen.getByText(
        "The live stream stopped sending new video, so monitoring has ended.",
      ),
    ).toBeTruthy();
  });

  it("shows finished-cleanly live completion without the idle warning messaging", () => {
    renderPanel({
      sessionStatus: "completed",
      progress: {
        ...BASE_PROGRESS,
        status: "completed",
        status_reason: "completed",
        status_detail: null,
        current_item: null,
      },
    });

    expectVisibleText("Finished cleanly");
    expect(
      screen.getByText("The live monitoring run reached a normal completion point."),
    ).toBeTruthy();
    expectVisibleText("The bounded live monitoring run completed for the current stream.");
    expect(screen.queryByText("Ended after going quiet")).toBeNull();
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
      progress: {
        ...BASE_PROGRESS,
        status: "running",
        status_reason: "running",
        status_detail: null,
      },
      sessionError: null,
    });

    expect(screen.queryByText("Recovering")).toBeNull();
    expect(screen.queryByText("Trying to reconnect to the live stream.")).toBeNull();
    expect(screen.getByText("Live monitoring is active and currently analyzing live-window-002.")).toBeTruthy();
  });

  it("renders terminal monitoring diagnostics from api stream failure metadata", () => {
    renderPanel({
      sessionStatus: "failed",
      progress: {
        ...BASE_PROGRESS,
        status: "failed",
        status_reason: "terminal_failure",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      },
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
      progress: {
        ...BASE_PROGRESS,
        status: "cancelled",
        current_item: null,
      },
      playbackStatus: "stopped",
    });

    expect(screen.getByText("Stopped by user")).toBeTruthy();
    expect(screen.getByText("Monitoring was ended by the user.")).toBeTruthy();
    expect(
      screen.getByText("Monitoring was stopped by the user. You can adjust the setup and start again."),
    ).toBeTruthy();
    expect(
      screen.queryByText("Live monitoring was stopped by the user before the current stream completed."),
    ).toBeNull();
  });

  it("aligns non-live analysis progress with playback position for segment sources", () => {
    renderPanel({
      source: VIDEO_SEGMENTS_SOURCE,
      playbackLive: false,
      playbackTime: 12,
      playbackDuration: 20,
      progress: {
        ...BASE_PROGRESS,
        processed_count: 9,
        total_count: 10,
      },
    });

    expect(screen.getByText("Analysis")).toBeTruthy();
    expect(screen.getByText("6/10")).toBeTruthy();
  });

  it("shows a waiting analysis label before the first live chunk is accepted", () => {
    renderPanel({
      sessionStatus: "running",
      progress: {
        ...BASE_PROGRESS,
        processed_count: 0,
        total_count: 0,
        current_item: null,
      },
    });

    expect(screen.getByText("Live monitoring is active for the current stream.")).toBeTruthy();
    expect(screen.getByText("Live, waiting for the first chunk")).toBeTruthy();
  });

  it("orders monitoring errors ahead of secondary playback diagnostics", () => {
    const { container } = renderPanel({
      sessionStatus: "failed",
      progress: {
        ...BASE_PROGRESS,
        status: "failed",
        status_reason: "source_unreachable",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      },
      playbackStatus: "error",
    });

    expect(getDiagnosticItems(container)).toEqual([
      "Monitoring Monitoring could not reconnect to the live stream, so it has ended.",
      "Playback Playback is unavailable. Check the player panel for the playback-specific reason.",
    ]);
  });

  it("treats playback failure as terminal once monitoring is no longer running", () => {
    const { container } = renderPanel({
      sessionStatus: "completed",
      progress: {
        ...BASE_PROGRESS,
        status: "completed",
        status_reason: "completed",
        status_detail: null,
      },
      playbackStatus: "error",
    });

    expect(getDiagnosticItems(container)).toEqual([
      "Playback Playback is unavailable. Check the player panel for the playback-specific reason.",
    ]);
  });

  it("shows raw lifecycle fields in the debug section when expanded", () => {
    renderPanel({
      sessionStatus: "failed",
      progress: {
        ...BASE_PROGRESS,
        status: "failed",
        status_reason: "source_unreachable",
        status_detail: SOURCE_UNREACHABLE_DETAIL,
      },
    });

    expectVisibleText("Show debug info");
    expectVisibleText("Raw session status");
    expectVisibleText("failed");
    expectVisibleText("source_unreachable");
    expectVisibleText(SOURCE_UNREACHABLE_DETAIL);
    expectVisibleText("video_blur");
  });

  it("shows discovered live chunks separately in the debug section", () => {
    renderPanel({
      progress: {
        ...BASE_PROGRESS,
        processed_count: 2,
        total_count: 5,
      },
    });

    expectVisibleText("Processed live chunks");
    expectVisibleText("2 chunks analyzed, 5 discovered");
  });
});
