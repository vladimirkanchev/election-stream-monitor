import type { MonitorSource } from "../types";
import { formatSourceModeLabel } from "../uiText";

interface StartupPreviewPanelProps {
  source: MonitorSource;
}

export function StartupPreviewPanel({ source }: StartupPreviewPanelProps) {
  return (
    <section className="monitor-card video-panel">
      <div className="monitor-card__header">
        <h2>Live View</h2>
        <span>{formatSourceModeLabel(source.kind)}</span>
      </div>
      <div
        aria-label={`Live stream preview for ${formatMode(source.kind)} from ${
          source.path || "no source selected"
        }`}
        className="video-panel__surface video-panel__surface--preview"
      >
        <div className="video-panel__placeholder">
          <strong>Waiting to start</strong>
          <p>
            {source.path
              ? `The player is ready for ${formatSourceModeLabel(source.kind).toLowerCase()} from ${source.path}.`
              : getEmptySourceMessage(source.kind)}
          </p>
        </div>
      </div>
    </section>
  );
}

function formatMode(mode: MonitorSource["kind"]): string {
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

function getEmptySourceMessage(mode: MonitorSource["kind"]): string {
  if (mode === "api_stream") {
    return "Paste a direct .m3u8 or .mp4 URL and start monitoring to begin playback.";
  }
  return "Select a source path and start monitoring to begin playback.";
}
