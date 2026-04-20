import { useEffect, useState } from "react";

import { localBridge } from "../bridge";
import type {
  MonitoringSessionState,
  MonitorSource,
  SessionSnapshot,
  SessionStatus,
  SessionSummary,
} from "../types";
import {
  getApiStreamOperatorMessage,
  getApiStreamSessionStateMessage,
  getSessionStartErrorMessage,
  getSessionStopErrorMessage,
} from "../uiErrors";

const EMPTY_SNAPSHOT: SessionSnapshot = {
  session: null,
  progress: null,
  alerts: [],
  results: [],
  latest_result: null,
};
const ACTIVE_SESSION_STATUSES: SessionStatus[] = ["pending", "running", "cancelling"];
const RUNNING_SESSION_STATUSES: SessionStatus[] = ["pending", "running"];

interface UseMonitoringSessionArgs {
  source: MonitorSource;
}

interface UseMonitoringSessionResult {
  sessionSummary: SessionSummary | null;
  sessionSnapshot: SessionSnapshot;
  monitoringSessionStatus: MonitoringSessionState;
  sessionError: string | null;
  startMonitoring: (selectedDetectors: string[]) => Promise<boolean>;
  endMonitoring: () => Promise<void>;
}

export function useMonitoringSession({
  source,
}: UseMonitoringSessionArgs): UseMonitoringSessionResult {
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [snapshot, setSnapshot] = useState<SessionSnapshot>(EMPTY_SNAPSHOT);
  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentSession = snapshot.session ?? session;
  const currentStatus = currentSession?.status;
  const isSessionActive = isActiveStatus(currentStatus);
  const isSessionRunning = isRunningStatus(currentStatus);
  const sessionStatus: MonitoringSessionState = starting ? "starting" : currentStatus ?? "idle";
  const canStart = Boolean(source.path) && !starting && !ending && !isSessionActive;

  useEffect(() => {
    if (!currentSession?.session_id || !isSessionActive) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      localBridge.readSession(currentSession.session_id)
        .then((nextSnapshot) => {
          applySnapshot(nextSnapshot, currentSession, setSnapshot, setSession);
          if (currentSession.mode === "api_stream") {
            setError(
              getApiStreamSessionStateMessage({
                status: nextSnapshot.session?.status ?? currentSession.status,
                statusReason: nextSnapshot.progress?.status_reason ?? null,
                statusDetail: nextSnapshot.progress?.status_detail ?? null,
              }),
            );
          }
          if (!isActiveStatus(nextSnapshot.session?.status)) {
            setStarting(false);
            setEnding(false);
          }
        })
        .catch(() => {
          // Snapshot polling is intentionally tolerant: keep the last good state
          // in the UI and try again on the next interval instead of clearing the
          // current session on one transient read failure.
          if (currentSession.mode === "api_stream") {
            setError(getApiStreamOperatorMessage("reconnecting"));
          }
        });
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [currentSession?.session_id, isSessionActive]);

  const startMonitoring = async (selectedDetectors: string[]): Promise<boolean> => {
    if (!canStart) {
      return false;
    }

    setStarting(true);
    setError(null);
    setSession(null);
    setSnapshot(EMPTY_SNAPSHOT);
    try {
      const nextSession = await localBridge.startSession({
        source,
        selectedDetectors,
      });
      setSession(nextSession);
      const nextSnapshot = await localBridge.readSession(nextSession.session_id);
      applySnapshot(nextSnapshot, nextSession, setSnapshot, setSession);
      return true;
    } catch (caughtError) {
      setError(getSessionStartErrorMessage(caughtError, source.kind));
      setSession(null);
      setSnapshot(EMPTY_SNAPSHOT);
      return false;
    } finally {
      setStarting(false);
    }
  };

  const endMonitoring = async (): Promise<void> => {
    if (!currentSession || ending) {
      return;
    }

    setEnding(true);
    setError(null);
    try {
      if (isSessionRunning) {
        const nextSession = await localBridge.cancelSession(currentSession.session_id);
        // A cancel bridge success may legitimately return null when the backend
        // accepted the stop request without an updated session summary payload.
        if (nextSession) {
          setSession(nextSession);
          setSnapshot((current) => updateSnapshotSession(current, nextSession));
        }
      }
    } catch (caughtError) {
      setError(getSessionStopErrorMessage(caughtError));
    } finally {
      setEnding(false);
    }
  };

  return {
    sessionSummary: currentSession,
    sessionSnapshot: snapshot,
    monitoringSessionStatus: sessionStatus,
    sessionError: error,
    startMonitoring,
    endMonitoring,
  };
}

function isActiveStatus(status: SessionStatus | undefined): boolean {
  return status ? ACTIVE_SESSION_STATUSES.includes(status) : false;
}

function isRunningStatus(status: SessionStatus | undefined): boolean {
  return status ? RUNNING_SESSION_STATUSES.includes(status) : false;
}

function applySnapshot(
  nextSnapshot: SessionSnapshot,
  fallbackSession: SessionSummary | null,
  setSnapshot: (snapshot: SessionSnapshot) => void,
  setSession: (session: SessionSummary | null) => void,
): void {
  const mergedSession = nextSnapshot.session ?? fallbackSession;
  setSnapshot({
    ...nextSnapshot,
    session: mergedSession,
  });
  setSession(mergedSession);
}

function updateSnapshotSession(
  snapshot: SessionSnapshot,
  session: SessionSummary,
): SessionSnapshot {
  return {
    ...snapshot,
    session,
    progress: snapshot.progress
      ? { ...snapshot.progress, status: session.status }
      : snapshot.progress,
    };
}
