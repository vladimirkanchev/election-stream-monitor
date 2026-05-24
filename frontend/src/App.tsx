import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { localBridge } from "./bridge";
import { AlertFeed } from "./components/AlertFeed";
import { DetectorCatalog } from "./components/DetectorCatalog";
import { PathInput } from "./components/PathInput";
import { RunButton } from "./components/RunButton";
import { SessionStatusPanel } from "./components/SessionStatusPanel";
import { SourceModeSelector } from "./components/SourceModeSelector";
import { StartupPreviewPanel } from "./components/StartupPreviewPanel";
import { useMonitoringSession } from "./hooks/useMonitoringSession";
import { useSetupState } from "./hooks/useSetupState";
import { buildAlertFeedItems, filterAlertsForPlayback } from "./presenters/alertFeed";
import { createMonitorSource } from "./sourceModel";
import type {
  AlertEvent,
  DetectorOption,
  MonitorSource,
  PlaybackStatus,
} from "./types";
import { getMonitoringControlState, isSetupFrozen } from "./viewModels/monitoringControls";

const VideoPlayerPanel = lazy(async () => import("./components/VideoPlayerPanel")
  .then((module) => ({ default: module.VideoPlayerPanel })));
const AlertDetailsDrawer = lazy(async () => import("./components/AlertDetailsDrawer")
  .then((module) => ({ default: module.AlertDetailsDrawer })));

