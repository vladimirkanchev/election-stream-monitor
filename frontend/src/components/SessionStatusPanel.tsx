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
  const statusTone = getStatusTone({
    source,
    sessionStatus,
    progress,
    sessionError,
  });
  const sessionCue = buildSessionCue({
    source,
    sessionStatus,
    progress,
    sessionError,
  });
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
        <span className={`monitor-card__status monitor-card__status--${statusTone}`}>
          {statusLabel}
        </span>
      </div>
      <div className={`session-overview session-overview--${statusTone}`}>
        <p className="session-overview__eyebrow">
          {sessionCue ? sessionCue.label : "Current state"}
        </p>
        <p className="management-copy session-overview__message">
          {buildSessionMessage(source, sessionStatus, source.path, progress?.current_item)}
        </p>
        {sessionCue ? (
          <p className={`session-overview__cue session-overview__cue--${sessionCue.tone}`}>
            {sessionCue.message}
          </p>
        ) : null}
      </div>
      {diagnostics.length > 0 ? (
        <div className="session-diagnostics">
          {diagnostics.map((diagnostic) => (
            <p
              key={`${diagnostic.kind}-${diagnostic.label}-${diagnostic.message}`}
              className={`session-diagnostics__item session-diagnostics__item--${diagnostic.kind}`}
            >
              <strong>{diagnostic.label}</strong> {diagnostic.message}
            </p>
          ))}
        </div>
      ) : null}
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
      return "A stop request is settling for the current live stream.";
    }
    return "The current session is ending. Playback and monitoring are being stopped cleanly.";
  }

  if (status === "completed") {
    if (isApiStream) {
      return "The bounded live monitoring run completed for the current stream.";
    }
    return "Monitoring finished successfully for the current source.";
  }

  if (status === "cancelled") {
    if (isApiStream) {
      return "Live monitoring was stopped by the user before the current stream completed.";
    }
    return "Monitoring was stopped by the user. You can adjust the setup and start again.";
  }

  if (status === "failed") {
    if (isApiStream) {
      return "Live monitoring ended before this stream finished. Check the details below for more information.";
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

function getStatusTone(args: {
  source: MonitorSource;
  sessionStatus: MonitoringSessionState;
  progress: SessionProgress | null;
  sessionError: string | null;
}): "active" | "warning" | "terminal" | "idle" {
  const { source, sessionStatus, progress, sessionError } = args;
  if (source.kind === "api_stream" && sessionStatus === "running" && sessionError) {
    return "warning";
  }
  if (
    source.kind === "api_stream"
    && sessionStatus === "completed"
    && progress?.status_reason === "idle_poll_budget_exhausted"
  ) {
    return "warning";
  }

  switch (sessionStatus) {
    case "starting":
    case "pending":
    case "running":
    case "completed":
      return "active";
    case "cancelling":
      return "warning";
    case "failed":
      return "terminal";
    case "cancelled":
      return "idle";
    case "idle":
    default:
      return "idle";
  }
}

function buildSessionCue(args: {
  source: MonitorSource;
  sessionStatus: MonitoringSessionState;
  progress: SessionProgress | null;
  sessionError: string | null;
}): {
  label: string;
  message: string;
  tone: "active" | "warning" | "terminal" | "idle";
} | null {
  const { source, sessionStatus, progress, sessionError } = args;

  if (source.kind === "api_stream" && sessionStatus === "running" && sessionError) {
    return {
      label: "Recovering",
      message: "Trying to reconnect to the live stream.",
      tone: "warning",
    };
  }

  if (sessionStatus === "cancelling") {
    return {
      label: "Stopping now",
      message: "The current monitoring run is settling a stop request.",
      tone: "warning",
    };
  }

  if (source.kind === "api_stream" && sessionStatus === "completed") {
    if (progress?.status_reason === "idle_poll_budget_exhausted") {
      return {
        label: "Ended after going quiet",
        message: "Monitoring stopped after the live stream stopped sending new video.",
        tone: "warning",
      };
    }
    return {
      label: "Finished cleanly",
      message: "The live monitoring run reached a normal completion point.",
      tone: "active",
    };
  }

  if (sessionStatus === "cancelled") {
    return {
      label: "Stopped by user",
      message: "Monitoring was ended by the user.",
      tone: "idle",
    };
  }

  if (sessionStatus === "failed") {
    return {
      label: "Needs attention",
      message: "Monitoring ended with a problem that needs review.",
      tone: "terminal",
    };
  }

  return null;
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

  return diagnostics.sort((left, right) => {
    const kindWeight = (kind: "warning" | "error") => (kind === "error" ? 0 : 1);
    const labelWeight = (label: string) => (label === "Monitoring" ? 0 : 1);
    return kindWeight(left.kind) - kindWeight(right.kind)
      || labelWeight(left.label) - labelWeight(right.label);
  });
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
