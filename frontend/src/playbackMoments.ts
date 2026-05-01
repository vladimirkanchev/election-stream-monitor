import type { AlertEvent, InputMode, SegmentStartTimes } from "./types";

const PLAYBACK_EPSILON = 1e-9;

export function formatPlaybackClock(totalSeconds: number): string {
  const safeSeconds =
    Number.isFinite(totalSeconds) && totalSeconds > 0 ? Math.floor(totalSeconds) : 0;
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(
      seconds,
    ).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function getAlertPlaybackMomentLabel(
  alert: AlertEvent,
  sourceKind: InputMode,
  segmentStartTimes: SegmentStartTimes,
): string {
  if (sourceKind === "video_segments") {
    const segmentStart = getSegmentStartTime(alert.source_name, segmentStartTimes);
    return typeof segmentStart === "number"
      ? formatPlaybackClock(segmentStart)
      : alert.source_name;
  }

  if (sourceKind === "video_files" && typeof alert.window_start_sec === "number") {
    return formatPlaybackClock(alert.window_start_sec);
  }

  return alert.source_name;
}

export function shouldRevealSegmentAlert(args: {
  alert: AlertEvent;
  playbackTime: number;
  currentPlaybackItem: string | null;
  segmentStartTimes: SegmentStartTimes;
}): boolean {
  const { alert, playbackTime, currentPlaybackItem, segmentStartTimes } = args;
  const segmentStart = getSegmentStartTime(alert.source_name, segmentStartTimes);
  if (typeof segmentStart === "number") {
    return segmentStart <= playbackTime + PLAYBACK_EPSILON;
  }

  if (!currentPlaybackItem) {
    return false;
  }

  const currentSegmentNumber = extractSegmentNumber(currentPlaybackItem);
  const alertSegmentNumber = extractSegmentNumber(alert.source_name);
  if (currentSegmentNumber !== null && alertSegmentNumber !== null) {
    return alertSegmentNumber <= currentSegmentNumber;
  }

  return false;
}

function getSegmentStartTime(
  sourceName: string,
  segmentStartTimes: SegmentStartTimes,
): number | undefined {
  return segmentStartTimes[sourceName];
}

function extractSegmentNumber(sourceName: string): number | null {
  const match = sourceName.match(/segment_(\d+)\.ts$/i);
  if (!match) {
    return null;
  }
  return Number.parseInt(match[1] ?? "", 10);
}
