import type { MonitoringSessionState, PlaybackStatus } from "../types";

export interface MonitoringControlStateArgs {
  sessionStatus: MonitoringSessionState;
  playbackStatus: PlaybackStatus;
  hasInputPath: boolean;
  hasSession: boolean;
}

export interface MonitoringControlState {
  startEnabled: boolean;
  endEnabled: boolean;
  controlsLocked: boolean;
  showPlayback: boolean;
  startBusy: boolean;
  endBusy: boolean;
}

export function getMonitoringControlState({
  sessionStatus,
  playbackStatus,
  hasInputPath,
  hasSession,
}: MonitoringControlStateArgs): MonitoringControlState {
  const sessionIsActive = ["starting", "pending", "running", "cancelling"].includes(sessionStatus);
  const playbackIsActive = ["loading", "playing"].includes(playbackStatus);
  const playbackIsTerminal = ["idle", "stopped", "error"].includes(playbackStatus);
  const sessionAllowsRestart = ["idle", "completed", "cancelled", "failed"].includes(sessionStatus);

  return {
    startEnabled: hasInputPath && sessionAllowsRestart && playbackIsTerminal,
    endEnabled: playbackIsActive,
    controlsLocked: sessionIsActive || playbackIsActive,
    showPlayback: hasSession || sessionStatus !== "idle" || playbackStatus !== "idle",
    startBusy: sessionStatus === "starting",
    endBusy: sessionStatus === "cancelling",
  };
}

export function isSetupFrozen(playbackStatus: PlaybackStatus): boolean {
  return ["loading", "playing"].includes(playbackStatus);
}
