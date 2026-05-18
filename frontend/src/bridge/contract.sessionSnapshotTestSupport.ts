import { vi } from "vitest";

import { createNormalizedBridge, ok } from "./contract";

export type BridgeSessionSnapshot = {
  session?: object | null;
  progress?: object | null;
  alerts?: unknown[];
  results?: unknown[];
  latest_result?: object | null;
};

/**
 * Fills in the default empty collection fields expected by the public bridge
 * session-snapshot contract so individual tests can stay focused on the nested
 * payload they want to vary.
 */
export function buildBridgeSnapshot(
  snapshot: BridgeSessionSnapshot,
): BridgeSessionSnapshot {
  return {
    alerts: [],
    results: [],
    latest_result: null,
    ...snapshot,
  };
}

/**
 * Reads one normalized session snapshot through the real public bridge facade.
 * Tests use this when they care about the full transport-normalization seam,
 * not just the pure normalizer helper.
 */
export function readNormalizedSession(
  sessionId: string,
  snapshot: BridgeSessionSnapshot,
) {
  const bridge = createReadSessionBridge(snapshot);
  return bridge.readSession(sessionId);
}

/**
 * Creates a minimal normalized bridge whose `readSession` path resolves to the
 * provided snapshot envelope.
 */
export function createReadSessionBridge(snapshot: BridgeSessionSnapshot) {
  return createNormalizedBridge({
    listDetectors: vi.fn(),
    startSession: vi.fn(),
    readSession: vi.fn().mockResolvedValue(ok(buildBridgeSnapshot(snapshot))),
    cancelSession: vi.fn(),
    resolvePlaybackSource: vi.fn(),
  });
}
