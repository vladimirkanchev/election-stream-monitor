import type {
  AlertEvent,
  DetectorOption,
  InputMode,
  LocalBridge,
  PlaybackSourceRequest,
  ResultEvent,
  SessionSnapshot,
  SessionSummary,
} from "../types";

export type BridgeErrorCode =
  | "DETECTOR_CATALOG_FAILED"
  | "SESSION_START_FAILED"
  | "SESSION_READ_FAILED"
  | "SESSION_CANCEL_FAILED"
  | "PLAYBACK_SOURCE_RESOLUTION_FAILED"
  | "INVALID_BRIDGE_RESPONSE";

export interface BridgeErrorPayload {
  code: BridgeErrorCode;
  message: string;
  details?: string | null;
  backend_error_code?: string | null;
  status_reason?: string | null;
  status_detail?: string | null;
}

export type BridgeSuccess<T> = {
  ok: true;
  data: T;
};

export type BridgeFailure = {
  ok: false;
  error: BridgeErrorPayload;
};

export type BridgeResponse<T> = BridgeSuccess<T> | BridgeFailure;

export interface BridgeTransport {
  listDetectors: (mode?: InputMode) => Promise<BridgeResponse<unknown>>;
  startSession: (input: {
    source: {
      kind: InputMode;
      path: string;
      access: "local_path" | "api_stream";
    };
    selectedDetectors: string[];
  }) => Promise<BridgeResponse<unknown>>;
  readSession: (sessionId: string) => Promise<BridgeResponse<unknown>>;
  cancelSession: (sessionId: string) => Promise<BridgeResponse<unknown>>;
  resolvePlaybackSource: (
    input: PlaybackSourceRequest,
  ) => Promise<BridgeResponse<unknown>>;
}

export class BridgeTransportError extends Error {
  readonly code: BridgeErrorCode;
  readonly details: string | null;
  readonly backendErrorCode: string | null;
  readonly statusReason: string | null;
  readonly statusDetail: string | null;

  constructor(error: BridgeErrorPayload) {
    super(error.message);
    this.name = "BridgeTransportError";
    this.code = error.code;
    this.details = error.details ?? null;
    this.backendErrorCode = error.backend_error_code ?? null;
    this.statusReason = error.status_reason ?? null;
    this.statusDetail = error.status_detail ?? null;
  }
}

export function isBridgeTransportError(error: unknown): error is BridgeTransportError {
  return error instanceof BridgeTransportError;
}

const VALID_INPUT_MODES: InputMode[] = [
  "video_segments",
  "video_files",
  "api_stream",
];
const VALID_SESSION_STATUSES = [
  "pending",
  "running",
  "cancelling",
  "cancelled",
  "completed",
  "failed",
] as const;
const VALID_DETECTOR_STATUSES = ["core", "optional", "experimental"] as const;
const VALID_DETECTOR_ORIGINS = ["built_in", "user"] as const;
const VALID_DETECTOR_CATEGORIES = ["quality", "visibility", "stability"] as const;

const EMPTY_SNAPSHOT: SessionSnapshot = {
  session: null,
  progress: null,
  alerts: [],
  results: [],
  latest_result: null,
};

export function createNormalizedBridge(
  rawBridge: LocalBridge | BridgeTransport,
): LocalBridge {
  return {
    async listDetectors(mode?: InputMode): Promise<DetectorOption[]> {
      const detectors = unwrapBridgeValue(await rawBridge.listDetectors(mode));
      return normalizeDetectorOptions(detectors);
    },
    async startSession(input): Promise<SessionSummary> {
      const session = normalizeSessionSummary(
        unwrapBridgeValue(await rawBridge.startSession(input)),
      );
      if (!session) {
        throw new BridgeTransportError({
          code: "INVALID_BRIDGE_RESPONSE",
          message: "invalid bridge startSession response",
        });
      }
      return session;
    },
    async readSession(sessionId: string): Promise<SessionSnapshot> {
      return normalizeSessionSnapshot(
        unwrapBridgeValue(await rawBridge.readSession(sessionId)),
      );
    },
    async cancelSession(sessionId: string): Promise<SessionSummary | null> {
      const session = unwrapBridgeValue(await rawBridge.cancelSession(sessionId));
      if (session === null) {
        return null;
      }

      const normalized = normalizeSessionSummary(session);
      if (!normalized) {
        throw new BridgeTransportError({
          code: "INVALID_BRIDGE_RESPONSE",
          message: "invalid bridge cancelSession response",
        });
      }
      return normalized;
    },
    async resolvePlaybackSource(
      input: PlaybackSourceRequest,
    ): Promise<string | null> {
      return normalizePlaybackSource(
        unwrapBridgeValue(await rawBridge.resolvePlaybackSource(input)),
      );
    },
  };
}

