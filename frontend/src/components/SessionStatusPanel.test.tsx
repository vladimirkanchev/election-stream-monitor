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

describe("SessionStatusPanel diagnostics", () => {
  it("shows a monitoring retry diagnostic when session polling is retrying", () => {
    renderPanel({
      sessionError: "The live stream is temporarily unavailable. Monitoring is reconnecting.",
    });

    expect(screen.getByText("Monitoring")).toBeTruthy();
    expect(
      screen.getByText("The live stream is temporarily unavailable. Monitoring is reconnecting."),
    ).toBeTruthy();
  });

  it("shows a terminal monitoring diagnostic from api stream failure metadata", () => {
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
        "The live stream could not be reconnected. Monitoring ended after the retry budget was exhausted.",
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
});
