import { describe, expect, it } from "vitest";

import { getResolvedPlaybackStatus, getStoppedPlaybackStatus } from "./playbackState";

describe("playback state transitions", () => {
  it("maps resolved playback state for loading, playing, and error cases", () => {
    expect(
      getResolvedPlaybackStatus({
        sourceKind: "video_files",
        hasMediaSource: true,
        playbackActive: true,
      }),
    ).toBe("loading");

    expect(
      getResolvedPlaybackStatus({
        sourceKind: "api_stream",
        hasMediaSource: true,
        playbackActive: true,
      }),
    ).toBe("loading");

    expect(
      getResolvedPlaybackStatus({
        sourceKind: "video_files",
        hasMediaSource: false,
        playbackActive: true,
      }),
    ).toBe("error");
  });

  it("preserves error status when stopping playback", () => {
    expect(getStoppedPlaybackStatus("error")).toBe("error");
    expect(getStoppedPlaybackStatus("playing")).toBe("stopped");
  });
});
