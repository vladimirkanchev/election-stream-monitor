import { describe, expect, it } from "vitest";

import { getMonitoringControlState } from "./monitoringControls";

describe("getMonitoringControlState", () => {
  it("enables start only when the session is restartable and playback is terminal", () => {
    expect(
      getMonitoringControlState({
        sessionStatus: "idle",
        playbackStatus: "idle",
        hasInputPath: true,
        hasSession: false,
      }).startEnabled,
    ).toBe(true);

    expect(
      getMonitoringControlState({
        sessionStatus: "running",
        playbackStatus: "idle",
        hasInputPath: true,
        hasSession: true,
      }).startEnabled,
    ).toBe(false);

    expect(
      getMonitoringControlState({
        sessionStatus: "idle",
        playbackStatus: "playing",
        hasInputPath: true,
        hasSession: false,
      }).startEnabled,
    ).toBe(false);
  });

  it("enables end only while playback is loading or playing", () => {
    expect(
      getMonitoringControlState({
        sessionStatus: "running",
        playbackStatus: "loading",
        hasInputPath: true,
        hasSession: true,
      }).endEnabled,
    ).toBe(true);

    expect(
      getMonitoringControlState({
        sessionStatus: "completed",
        playbackStatus: "playing",
        hasInputPath: true,
        hasSession: true,
      }).endEnabled,
    ).toBe(true);

    expect(
      getMonitoringControlState({
        sessionStatus: "completed",
        playbackStatus: "stopped",
        hasInputPath: true,
        hasSession: true,
      }).endEnabled,
    ).toBe(false);
  });
});
