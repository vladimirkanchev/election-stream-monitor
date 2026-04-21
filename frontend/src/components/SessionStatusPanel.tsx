import { formatPlaybackClock } from "../playbackMoments";
import type {
  MonitorSource,
  MonitoringSessionState,
  PlaybackStatus,
  SessionProgress,
} from "../types";
import { getApiStreamSessionStateMessage } from "../uiErrors";
import {
  formatMonitoringStatus,
  formatSourceModeLabel,
} from "../uiText";

interface SessionStatusPanelProps {
  source: MonitorSource;
  sessionStatus: MonitoringSessionState;
  progress: SessionProgress | null;
  selectedDetectorCount: number;
  visibleAlertCount: number;
  playbackTime: number;
  playbackDuration: number | null;
  playbackLive: boolean;
  playbackStatus: PlaybackStatus;
  sessionError: string | null;
}

export function SessionStatusPanel({
  source,
  sessionStatus,
  progress,
  selectedDetectorCount,
  visibleAlertCount,
  playbackTime,
  playbackDuration,
  playbackLive,
  playbackStatus,
  sessionError,
}: SessionStatusPanelProps) {
  const statusLabel = formatMonitoringStatus(sessionStatus);
  const analysisLabel = formatAnalysisProgress(
    source,
    progress,
    playbackTime,
    playbackDuration,
    playbackLive,
  );
  const playbackLabel = formatPlaybackProgress(playbackTime, playbackDuration, playbackLive);
  const diagnostics = buildDiagnostics({
    source,
    sessionStatus,
    progress,
    sessionError,
    playbackStatus,
  });

  return (
    <section className="monitor-card monitor-card--quiet">
      <div className="monitor-card__header">
        <h2>Session</h2>
        <span>{statusLabel}</span>
      </div>
      <dl className="status-grid status-grid--compact">
        <div>
          <dt>Source</dt>
          <dd>{formatSourceModeLabel(source.kind)}</dd>
        </div>
        <div>
          <dt>Detectors</dt>
          <dd>{selectedDetectorCount} selected</dd>
        </div>
        <div>
          <dt>Analysis</dt>
          <dd>{analysisLabel}</dd>
        </div>
        <div>
          <dt>Playback</dt>
          <dd>{playbackLabel}</dd>
        </div>
        <div>
          <dt>Alerts</dt>
          <dd>{visibleAlertCount}</dd>
        </div>
      </dl>
      <p className="management-copy">
        {buildSessionMessage(source, sessionStatus, source.path, progress?.current_item)}
      </p>
      {diagnostics.length > 0 ? (
        <div className="session-diagnostics">
          {diagnostics.map((diagnostic) => (
            <p
              key={`${diagnostic.kind}-${diagnostic.message}`}
              className={`session-diagnostics__item session-diagnostics__item--${diagnostic.kind}`}
            >
              <strong>{diagnostic.label}</strong> {diagnostic.message}
            </p>
          ))}
        </div>
      ) : null}
      {progress ? (
        <details className="session-debug">
          <summary>Show debug info</summary>
          <dl className="status-grid status-grid--compact">
            <div>
              <dt>Latest analyzed filename</dt>
              <dd>{progress.current_item ?? "None"}</dd>
            </div>
            <div>
              <dt>Raw session status</dt>
              <dd>{progress.status}</dd>
            </div>
            <div>
              <dt>Status reason</dt>
              <dd>{progress.status_reason ?? "None"}</dd>
            </div>
            <div>
              <dt>Status detail</dt>
              <dd>{progress.status_detail ?? "None"}</dd>
            </div>
            <div>
              <dt>Latest detectors run</dt>
              <dd>
                {progress.latest_result_detectors.length > 0
                  ? progress.latest_result_detectors.join(", ")
                  : "None"}
              </dd>
            </div>
            <div>
              <dt>{source.kind === "api_stream" ? "Processed live chunks" : "Processed item index"}</dt>
              <dd>{formatDebugProgress(source, progress)}</dd>
            </div>
          </dl>
        </details>
      ) : null}
    </section>
  );
}

