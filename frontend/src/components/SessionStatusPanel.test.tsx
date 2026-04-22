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

function renderPanel(args: {
  progress?: SessionProgress | null;
  sessionStatus?: "idle" | "starting" | "pending" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  playbackStatus?: PlaybackStatus;
  sessionError?: string | null;
}) {
  return render(
    <SessionStatusPanel
      source={API_STREAM_SOURCE}
      sessionStatus={args.sessionStatus ?? "running"}
      progress={args.progress ?? BASE_PROGRESS}
      selectedDetectorCount={1}
      visibleAlertCount={0}
      playbackTime={5}
      playbackDuration={null}
      playbackLive
      playbackStatus={args.playbackStatus ?? "playing"}
      sessionError={args.sessionError ?? null}
    />,
  );
}

afterEach(() => {
  cleanup();
});

describe("SessionStatusPanel monitoring UX", () => {
  it("keeps live stop and terminal summaries distinct", () => {
    const { rerender } = render(
      <SessionStatusPanel
        source={API_STREAM_SOURCE}
        sessionStatus="cancelling"
        progress={{ ...BASE_PROGRESS, status: "cancelling" }}
        selectedDetectorCount={1}
        visibleAlertCount={0}
        playbackTime={5}
        playbackDuration={null}
        playbackLive
        playbackStatus="playing"
        sessionError={null}
      />,
    );

    expect(screen.getByText("Stopping now")).toBeTruthy();
    expect(screen.getByText("The current monitoring run is settling a stop request.")).toBeTruthy();
    expect(screen.getByText("A stop request is settling for the current live stream.")).toBeTruthy();

    rerender(
      <SessionStatusPanel
        source={API_STREAM_SOURCE}
        sessionStatus="cancelled"
        progress={{ ...BASE_PROGRESS, status: "cancelled", current_item: null }}
        selectedDetectorCount={1}
        visibleAlertCount={0}
        playbackTime={5}
        playbackDuration={null}
        playbackLive
        playbackStatus="stopped"
        sessionError={null}
      />,
    );

    expect(screen.getByText("Stopped by user")).toBeTruthy();
    expect(screen.getByText("Monitoring was ended by the user.")).toBeTruthy();
    expect(
      screen.getByText("Live monitoring was stopped by the user before the current stream completed."),
    ).toBeTruthy();

    rerender(
      <SessionStatusPanel
        source={API_STREAM_SOURCE}
        sessionStatus="failed"
        progress={{
          ...BASE_PROGRESS,
          status: "failed",
          status_reason: "source_unreachable",
          status_detail: "api_stream reconnect budget exhausted: upstream returned HTTP 503",
        }}
        selectedDetectorCount={1}
        visibleAlertCount={0}
        playbackTime={5}
        playbackDuration={null}
        playbackLive
        playbackStatus="stopped"
        sessionError={null}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeTruthy();
    expect(screen.getByText("Monitoring ended with a problem that needs review.")).toBeTruthy();
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

    expect(screen.getByText("Ended after going quiet")).toBeTruthy();
    expect(
      screen.getByText("Monitoring stopped after the live stream stopped sending new video."),
    ).toBeTruthy();
    expect(screen.getByText("The bounded live monitoring run completed for the current stream.")).toBeTruthy();
    expect(
      screen.getByText(
        "The live stream stopped sending new video, so monitoring has ended.",
      ),
    ).toBeTruthy();
  });

  it("renders a reconnecting cue separately from terminal diagnostics", () => {
    renderPanel({
      sessionError: "The live stream dropped for a moment. Monitoring is trying to reconnect.",
    });

    expect(screen.getByText("Recovering")).toBeTruthy();
    expect(screen.getByText("Trying to reconnect to the live stream.")).toBeTruthy();
    expect(screen.getByText("Monitoring")).toBeTruthy();
    expect(
      screen.getByText("The live stream dropped for a moment. Monitoring is trying to reconnect."),
    ).toBeTruthy();
  });

  it("renders terminal monitoring diagnostics from api stream failure metadata", () => {
    renderPanel({
      sessionStatus: "failed",
      progress: {
        ...BASE_PROGRESS,
        status: "failed",
        status_reason: "terminal_failure",
        status_detail: "api_stream reconnect budget exhausted: upstream returned HTTP 503",
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

  it("orders monitoring errors ahead of secondary playback diagnostics", () => {
    const { container } = renderPanel({
      sessionStatus: "failed",
      progress: {
        ...BASE_PROGRESS,
        status: "failed",
        status_reason: "source_unreachable",
        status_detail: "api_stream reconnect budget exhausted: upstream returned HTTP 503",
      },
      playbackStatus: "error",
    });

    const diagnosticItems = Array.from(
      container.querySelectorAll(".session-diagnostics__item"),
    ).map((item) => item.textContent?.trim());

    expect(diagnosticItems).toEqual([
      "Monitoring Monitoring could not reconnect to the live stream, so it has ended.",
      "Playback Playback is unavailable. Check the player panel for the playback-specific reason.",
    ]);
  });
});
