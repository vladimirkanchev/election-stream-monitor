/**
 * Shared builders for the bridge contract suites.
 *
 * These helpers keep bridge tests focused on envelope and normalization
 * behavior instead of repeated literals.
 */

import { vi } from "vitest";

import type {
  DetectorOption,
  LocalBridge,
  MonitorSource,
  SessionProgress,
  SessionSummary,
} from "../types";
import { createNormalizedBridge } from "./contract";

export const API_STREAM_MONITOR_SOURCE: MonitorSource = {
  kind: "api_stream",
  path: "https://example.com/live/index.m3u8",
  access: "api_stream",
};

export const VIDEO_SEGMENTS_MONITOR_SOURCE: MonitorSource = {
  kind: "video_segments",
  path: "/tmp/source",
  access: "local_path",
};

/**
 * Build a detector option that already matches the normalized bridge contract.
 */
export function buildDetectorOption(
  overrides: Partial<DetectorOption> = {},
): DetectorOption {
  return {
    id: "video_blur",
    display_name: "Blur Check",
    description: "Blur detector",
    category: "quality",
    origin: "built_in",
    status: "optional",
    default_rule_id: "video_blur.default_rule",
    default_selected: false,
    produces_alerts: true,
    supported_modes: ["video_segments", "video_files", "api_stream"],
    supported_suffixes: [".ts", ".mp4"],
    ...overrides,
  };
}

/**
 * Build a valid session summary for bridge contract tests.
 */
export function buildSessionSummary(
  overrides: Partial<SessionSummary> = {},
): SessionSummary {
  return {
    session_id: "session-123",
    mode: "video_segments",
    input_path: "/data/streams/segments",
    selected_detectors: ["video_blur"],
    status: "running",
    ...overrides,
  };
}

/**
 * Build a valid polling-progress payload for snapshot tests.
 */
export function buildSessionProgress(
  overrides: Partial<SessionProgress> = {},
): SessionProgress {
  return {
    session_id: "session-123",
    status: "running",
    processed_count: 1,
    total_count: 4,
    current_item: "segment_0000.ts",
    latest_result_detector: "video_metrics",
    latest_result_detectors: ["video_metrics"],
    alert_count: 0,
    last_updated_utc: "2026-07-02 13:15:00",
    status_reason: "running",
    status_detail: null,
    ...overrides,
  };
}

/**
 * Wrap a partially stubbed raw bridge in the public normalization facade.
 */
export function createContractBridge(overrides: Partial<LocalBridge> = {}) {
  return createNormalizedBridge({
    listDetectors: vi.fn(),
    startSession: vi.fn(),
    readSession: vi.fn(),
    cancelSession: vi.fn(),
    resolvePlaybackSource: vi.fn(),
    ...overrides,
  });
}
