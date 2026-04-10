import { useEffect, useState } from "react";

import { localBridge } from "./bridge";
import { AlertDetailsDrawer } from "./components/AlertDetailsDrawer";
import { AlertFeed } from "./components/AlertFeed";
import { DetectorCatalog } from "./components/DetectorCatalog";
import { PathInput } from "./components/PathInput";
import { RunButton } from "./components/RunButton";
import { SessionStatusPanel } from "./components/SessionStatusPanel";
import { SourceModeSelector } from "./components/SourceModeSelector";
import { StartupPreviewPanel } from "./components/StartupPreviewPanel";
import { VideoPlayerPanel } from "./components/VideoPlayerPanel";
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
  const visibleAlerts = filterAlertsForPlayback({
    alerts: sessionSnapshot.alerts,
    sourceKind: displaySource.kind,
    playbackTime,
    playbackDuration,
    playbackLive,
    totalAnalysisCount: sessionSnapshot.progress?.total_count ?? 0,
    currentPlaybackItem,
    segmentStartTimes,
  });
  const alertItems = buildAlertFeedItems(
    visibleAlerts,
    detectors,
    displaySource.kind,
    segmentStartTimes,
  );

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
            visibleAlertCount={visibleAlerts.length}
            playbackTime={playbackTime}
            playbackDuration={playbackDuration}
            playbackLive={playbackLive}
            playbackStatus={playbackStatus}
            sessionError={sessionError}
          />
        </section>

        <div className="setup-side">
          {controlState.showPlayback ? (
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
          ) : (
            <StartupPreviewPanel source={setupMonitorSource} />
          )}
          <AlertFeed
            items={alertItems}
            onSelect={setSelectedAlert}
            monitoringStarted={monitoringSessionStatus !== "idle"}
            totalRaisedCount={sessionSnapshot.alerts.length}
          />
        </div>
      </main>

      <AlertDetailsDrawer
        alert={selectedAlert}
        detectors={detectors}
        sourceKind={displaySource.kind}
        segmentStartTimes={segmentStartTimes}
        onClose={() => setSelectedAlert(null)}
      />
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
