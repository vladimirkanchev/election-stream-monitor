import type { MonitorSource, PlaybackStatus } from "../types";

export function getResolvedPlaybackStatus(args: {
  sourceKind: MonitorSource["kind"];
  hasMediaSource: boolean;
  playbackActive: boolean;
}): PlaybackStatus {
  const { sourceKind, hasMediaSource, playbackActive } = args;

  if (!hasMediaSource) {
    return sourceKind === "video_segments" ? "loading" : "error";
  }

  return playbackActive ? "loading" : "stopped";
}

export function getStoppedPlaybackStatus(currentStatus: PlaybackStatus): PlaybackStatus {
  return currentStatus === "error" ? currentStatus : "stopped";
}