export function ok<T>(data: T): BridgeSuccess<T> {
  return { ok: true, data };
}

export function fail(
  code: BridgeErrorCode,
  message: string,
  details?: string | null,
  metadata?: {
    backend_error_code?: string | null;
    status_reason?: string | null;
    status_detail?: string | null;
  },
): BridgeFailure {
  return {
    ok: false,
    error: {
      code,
      message,
      details: details ?? null,
      backend_error_code: metadata?.backend_error_code ?? null,
      status_reason: metadata?.status_reason ?? null,
      status_detail: metadata?.status_detail ?? null,
    },
  };
}

export function unwrapBridgeValue<T>(value: T | BridgeResponse<T>): T {
  if (isBridgeResponse(value)) {
    if (!value.ok) {
      throw new BridgeTransportError(normalizeBridgeErrorPayload(value.error));
    }
    return value.data;
  }

  return value;
}

function normalizeBridgeErrorPayload(value: unknown): BridgeErrorPayload {
  if (!isRecord(value)) {
    return {
      code: "INVALID_BRIDGE_RESPONSE",
      message: "invalid bridge error response",
      details: null,
      backend_error_code: null,
      status_reason: null,
      status_detail: null,
    };
  }

  return {
    code: isBridgeErrorCode(value.code) ? value.code : "INVALID_BRIDGE_RESPONSE",
    message:
      typeof value.message === "string" && value.message.trim().length > 0
        ? value.message
        : "invalid bridge error response",
    details: isNullableString(value.details) ? value.details : null,
    backend_error_code: isNullableString(value.backend_error_code)
      ? value.backend_error_code
      : null,
    status_reason: isNullableString(value.status_reason) ? value.status_reason : null,
    status_detail: isNullableString(value.status_detail) ? value.status_detail : null,
  };
}

export function normalizeDetectorOptions(value: unknown): DetectorOption[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(isDetectorOption);
}

export function normalizeSessionSnapshot(value: unknown): SessionSnapshot {
  if (!isRecord(value)) {
    return EMPTY_SNAPSHOT;
  }

  // Terminal snapshots remain normal read successes; route-level failures are
  // represented separately as typed bridge errors before normalization.
  return {
    session: normalizeSessionSummary(value.session),
    progress: normalizeSessionProgress(value.progress),
    alerts: Array.isArray(value.alerts) ? value.alerts.filter(isAlertEvent) : [],
    results: Array.isArray(value.results) ? value.results.filter(isResultEvent) : [],
    latest_result: isResultEvent(value.latest_result) ? value.latest_result : null,
  };
}

export function normalizeSessionSummary(value: unknown): SessionSummary | null {
  if (!isRecord(value)) {
    return null;
  }

  if (
    !isNonEmptyString(value.session_id) ||
    !isInputMode(value.mode) ||
    typeof value.input_path !== "string" ||
    !Array.isArray(value.selected_detectors) ||
    !value.selected_detectors.every((item) => typeof item === "string") ||
    !isSessionStatus(value.status)
  ) {
    return null;
  }

  return {
    session_id: value.session_id,
    mode: value.mode,
    input_path: value.input_path,
    selected_detectors: value.selected_detectors,
    status: value.status,
  };
}

