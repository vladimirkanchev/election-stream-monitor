import type {
  AlertEvent,
  DetectorOption,
  PlaybackSourceRequest,
  ResultEvent,
  RunSessionInput,
  SessionProgress,
  SessionSnapshot,
  SessionSummary,
} from "../types";

const demoDetectors: DetectorOption[] = [
  {
    id: "video_metrics",
    display_name: "Black Screen",
    description:
      "Tracks duration, file size, and bitrate so you can spot weak or unusual stream quality.",
    category: "quality",
    origin: "built_in",
    status: "core",
    default_rule_id: "video_metrics.default_rule",
    default_selected: false,
    produces_alerts: false,
    supported_modes: ["video_segments", "video_files", "api_stream"],
    supported_suffixes: [".ts", ".mp4"],
  },
  {
    id: "video_blur",
    display_name: "Blur",
    description:
      "Flags soft or blurry video when the opening frame loses too much visual detail.",
    category: "quality",
    origin: "built_in",
    status: "optional",
    default_rule_id: "video_blur.default_rule",
    default_selected: false,
    produces_alerts: true,
    supported_modes: ["video_segments", "video_files", "api_stream"],
    supported_suffixes: [".ts", ".mp4"],
  },
];

const sessionStore = new Map<string, SessionSnapshot>();
const sessionHistory: SessionSummary[] = [];

function getDemoItemsForSourceKind(sourceKind: RunSessionInput["source"]["kind"]): string[] {
  if (sourceKind === "video_segments") {
    return ["segment_0001.ts", "segment_0002.ts", "segment_0003.ts", "segment_0004.ts"];
  }
  return ["election_recording.mp4"];
}

export async function listDetectors(): Promise<DetectorOption[]> {
  try {
    const response = await fetch("/detectors.json", { cache: "no-store" });
    if (response.ok) {
      return (await response.json()) as DetectorOption[];
    }
  } catch (_error) {
    // Keep the demo bridge self-contained when the generated detector catalog
    // is missing, for example in isolated frontend tests or lightweight UI demos.
  }

  return demoDetectors;
}

export async function listSessionHistory(): Promise<SessionSummary[]> {
  return sessionHistory.slice().reverse();
}

export async function startSession(
  input: RunSessionInput,
): Promise<SessionSummary> {
  const sessionId = `demo-${Date.now()}`;
  const items = getDemoItemsForSourceKind(input.source.kind);
  const session: SessionSummary = {
    session_id: sessionId,
    mode: input.source.kind,
    input_path: input.source.path,
    selected_detectors: input.selectedDetectors,
    status: "running",
  };
  const progress: SessionProgress = {
    session_id: sessionId,
    status: "running",
    processed_count: 0,
    total_count: items.length,
    current_item: null,
    latest_result_detector: null,
    alert_count: 0,
    last_updated_utc: new Date().toISOString(),
    latest_result_detectors: [],
  };

  sessionStore.set(sessionId, {
    session,
    progress,
    alerts: [],
    results: [],
    latest_result: null,
  });
  sessionHistory.push(session);

  simulateProgress(sessionId, input, items);
  return session;
}

export async function readSession(sessionId: string): Promise<SessionSnapshot> {
  return (
    sessionStore.get(sessionId) ?? {
      session: null,
      progress: null,
      alerts: [],
      results: [],
      latest_result: null,
    }
  );
}

export async function cancelSession(sessionId: string): Promise<SessionSummary | null> {
  const current = sessionStore.get(sessionId);
  if (!current?.session || !current.progress) {
    return null;
  }

  const nextSession: SessionSummary = {
    ...current.session,
    status: "cancelling",
  };

  sessionStore.set(sessionId, {
    ...current,
    session: nextSession,
    progress: {
      ...current.progress,
      status: "cancelling",
      last_updated_utc: new Date().toISOString(),
    },
  });

  const historyIndex = sessionHistory.findIndex(
    (entry) => entry.session_id === sessionId,
  );
  if (historyIndex >= 0) {
    sessionHistory[historyIndex] = nextSession;
  }

  window.setTimeout(() => {
    const latest = sessionStore.get(sessionId);
    if (!latest?.session || !latest.progress) {
      return;
    }

    const cancelledSession: SessionSummary = {
      ...latest.session,
      status: "cancelled",
    };

    sessionStore.set(sessionId, {
      ...latest,
      session: cancelledSession,
      progress: {
        ...latest.progress,
        status: "cancelled",
        last_updated_utc: new Date().toISOString(),
      },
    });

    const cancelledHistoryIndex = sessionHistory.findIndex(
      (entry) => entry.session_id === sessionId,
    );
    if (cancelledHistoryIndex >= 0) {
      sessionHistory[cancelledHistoryIndex] = cancelledSession;
    }
  }, 150);

  return nextSession;
}

