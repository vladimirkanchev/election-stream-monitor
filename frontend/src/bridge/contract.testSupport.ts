/**
 * Shared builders for the bridge contract suites.
 *
 * These helpers keep the success and error tests focused on envelope and
 * normalization behavior instead of repeating source and summary literals.
 */

import { vi } from "vitest";

import type { DetectorOption, LocalBridge, MonitorSource, SessionSummary } from "../types";
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
 * Creates a detector catalog entry shaped like the normalized bridge contract.
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
 * Creates a valid session summary payload for bridge start/cancel contract
 * tests, with optional overrides for the lifecycle fields under test.
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
 * Wraps a partially stubbed raw bridge in the public normalization facade so
 * individual tests can override only the transport call they care about.
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