export function normalizePlaybackSource(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeSessionProgress(
  value: unknown,
): SessionSnapshot["progress"] {
  if (!isRecord(value)) {
    return null;
  }

  if (
    !isNonEmptyString(value.session_id) ||
    !isSessionStatus(value.status) ||
    typeof value.processed_count !== "number" ||
    typeof value.total_count !== "number" ||
    typeof value.alert_count !== "number" ||
    typeof value.last_updated_utc !== "string" ||
    !isNullableString(value.current_item) ||
    !isNullableString(value.latest_result_detector) ||
    !Array.isArray(value.latest_result_detectors) ||
    !value.latest_result_detectors.every((item) => typeof item === "string")
  ) {
    return null;
  }

  return {
    session_id: value.session_id,
    status: value.status,
    processed_count: value.processed_count,
    total_count: value.total_count,
    current_item: value.current_item,
    latest_result_detector: value.latest_result_detector,
    alert_count: value.alert_count,
    last_updated_utc: value.last_updated_utc,
    latest_result_detectors: value.latest_result_detectors,
    status_reason: isNullableString(value.status_reason) ? value.status_reason : null,
    status_detail: isNullableString(value.status_detail) ? value.status_detail : null,
  };
}

function isDetectorOption(value: unknown): value is DetectorOption {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.id) &&
    typeof value.display_name === "string" &&
    typeof value.description === "string" &&
    isDetectorCategory(value.category) &&
    isDetectorOrigin(value.origin) &&
    isDetectorStatus(value.status) &&
    (typeof value.default_rule_id === "string" || value.default_rule_id === null) &&
    typeof value.default_selected === "boolean" &&
    typeof value.produces_alerts === "boolean" &&
    Array.isArray(value.supported_modes) &&
    value.supported_modes.every(isInputMode) &&
    Array.isArray(value.supported_suffixes) &&
    value.supported_suffixes.every((item) => typeof item === "string")
  );
}

function isBridgeResponse<T>(
  value: T | BridgeResponse<T>,
): value is BridgeResponse<T> {
  return isRecord(value) && typeof value.ok === "boolean";
}

function isAlertEvent(value: unknown): value is AlertEvent {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.session_id) &&
    typeof value.timestamp_utc === "string" &&
    isNonEmptyString(value.detector_id) &&
    typeof value.title === "string" &&
    typeof value.message === "string" &&
    (value.severity === "info" || value.severity === "warning") &&
    typeof value.source_name === "string" &&
    (typeof value.window_index === "number" ||
      value.window_index === null ||
      value.window_index === undefined) &&
    (typeof value.window_start_sec === "number" ||
      value.window_start_sec === null ||
      value.window_start_sec === undefined)
  );
}

function isResultEvent(value: unknown): value is ResultEvent {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.session_id) &&
    isNonEmptyString(value.detector_id) &&
    isRecord(value.payload)
  );
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null;
}

function isInputMode(value: unknown): value is InputMode {
  return typeof value === "string" && VALID_INPUT_MODES.includes(value as InputMode);
}

function isSessionStatus(
  value: unknown,
): value is SessionSummary["status"] {
  return (
    typeof value === "string" &&
    VALID_SESSION_STATUSES.includes(value as SessionSummary["status"])
  );
}

function isDetectorStatus(
  value: unknown,
): value is DetectorOption["status"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_STATUSES.includes(value as DetectorOption["status"])
  );
}

function isBridgeErrorCode(value: unknown): value is BridgeErrorCode {
  return (
    value === "DETECTOR_CATALOG_FAILED" ||
    value === "SESSION_START_FAILED" ||
    value === "SESSION_READ_FAILED" ||
    value === "SESSION_CANCEL_FAILED" ||
    value === "PLAYBACK_SOURCE_RESOLUTION_FAILED" ||
    value === "INVALID_BRIDGE_RESPONSE"
  );
}

function isDetectorOrigin(
  value: unknown,
): value is DetectorOption["origin"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_ORIGINS.includes(value as DetectorOption["origin"])
  );
}

function isDetectorCategory(
  value: unknown,
): value is DetectorOption["category"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_CATEGORIES.includes(value as DetectorOption["category"])
  );
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}