export async function resolvePlaybackSource(
  input: PlaybackSourceRequest,
): Promise<string | null> {
  const { source, currentItem } = input;

  if (source.kind === "video_segments") {
    return null;
  }

  return buildFallbackMediaSource(source.path, currentItem);
}

function simulateProgress(sessionId: string, input: RunSessionInput, items: string[]): void {
  items.forEach((item, index) => {
    window.setTimeout(() => {
      const current = sessionStore.get(sessionId);
      if (!current || !current.session || !current.progress) {
        return;
      }
      if (current.session.status !== "running" || current.progress.status !== "running") {
        return;
      }

      const detectorId =
        input.selectedDetectors.length > 0
          ? input.selectedDetectors[index % input.selectedDetectors.length]
          : null;

      const resultPayload =
        detectorId === "video_blur"
          ? {
              source_name: item,
              timestamp_utc: new Date().toISOString(),
              processing_sec: 0.11,
              blur_score: 9.3,
              blur_detected: true,
              threshold_used: 12,
            }
          : detectorId === "video_metrics"
            ? {
                source_name: item,
                timestamp_utc: new Date().toISOString(),
                processing_sec: 0.08,
                bitrate_nominal_kbps: 18.7,
                duration_sec: 1.0,
              }
            : null;

      const result: ResultEvent | null = detectorId && resultPayload
        ? {
            session_id: sessionId,
            detector_id: detectorId,
            payload: resultPayload,
          }
        : null;

      const alerts: AlertEvent[] =
        detectorId === "video_blur"
          ? [
              {
                session_id: sessionId,
                timestamp_utc: new Date().toISOString(),
                detector_id: detectorId,
                title: "Blur detected",
                message: `Blur score 9.3 fell below the configured threshold in ${item}.`,
                severity: "warning",
                source_name: item,
                window_index: index,
                window_start_sec: index,
              },
            ]
          : detectorId === "video_metrics" && index === 1
              ? [
                  {
                    session_id: sessionId,
                    timestamp_utc: new Date().toISOString(),
                    detector_id: detectorId,
                    title: "Low bitrate observed",
                    message: `The nominal bitrate for ${item} dropped below the expected level.`,
                    severity: "info",
                    source_name: item,
                    window_index: index,
                  },
                ]
              : [];

      const nextResults = result ? [...current.results, result] : current.results;
      const nextAlerts = [...current.alerts, ...alerts];
      const completed = index === items.length - 1;
      const nextSession = {
        ...current.session,
        status: completed ? "completed" : "running",
      } satisfies SessionSummary;

      sessionStore.set(sessionId, {
        session: nextSession,
        progress: {
          ...current.progress,
          status: completed ? "completed" : "running",
          processed_count: index + 1,
          total_count: items.length,
          current_item: item,
          latest_result_detector: detectorId,
          alert_count: nextAlerts.length,
          last_updated_utc: new Date().toISOString(),
          latest_result_detectors: detectorId ? [detectorId] : [],
        },
        alerts: nextAlerts,
        results: nextResults,
        latest_result: result ?? current.latest_result,
      });

      const historyIndex = sessionHistory.findIndex(
        (entry) => entry.session_id === sessionId,
      );
      if (historyIndex >= 0) {
        sessionHistory[historyIndex] = nextSession;
      }
    }, 800 * (index + 1));
  });
}

function buildFallbackMediaSource(
  inputPath: string,
  currentItem: string | null,
): string | null {
  const base = inputPath.trim();
  if (!base) {
    return null;
  }

  const directSchemes = ["http://", "https://", "blob:", "data:", "file://"];
  if (directSchemes.some((scheme) => base.startsWith(scheme))) {
    if (currentItem && base.endsWith("/")) {
      return `${base}${encodeURIComponent(currentItem)}`;
    }
    return base;
  }

  const looksLikeFilePath = /\/[^/]+\.[a-zA-Z0-9]{2,8}$/.test(base);
  if (looksLikeFilePath) {
    return encodeURI(`file://${base}`);
  }

  if (currentItem) {
    return encodeURI(`file://${base.replace(/\/$/, "")}/${currentItem}`);
  }

  return encodeURI(`file://${base}`);
}