export default function App() {
  const [detectors, setDetectors] = useState<DetectorOption[]>([]);
  const [playbackRequested, setPlaybackRequested] = useState(false);
  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>("idle");
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState<number | null>(null);
  const [playbackLive, setPlaybackLive] = useState(false);
  const [currentPlaybackItem, setCurrentPlaybackItem] = useState<string | null>(null);
  const [segmentStartTimes, setSegmentStartTimes] = useState<Record<string, number>>({});
  const [selectedAlert, setSelectedAlert] = useState<AlertEvent | null>(null);
  const [revealedLocalAlertKeys, setRevealedLocalAlertKeys] = useState<string[]>([]);
  const setupFrozen = isSetupFrozen(playbackStatus);

  const {
    source: setupMonitorSource,
    visibleDetectors,
    selectedDetectors: setupSelectedDetectors,
    setSourceKind,
    setSourcePath,
    setSelectedDetectors: setSetupSelectedDetectors,
  } = useSetupState({
    detectors,
    frozen: setupFrozen,
  });

  const {
    sessionSummary,
    sessionSnapshot,
    monitoringSessionStatus,
    sessionError,
    startMonitoring,
    endMonitoring,
  } = useMonitoringSession({
    source: setupMonitorSource,
  });

  useEffect(() => {
    localBridge.listDetectors().then((items) => {
      setDetectors(items);
    });
  }, []);

  const controlState = getControlState({
    sessionStatus: monitoringSessionStatus,
    playbackStatus,
    hasInputPath: Boolean(setupMonitorSource.path),
    hasSession: Boolean(sessionSummary),
  });
  const showSetupFeedbackError = Boolean(sessionError) && !sessionSummary;
  const displaySource = getDisplaySource(sessionSummary, setupMonitorSource);
  const playbackVisibleAlerts = filterAlertsForPlayback({
    alerts: sessionSnapshot.alerts,
    sourceKind: displaySource.kind,
    playbackTime,
    playbackDuration,
    playbackLive,
    totalAnalysisCount: sessionSnapshot.progress?.total_count ?? 0,
    currentPlaybackItem,
    segmentStartTimes,
  });
  const displayedAlerts = useMemo(
    () => mergeDisplayedAlerts({
      allAlerts: sessionSnapshot.alerts,
      playbackVisibleAlerts,
      sourceKind: displaySource.kind,
      revealedAlertKeys: revealedLocalAlertKeys,
    }),
    [displaySource.kind, playbackVisibleAlerts, revealedLocalAlertKeys, sessionSnapshot.alerts],
  );
  const alertItems = buildAlertFeedItems(
    displayedAlerts,
    detectors,
    displaySource.kind,
    segmentStartTimes,
  );
  const localPlaylistWarning = buildLocalPlaylistWarning({
    source: displaySource,
    progress: sessionSnapshot.progress,
    segmentStartTimes,
  });

  useEffect(() => {
    setRevealedLocalAlertKeys([]);
  }, [sessionSnapshot.session?.session_id]);

  useEffect(() => {
    if (!usesStickyLocalAlertReveal(displaySource.kind) || playbackVisibleAlerts.length === 0) {
      return;
    }

    setRevealedLocalAlertKeys((currentKeys) => {
      const nextKeys = new Set(currentKeys);
      for (const alert of playbackVisibleAlerts) {
        nextKeys.add(buildAlertIdentity(alert));
      }
      return nextKeys.size === currentKeys.length
        ? currentKeys
        : Array.from(nextKeys);
    });
  }, [displaySource.kind, playbackVisibleAlerts]);

  useEffect(() => {
    if (!controlState.showPlayback && playbackStatus !== "idle") {
      setPlaybackStatus("idle");
    }
  }, [controlState.showPlayback, playbackStatus]);

  useEffect(() => {
    if (!controlState.showPlayback) {
      setPlaybackTime(0);
      setPlaybackDuration(null);
      setPlaybackLive(false);
      setCurrentPlaybackItem(null);
      setSegmentStartTimes({});
    }
  }, [controlState.showPlayback]);

  const handleStartMonitoring = async () => {
    if (!controlState.startEnabled) {
      return;
    }

    setPlaybackRequested(true);
    setPlaybackStatus("loading");
    setSelectedAlert(null);
    const didStart = await startMonitoring(setupSelectedDetectors);
    if (!didStart) {
      setPlaybackRequested(false);
      setPlaybackStatus("idle");
    }
  };

  const handleEndMonitoring = async () => {
    if (!controlState.endEnabled) {
      return;
    }

    setPlaybackRequested(false);
    await endMonitoring();
    setSelectedAlert(null);
  };

  return (
    <>
      <main className="app-shell app-shell--wide">
        <section className="setup-panel setup-panel--tall">
          <header className="setup-panel__header">
            <h1>Election Monitor</h1>
            <p>Select a local source, choose detectors, and start monitoring.</p>
          </header>

          <SourceModeSelector
            value={setupMonitorSource.kind}
            onChange={setSourceKind}
            disabled={controlState.controlsLocked}
          />
          <PathInput
            mode={setupMonitorSource.kind}
            value={setupMonitorSource.path}
            onChange={setSourcePath}
            disabled={controlState.controlsLocked}
          />
          <DetectorCatalog
            detectors={visibleDetectors}
            selected={setupSelectedDetectors}
            onChange={setSetupSelectedDetectors}
            disabled={controlState.controlsLocked}
          />
          <RunButton
            disabled={!controlState.startEnabled}
            running={controlState.startBusy}
            onClick={handleStartMonitoring}
          />
          <button
            className="run-button run-button--secondary"
            disabled={!controlState.endEnabled}
            type="button"
            onClick={handleEndMonitoring}
          >
            {controlState.endBusy ? "Ending Session..." : "End Monitoring"}
          </button>
          {showSetupFeedbackError ? (
            <p className="setup-panel__feedback setup-panel__feedback--error">{sessionError}</p>
          ) : null}
          {!showSetupFeedbackError && !setupMonitorSource.path ? (
            <p className="setup-panel__feedback">
              Add a local file or folder path to enable monitoring.
            </p>
          ) : null}
          <SessionStatusPanel
            source={setupMonitorSource}
            sessionStatus={monitoringSessionStatus}
            progress={sessionSnapshot.progress}
            selectedDetectorCount={setupSelectedDetectors.length}
            visibleAlertCount={displayedAlerts.length}
            playbackTime={playbackTime}
            playbackDuration={playbackDuration}
            playbackLive={playbackLive}
            playbackStatus={playbackStatus}
            sessionError={sessionError}
            localPlaylistWarning={localPlaylistWarning}
          />
        </section>

        <div className="setup-side">
          {controlState.showPlayback ? (
            <Suspense fallback={<PlaybackPanelFallback />}>
              <VideoPlayerPanel
                source={displaySource}
                currentItem={sessionSnapshot.progress?.current_item ?? null}
                playbackRequested={playbackRequested}
                onPlaybackStatusChange={setPlaybackStatus}
                onPlaybackMetricsChange={({ time, duration, isLive }) => {
                  setPlaybackTime(time);
                  setPlaybackDuration(duration);
                  setPlaybackLive(isLive);
                }}
                onPlaybackItemChange={setCurrentPlaybackItem}
                onPlaybackSegmentMapChange={setSegmentStartTimes}
              />
            </Suspense>
          ) : (
            <StartupPreviewPanel source={setupMonitorSource} />
          )}
          <AlertFeed
            items={alertItems}
            onSelect={setSelectedAlert}
            monitoringStarted={monitoringSessionStatus !== "idle"}
            totalRaisedCount={sessionSnapshot.alerts.length}
            playbackFiltered={displayedAlerts.length !== sessionSnapshot.alerts.length}
          />
        </div>
      </main>

      <Suspense fallback={null}>
        <AlertDetailsDrawer
          alert={selectedAlert}
          detectors={detectors}
          sourceKind={displaySource.kind}
          segmentStartTimes={segmentStartTimes}
          onClose={() => setSelectedAlert(null)}
        />
      </Suspense>
    </>
  );
}

