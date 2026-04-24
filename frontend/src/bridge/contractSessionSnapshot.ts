/**
 * Session snapshot normalization for the frontend bridge contract.
 *
 * The normalizers here fail closed on malformed nested payloads while keeping
 * the outer session snapshot shape stable for hooks and UI code.
 */

import type {
  AlertEvent,
  ResultEvent,
  SessionSnapshot,
  SessionSummary,
} from "../types";
import {
  isInputMode,
  isNonEmptyString,
  isRecord,
  isSessionStatus,
  isStringArray,
  normalizeNullableString,
} from "./contractShared";

const EMPTY_SNAPSHOT: SessionSnapshot = {
  session: null,
  progress: null,
  alerts: [],
  results: [],
  latest_result: null,
};

export function normalizeSessionSnapshot(value: unknown): SessionSnapshot {
  if (!isRecord(value)) {
    return EMPTY_SNAPSHOT;
  }

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
    !isOptionalNullableString(value.current_item) ||
    !isOptionalNullableString(value.latest_result_detector) ||
    !isStringArray(value.latest_result_detectors)
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
    status_reason: normalizeNullableString(value.status_reason),
    status_detail: normalizeNullableString(value.status_detail),
  };
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

function isOptionalNullableString(
  value: unknown,
): value is string | null | undefined {
  return typeof value === "string" || value === null || value === undefined;
}
