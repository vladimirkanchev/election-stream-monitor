import type { BridgeTransport } from "./contract";
import { fail, ok } from "./contract";
import {
  cancelSession as demoCancelSession,
  listDetectors as demoListDetectors,
  readSession as demoReadSession,
  resolvePlaybackSource as demoResolvePlaybackSource,
  startSession as demoStartSession,
} from "./demoBridge";

interface WindowWithBridgeTransport extends Window {
  electionBridge?: BridgeTransport;
}

export const demoBridgeTransport: BridgeTransport = {
  async listDetectors(_mode) {
    try {
      return ok(await demoListDetectors());
    } catch (error) {
      return fail("DETECTOR_CATALOG_FAILED", "Detector catalog request failed", getErrorDetails(error));
    }
  },
  async startSession(input) {
    try {
      return ok(await demoStartSession(input));
    } catch (error) {
      return fail("SESSION_START_FAILED", "Session start request failed", getErrorDetails(error));
    }
  },
  async readSession(sessionId) {
    try {
      return ok(await demoReadSession(sessionId));
    } catch (error) {
      return fail("SESSION_READ_FAILED", "Session read request failed", getErrorDetails(error));
    }
  },
  async cancelSession(sessionId) {
    try {
      return ok(await demoCancelSession(sessionId));
    } catch (error) {
      return fail("SESSION_CANCEL_FAILED", "Session cancel request failed", getErrorDetails(error));
    }
  },
  async resolvePlaybackSource(input) {
    try {
      return ok(await demoResolvePlaybackSource(input));
    } catch (error) {
      return fail(
        "PLAYBACK_SOURCE_RESOLUTION_FAILED",
        "Playback source resolution failed",
        getErrorDetails(error),
      );
    }
  },
};

export function resolveBridgeTransport(windowObject: Window): BridgeTransport {
  const bridgeWindow = windowObject as WindowWithBridgeTransport;
  if (bridgeWindow.electionBridge) {
    return bridgeWindow.electionBridge;
  }
  return demoBridgeTransport;
}

function getErrorDetails(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
