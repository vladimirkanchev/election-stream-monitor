/**
 * Stable public facade for frontend bridge normalization.
 *
 * This module keeps the public bridge-facing API small while delegating
 * detailed normalization concerns to focused helpers:
 *
 * - `contractErrors` for transport envelopes, error types, and typed failures
 * - `contractDetectors` for detector catalog normalization
 * - `contractSessionSnapshot` for session snapshot normalization
 * - `contractShared` for small reusable validators used by the owning modules
 */

import type {
  DetectorOption,
  InputMode,
  LocalBridge,
  PlaybackSourceRequest,
  SessionSnapshot,
  SessionSummary,
} from "../types";
import {
  type BridgeErrorCode,
  type BridgeErrorPayload,
  BridgeTransportError,
  fail,
  isBridgeTransportError,
  ok,
  unwrapBridgeValue,
  type BridgeFailure,
  type BridgeResponse,
  type BridgeSuccess,
} from "./contractErrors";
import { normalizeDetectorOptions } from "./contractDetectors";
import {
  normalizeSessionSnapshot,
  normalizeSessionSummary,
} from "./contractSessionSnapshot";

export {
  type BridgeErrorCode,
  type BridgeErrorPayload,
  BridgeTransportError,
  fail,
  isBridgeTransportError,
  ok,
  normalizeDetectorOptions,
  normalizeSessionSnapshot,
};

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

export function createNormalizedBridge(
  rawBridge: LocalBridge | BridgeTransport,
): LocalBridge {
  return {
    async listDetectors(mode?: InputMode): Promise<DetectorOption[]> {
      const detectors = unwrapBridgeValue(await rawBridge.listDetectors(mode));
      return normalizeDetectorOptions(detectors);
    },
    async startSession(input): Promise<SessionSummary> {
      return requireSessionSummary(
        unwrapBridgeValue(await rawBridge.startSession(input)),
        "invalid bridge startSession response",
      );
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

      return requireSessionSummary(
        session,
        "invalid bridge cancelSession response",
      );
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

export function normalizePlaybackSource(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function requireSessionSummary(
  value: unknown,
  invalidMessage: string,
): SessionSummary {
  const normalized = normalizeSessionSummary(value);
  if (!normalized) {
    throw new BridgeTransportError({
      code: "INVALID_BRIDGE_RESPONSE",
      message: invalidMessage,
    });
  }
  return normalized;
}
