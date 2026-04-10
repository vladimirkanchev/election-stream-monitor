import { getAlertPlaybackMomentLabel, shouldRevealSegmentAlert } from "../playbackMoments";
import type { AlertEvent, DetectorOption, InputMode, SegmentStartTimes } from "../types";

export interface AlertFeedItem {
  key: string;
  alert: AlertEvent;
  title: string;
  message: string;
  sourceLabel: string;
  timestampLabel: string;
  severity: AlertEvent["severity"];
}

export function buildAlertFeedItems(
  alerts: AlertEvent[],
  detectors: DetectorOption[],
  sourceKind: InputMode,
  segmentStartTimes: SegmentStartTimes,
): AlertFeedItem[] {
  return alerts
    .slice()
    .reverse()
    .map((alert, index) => ({
      key: buildAlertKey(alert, index),
      alert,
      title: formatDetector(alert.detector_id, detectors),
      message: alert.message,
      sourceLabel: alert.source_name,
      timestampLabel: getAlertPlaybackMomentLabel(alert, sourceKind, segmentStartTimes),
      severity: alert.severity,
    }));
}

export function filterAlertsForPlayback(args: {
  alerts: AlertEvent[];
  sourceKind: InputMode;
  playbackTime: number;
  playbackDuration: number | null;
  playbackLive: boolean;
  totalAnalysisCount: number;
  currentPlaybackItem: string | null;
  segmentStartTimes: SegmentStartTimes;
}): AlertEvent[] {
  const {
    alerts,
    sourceKind,
    playbackTime,
    playbackDuration,
    playbackLive,
    totalAnalysisCount,
    currentPlaybackItem,
    segmentStartTimes,
  } = args;

  if (alerts.length === 0) {
    return alerts;
  }

  if (playbackLive || totalAnalysisCount <= 0) {
    return alerts;
  }

  if (sourceKind === "video_segments") {
    return filterSegmentAlerts(
      alerts,
      playbackTime,
      currentPlaybackItem,
      segmentStartTimes,
    );
  }

  if (
    !playbackDuration ||
    !Number.isFinite(playbackDuration) ||
    playbackDuration <= 0
  ) {
    return alerts;
  }

  const ratio = Math.max(0, Math.min(1, playbackTime / playbackDuration));
  const visibleSliceCount = Math.min(totalAnalysisCount, Math.floor(ratio * totalAnalysisCount));

  return filterFinitePlaybackAlerts(
    alerts,
    sourceKind,
    playbackTime,
    visibleSliceCount,
  );
}

function formatDetector(detectorId: string, detectors: DetectorOption[]): string {
  return (
    detectors.find((detector) => detector.id === detectorId)?.display_name ?? detectorId
  );
}

function buildAlertKey(alert: AlertEvent, index: number): string {
  return [
    alert.timestamp_utc,
    alert.detector_id,
    alert.source_name,
    alert.severity,
    index,
  ].join("-");
}

function filterSegmentAlerts(
  alerts: AlertEvent[],
  playbackTime: number,
  currentPlaybackItem: string | null,
  segmentStartTimes: SegmentStartTimes,
): AlertEvent[] {
  if (!currentPlaybackItem) {
    return [];
  }

  return alerts.filter((alert) =>
    shouldRevealSegmentAlert({
      alert,
      playbackTime,
      currentPlaybackItem,
      segmentStartTimes,
    }),
  );
}

function filterFinitePlaybackAlerts(
  alerts: AlertEvent[],
  sourceKind: InputMode,
  playbackTime: number,
  visibleSliceCount: number,
): AlertEvent[] {
  return alerts.filter((alert) => {
    if (sourceKind === "video_files" && typeof alert.window_start_sec === "number") {
      return alert.window_start_sec <= playbackTime + 1e-9;
    }

    if (typeof alert.window_index === "number") {
      return alert.window_index < visibleSliceCount;
    }

    return true;
  });
}
