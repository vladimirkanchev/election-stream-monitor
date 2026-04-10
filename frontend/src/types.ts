export type InputMode = "video_segments" | "video_files" | "api_stream";
export type SessionStatus =
  | "pending"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed";
export type MonitoringSessionState = "idle" | "starting" | SessionStatus;
export type PlaybackStatus = "idle" | "loading" | "playing" | "stopped" | "error";
export type MonitorSourceAccess = "local_path" | "api_stream";
export interface MonitorSource {
  kind: InputMode;
  path: string;
  access: MonitorSourceAccess;
}

export type SegmentStartTimes = Record<string, number>;

export type DetectorStatus = "core" | "optional" | "experimental";
export type DetectorOrigin = "built_in" | "user";

export interface DetectorOption {
  id: string;
  display_name: string;
  description: string;
  category: "quality" | "visibility" | "stability";
  origin: DetectorOrigin;
  status: DetectorStatus;
  default_rule_id: string | null;
  default_selected: boolean;
  produces_alerts: boolean;
  supported_modes: InputMode[];
  supported_suffixes: string[];
}

export interface AlertRuleOption {
  id: string;
  detector_id: string;
  display_name: string;
  description: string;
  origin: DetectorOrigin;
  status: DetectorStatus;
}

export interface SessionSummary {
  session_id: string;
  mode: InputMode;
  input_path: string;
  selected_detectors: string[];
  status: SessionStatus;
}

export interface RunSessionInput {
  source: MonitorSource;
  selectedDetectors: string[];
}

export interface SessionProgress {
  session_id: string;
  status: SessionStatus;
  processed_count: number;
  total_count: number;
  current_item: string | null;
  latest_result_detector: string | null;
  alert_count: number;
  last_updated_utc: string;
  latest_result_detectors: string[];
  status_reason?: string | null;
  status_detail?: string | null;
}

export interface AlertEvent {
  session_id: string;
  timestamp_utc: string;
  detector_id: string;
  title: string;
  message: string;
  severity: "info" | "warning";
  source_name: string;
  window_index?: number | null;
  window_start_sec?: number | null;
}

export interface ResultEvent {
  session_id: string;
  detector_id: string;
  payload: Record<string, unknown>;
}

export interface SessionSnapshot {
  session: SessionSummary | null;
  progress: SessionProgress | null;
  alerts: AlertEvent[];
  results: ResultEvent[];
  latest_result: ResultEvent | null;
}

export interface PlaybackSourceRequest {
  source: MonitorSource;
  currentItem: string | null;
}

export interface LocalBridge {
  listDetectors: (mode?: InputMode) => Promise<DetectorOption[]>;
  startSession: (input: RunSessionInput) => Promise<SessionSummary>;
  readSession: (sessionId: string) => Promise<SessionSnapshot>;
  cancelSession: (sessionId: string) => Promise<SessionSummary | null>;
  resolvePlaybackSource: (input: PlaybackSourceRequest) => Promise<string | null>;
}