function buildSessionMessage(
  source: MonitorSource,
  status: MonitoringSessionState,
  sourcePath: string,
  currentItem: string | null | undefined,
): string {
  const isApiStream = source.kind === "api_stream";
  if (!sourcePath) {
    return "Select a source path and the detectors you want to use before starting monitoring.";
  }

  if (status === "idle") {
    return "The current setup is ready. Start monitoring when you want playback and alerts to begin.";
  }

  if (status === "starting" || status === "pending") {
    if (isApiStream) {
      return "Connecting to the selected live stream and preparing the first chunks for monitoring.";
    }
    return "The session is preparing the selected source for playback and detector processing.";
  }

  if (status === "running") {
    if (isApiStream) {
      return currentItem
        ? `Live monitoring is active and currently analyzing ${currentItem}.`
        : "Live monitoring is active for the current stream.";
    }
    return "Playback and monitoring are running for the current source.";
  }

  if (status === "cancelling") {
    if (isApiStream) {
      return "Live monitoring is stopping cleanly for the current stream.";
    }
    return "The current session is ending. Playback and monitoring are being stopped cleanly.";
  }

  if (status === "completed") {
    if (isApiStream) {
      return "The bounded live monitoring run has ended for the current stream.";
    }
    return "Monitoring finished successfully for the current source.";
  }

  if (status === "cancelled") {
    if (isApiStream) {
      return "Live monitoring was stopped by the user. You can start it again when needed.";
    }
    return "Monitoring was stopped by the user. You can adjust the setup and start again.";
  }

  if (status === "failed") {
    if (isApiStream) {
      return "Live monitoring ended with an error. Check the monitoring details for the specific live-stream reason.";
    }
    return "Monitoring ended with an error. Check the source path and try again.";
  }

  return "The session is ready.";
}

function formatPlaybackProgress(
  playbackTime: number,
  playbackDuration: number | null,
  playbackLive: boolean,
): string {
  const elapsedLabel = formatPlaybackClock(playbackTime);
  if (playbackLive) {
    return `${elapsedLabel} live`;
  }
  if (playbackDuration && Number.isFinite(playbackDuration) && playbackDuration > 0) {
    return `${elapsedLabel}/${formatPlaybackClock(playbackDuration)}`;
  }
  return elapsedLabel;
}

function formatAnalysisProgress(
  source: MonitorSource,
  progress: SessionProgress | null,
  playbackTime: number,
  playbackDuration: number | null,
  playbackLive: boolean,
): string {
  if (!progress) {
    return "Not started";
  }

  if (source.kind === "api_stream") {
    return formatLiveAnalysisProgress(progress);
  }

  const totalCount = progress.total_count || progress.processed_count || 0;
  if (totalCount <= 0) {
    return "Not started";
  }

  if (
    (source.kind === "video_files" || source.kind === "video_segments") &&
    !playbackLive &&
    playbackDuration &&
    Number.isFinite(playbackDuration) &&
    playbackDuration > 0
  ) {
    const ratio = Math.max(0, Math.min(1, playbackTime / playbackDuration));
    const alignedCount = Math.min(totalCount, Math.floor(ratio * totalCount));
    return `${alignedCount}/${totalCount}`;
  }

  return `${progress.processed_count}/${totalCount}`;
}

function formatLiveAnalysisProgress(progress: SessionProgress): string {
  const chunkCount = progress.processed_count;
  if (chunkCount <= 0) {
    return "Live, waiting for the first chunk";
  }

  const chunkLabel = chunkCount === 1 ? "chunk" : "chunks";
  return `Live, ${chunkCount} ${chunkLabel} analyzed`;
}

function buildDiagnostics(args: {
  source: MonitorSource;
  sessionStatus: MonitoringSessionState;
  progress: SessionProgress | null;
  sessionError: string | null;
  playbackStatus: PlaybackStatus;
}): Array<{
  kind: "warning" | "error";
  label: string;
  message: string;
}> {
  const diagnostics: Array<{
    kind: "warning" | "error";
    label: string;
    message: string;
  }> = [];
  const { source, sessionStatus, progress, sessionError, playbackStatus } = args;
  const showMonitoringDiagnostic = sessionStatus !== "idle";

  if (sessionError && showMonitoringDiagnostic) {
    diagnostics.push({
      kind: "warning",
      label: "Monitoring",
      message: sessionError,
    });
  } else if (source.kind === "api_stream" && showMonitoringDiagnostic) {
    const failedMessage = getApiStreamSessionStateMessage({
      status: progress?.status ?? null,
      statusReason: progress?.status_reason ?? null,
      statusDetail: progress?.status_detail ?? null,
    });
    if (failedMessage) {
      diagnostics.push({
        kind: "error",
        label: "Monitoring",
        message: failedMessage,
      });
    }
  }

  if (playbackStatus === "error") {
    diagnostics.push({
      kind: sessionStatus === "running" ? "warning" : "error",
      label: "Playback",
      message:
        sessionStatus === "running"
          ? "Playback failed separately from monitoring. Monitoring may still be running; check the player panel for the playback-specific reason."
          : "Playback is unavailable. Check the player panel for the playback-specific reason.",
    });
  }

  return diagnostics;
}

function formatDebugProgress(source: MonitorSource, progress: SessionProgress): string {
  if (source.kind !== "api_stream") {
    const totalCount = progress.total_count || progress.processed_count;
    return `${progress.processed_count}/${totalCount}`;
  }

  const discoveredCount = Math.max(progress.total_count, progress.processed_count);
  const chunkLabel = progress.processed_count === 1 ? "chunk" : "chunks";
  if (discoveredCount > progress.processed_count) {
    return `${progress.processed_count} ${chunkLabel} analyzed, ${discoveredCount} discovered`;
  }

  return `${progress.processed_count} ${chunkLabel} analyzed`;
}
