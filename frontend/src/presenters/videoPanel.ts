import type { MonitorSource, PlaybackStatus } from "../types";
import {
  getPlaybackLoadingMessage,
  getPlaybackUnavailableDescription,
} from "../uiErrors";
import { formatSourceModeLabel } from "../uiText";

export interface VideoPanelDisplayModel {
  modeLabel: string;
  statusLabel: string;
  statusTone: "neutral" | "active" | "error";
  routeLabel: string;
  showPreparingState: boolean;
  showPlaybackUnavailable: boolean;
  loadingMessage: string;
  loadedFromLabel: string;
  loadedFromTitle: string;
  playbackTimeLabel: string;
  hintMessage: string | null;
  errorMessage: string | null;
}

interface BuildVideoPanelDisplayModelArgs {
  source: MonitorSource;
  currentItem: string | null;
  mediaSource: string | null;
  playbackStatus: PlaybackStatus;
  playbackTime: number;
  error: string | null;
}

export function buildVideoPanelDisplayModel({
  source,
  currentItem,
  mediaSource,
  playbackStatus,
  playbackTime,
  error,
}: BuildVideoPanelDisplayModelArgs): VideoPanelDisplayModel {
  const showPreparingState =
    !mediaSource &&
    (playbackStatus === "loading" || (source.kind === "video_segments" && !error));
  const showPlaybackUnavailable = !showPreparingState && !mediaSource;
  const loadedFrom = formatLoadedSource(source, currentItem);

  return {
    modeLabel: formatSourceModeLabel(source.kind),
    statusLabel: formatPlaybackStatus(playbackStatus, Boolean(error)),
    statusTone: error || playbackStatus === "error"
      ? "error"
      : playbackStatus === "playing"
        ? "active"
        : "neutral",
    routeLabel: formatPlaybackRoute(source, mediaSource),
    showPreparingState,
    showPlaybackUnavailable,
    loadingMessage: getPlaybackLoadingMessage(source.kind),
    loadedFromLabel: abbreviateMiddle(loadedFrom, 56),
    loadedFromTitle: loadedFrom,
    playbackTimeLabel: formatPlaybackTime(playbackTime),
    hintMessage: getHintMessage(source, mediaSource, error),
    errorMessage: error ?? (showPlaybackUnavailable ? getPlaybackUnavailableDescription() : null),
  };
}

function formatPlaybackStatus(
  playbackStatus: PlaybackStatus,
  hasError: boolean,
): string {
  if (hasError || playbackStatus === "error") {
    return "Playback error";
  }

  switch (playbackStatus) {
    case "loading":
      return "Preparing";
    case "playing":
      return "Playing";
    case "stopped":
      return "Stopped";
    case "idle":
    default:
      return "Idle";
  }
}

function formatPlaybackRoute(source: MonitorSource, mediaSource: string | null): string {
  if (!mediaSource) {
    switch (source.kind) {
      case "api_stream":
        return "Awaiting stream resolution";
      case "video_segments":
        return "Awaiting local playlist";
      case "video_files":
        return "Awaiting local file";
      default:
        return "Awaiting media source";
    }
  }

  if (source.kind === "video_segments") {
    return "Local HLS playlist";
  }
  if (mediaSource.startsWith("local-media://proxy/")) {
    return "Local HLS proxy";
  }
  if (mediaSource.startsWith("local-media://media/")) {
    return "Local media bridge";
  }
  if (/^https?:\/\//i.test(mediaSource)) {
    return "Direct remote media";
  }
  return "Direct local media";
}

function getHintMessage(
  source: MonitorSource,
  mediaSource: string | null,
  error: string | null,
): string | null {
  if (error || !mediaSource) {
    return null;
  }

  if (source.kind === "video_segments") {
    return "Playback is using the local HLS playlist.";
  }
  if (source.kind === "api_stream" && mediaSource.startsWith("local-media://proxy/")) {
    return "Remote HLS playback is routed through the local proxy.";
  }
  if (source.kind === "api_stream" && /^https?:\/\//i.test(mediaSource)) {
    return "Playback is using the direct remote media file.";
  }
  if (source.kind === "video_files") {
    return "Playback is using the selected local media file.";
  }
  return null;
}

function formatLoadedSource(source: MonitorSource, currentItem: string | null): string {
  if (source.kind === "video_segments" || source.kind === "video_files") {
    return source.path;
  }

  if (!currentItem) {
    return source.path;
  }

  const trimmed = source.path.replace(/\/$/, "");
  const looksLikeFilePath = /\/[^/]+\.[a-zA-Z0-9]{2,8}$/.test(trimmed);
  if (looksLikeFilePath) {
    return trimmed;
  }
  return `${trimmed}/${currentItem}`;
}

function abbreviateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  const visible = maxLength - 1;
  const startLength = Math.ceil(visible / 2);
  const endLength = Math.floor(visible / 2);
  return `${value.slice(0, startLength)}…${value.slice(-endLength)}`;
}

function formatPlaybackTime(totalSeconds: number): string {
  const safeSeconds = Number.isFinite(totalSeconds) && totalSeconds > 0 ? totalSeconds : 0;
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = Math.floor(safeSeconds % 60);

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(
      seconds,
    ).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
