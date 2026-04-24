/**
 * Error-path tests for the public bridge contract facade plus the typed error
 * and transport-envelope behavior owned by `contractErrors`.
 */

import { describe, expect, it, vi } from "vitest";

import type { LocalBridge } from "../types";
import { createNormalizedBridge, fail } from "./contract";

describe("bridge contract error normalization", () => {
  it("raises when startSession returns a malformed summary", async () => {
    const rawBridge: LocalBridge = {
      listDetectors: vi.fn().mockResolvedValue([]),
      startSession: vi.fn().mockResolvedValue({
        mode: "video_segments",
        status: "running",
      }),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    };

    const bridge = createNormalizedBridge(rawBridge);

    await expect(
      bridge.startSession({
        source: {
          kind: "video_segments",
          path: "/tmp/source",
          access: "local_path",
        },
        selectedDetectors: [],
      }),
    ).rejects.toThrow("invalid bridge startSession response");
  });

  it("raises a typed bridge error when the transport returns an explicit start failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn().mockResolvedValue(
        fail("SESSION_START_FAILED", "Session start request failed", "cli crashed"),
      ),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(
      bridge.startSession({
        source: {
          kind: "video_segments",
          path: "/tmp/source",
          access: "local_path",
        },
        selectedDetectors: [],
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "cli crashed",
    });
  });

  it("falls back to a safe typed bridge error when startSession failure metadata is malformed", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn().mockResolvedValue({
        ok: false,
        error: {
          code: "SESSION_START_FAILED",
          details: { noisy: true },
          status_reason: 42,
          backend_error_code: "start_failed",
        },
      }),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(
      bridge.startSession({
        source: {
          kind: "video_segments",
          path: "/tmp/source",
          access: "local_path",
        },
        selectedDetectors: [],
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_START_FAILED",
      message: "invalid bridge error response",
      details: null,
      backendErrorCode: "start_failed",
      statusReason: null,
      statusDetail: null,
    });
  });

  it("raises a typed bridge error when cancelSession returns an explicit backend failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_CANCEL_FAILED",
          "Session cancel request failed",
          "No persisted session snapshot found for session_id=session-123",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-123",
          },
        ),
      ),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_CANCEL_FAILED",
      message: "Session cancel request failed",
      details: "No persisted session snapshot found for session_id=session-123",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-123",
    });
  });

  it("preserves invalid cancel-state failures as typed bridge transport errors", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_CANCEL_FAILED",
          "Session cancel request failed",
          "Session session-123 is already completed.",
          {
            backend_error_code: "cancel_failed",
            status_reason: "cancel_failed",
            status_detail: "Session session-123 is already completed.",
          },
        ),
      ),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_CANCEL_FAILED",
      backendErrorCode: "cancel_failed",
      statusReason: "cancel_failed",
      statusDetail: "Session session-123 is already completed.",
    });
  });

  it("raises a typed bridge error when readSession returns a missing-session failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-123",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-123",
          },
        ),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_READ_FAILED",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-123",
    });
  });

  it("preserves typed lifecycle metadata for explicit readSession bridge failures", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn().mockResolvedValue(
        fail(
          "SESSION_READ_FAILED",
          "Session read request failed",
          "No persisted session snapshot found for session_id=session-456",
          {
            backend_error_code: "session_not_found",
            status_reason: "session_not_found",
            status_detail: "No persisted session snapshot found for session_id=session-456",
          },
        ),
      ),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.readSession("session-456")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "SESSION_READ_FAILED",
      message: "Session read request failed",
      details: "No persisted session snapshot found for session_id=session-456",
      backendErrorCode: "session_not_found",
      statusReason: "session_not_found",
      statusDetail: "No persisted session snapshot found for session_id=session-456",
    });
  });

  it("raises when cancelSession returns a malformed non-null summary", async () => {
    const rawBridge: LocalBridge = {
      listDetectors: vi.fn().mockResolvedValue([]),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        session_id: "session-1",
      }),
      resolvePlaybackSource: vi.fn(),
    };

    const bridge = createNormalizedBridge(rawBridge);

    await expect(bridge.cancelSession("session-1")).rejects.toThrow(
      "invalid bridge cancelSession response",
    );
  });

  it("raises a typed bridge error when playback resolution returns an explicit failure", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn().mockResolvedValue(
        fail(
          "PLAYBACK_SOURCE_RESOLUTION_FAILED",
          "Playback source resolution failed",
          "remote source unreachable",
        ),
      ),
    });

    await expect(
      bridge.resolvePlaybackSource({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        },
        currentItem: null,
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "PLAYBACK_SOURCE_RESOLUTION_FAILED",
      message: "Playback source resolution failed",
      details: "remote source unreachable",
    });
  });

  it("keeps optional backend error metadata on typed bridge failures", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn().mockResolvedValue(
        fail(
          "PLAYBACK_SOURCE_RESOLUTION_FAILED",
          "Playback source resolution failed",
          "backend reported a structured error",
          {
            backend_error_code: "playback_unavailable",
            status_reason: "playback_unavailable",
            status_detail: "Renderer-safe playback source could not be prepared",
          },
        ),
      ),
    });

    await expect(
      bridge.resolvePlaybackSource({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        },
        currentItem: null,
      }),
    ).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "PLAYBACK_SOURCE_RESOLUTION_FAILED",
      backendErrorCode: "playback_unavailable",
      statusReason: "playback_unavailable",
      statusDetail: "Renderer-safe playback source could not be prepared",
    });
  });

  it("falls back to a safe typed bridge error when a failure envelope is malformed", async () => {
    const bridge = createNormalizedBridge({
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn().mockResolvedValue({
        ok: false,
        error: { backend_error_code: "cancel_failed" },
      }),
      resolvePlaybackSource: vi.fn(),
    });

    await expect(bridge.cancelSession("session-123")).rejects.toMatchObject({
      name: "BridgeTransportError",
      code: "INVALID_BRIDGE_RESPONSE",
      message: "invalid bridge error response",
      details: null,
      backendErrorCode: "cancel_failed",
      statusReason: null,
      statusDetail: null,
    });
  });
});