function getDisplaySource(
  session: { mode: MonitorSource["kind"]; input_path: string } | null,
  setupMonitorSource: MonitorSource,
): MonitorSource {
  if (!session) {
    return setupMonitorSource;
  }

  return createMonitorSource(session.mode, session.input_path);
}

function getControlState(args: Parameters<typeof getMonitoringControlState>[0]) {
  return getMonitoringControlState(args);
}

function mergeDisplayedAlerts(args: {
  allAlerts: AlertEvent[];
  playbackVisibleAlerts: AlertEvent[];
  sourceKind: MonitorSource["kind"];
  revealedAlertKeys: string[];
}): AlertEvent[] {
  const {
    allAlerts,
    playbackVisibleAlerts,
    sourceKind,
    revealedAlertKeys,
  } = args;

  if (!usesStickyLocalAlertReveal(sourceKind)) {
    return playbackVisibleAlerts;
  }

  if (revealedAlertKeys.length === 0) {
    return playbackVisibleAlerts;
  }

  const visibleKeys = new Set(revealedAlertKeys);
  return allAlerts.filter((alert) => visibleKeys.has(buildAlertIdentity(alert)));
}

function usesStickyLocalAlertReveal(sourceKind: MonitorSource["kind"]): boolean {
  return sourceKind === "video_segments" || sourceKind === "video_files";
}

function buildLocalPlaylistWarning(args: {
  source: MonitorSource;
  progress: ReturnType<typeof useMonitoringSession>["sessionSnapshot"]["progress"];
  segmentStartTimes: Record<string, number>;
}): string | null {
  const { source, progress, segmentStartTimes } = args;
  if (source.kind !== "video_segments" || !progress) {
    return null;
  }
  if (progress.status !== "completed" || progress.total_count <= 0) {
    return null;
  }

  const playlistSegmentCount = Object.keys(segmentStartTimes).length;
  if (playlistSegmentCount <= progress.total_count) {
    return null;
  }

  return "Playlist has gaps. Playback may be incomplete.";
}

function buildAlertIdentity(alert: AlertEvent): string {
  return [
    alert.timestamp_utc,
    alert.detector_id,
    alert.source_name,
    alert.severity,
  ].join("-");
}

function PlaybackPanelFallback() {
  return (
    <section className="monitor-card video-panel">
      <div className="monitor-card__header">
        <h2>Live View</h2>
        <span>Loading player</span>
      </div>
      <div className="video-panel__surface">
        <div className="video-panel__placeholder">
          <strong>Preparing playback</strong>
          <p>Loading the playback panel for the current monitoring session.</p>
        </div>
      </div>
    </section>
  );
}
