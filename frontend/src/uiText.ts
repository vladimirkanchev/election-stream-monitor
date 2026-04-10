import type { InputMode, MonitoringSessionState } from "./types";

export function formatSourceModeLabel(mode: InputMode): string {
  switch (mode) {
    case "video_segments":
      return "Video segments";
    case "video_files":
      return "Video files";
    case "api_stream":
      return "API stream";
    default:
      return mode;
  }
}

export function getSourcePathPlaceholder(mode: InputMode): string {
  switch (mode) {
    case "video_segments":
      return "/data/streams/segments";
    case "video_files":
      return "/data/streams/local";
    case "api_stream":
      return "https://example.com/live/index.m3u8";
    default:
      return "/data/input";
  }
}

export function getSourcePathHint(mode: InputMode): string {
  switch (mode) {
    case "video_segments":
      return "Use a folder with .ts segments and an index.m3u8 playlist.";
    case "video_files":
      return "Use a local .mp4 file or a folder that contains playable .mp4 files.";
    case "api_stream":
      return "Use a remote HLS or other supported stream URL.";
    default:
      return "Select a local source path to start monitoring.";
  }
}

export function formatMonitoringStatus(status: MonitoringSessionState): string {
  switch (status) {
    case "starting":
      return "Starting";
    case "pending":
      return "Preparing";
    case "running":
      return "Running";
    case "cancelling":
      return "Ending";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Stopped";
    case "failed":
      return "Failed";
    case "idle":
    default:
      return "Ready";
  }
}
