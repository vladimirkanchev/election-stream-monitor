/**
 * Focused tests for extracted IPC bridge registration.
 */

import { describe, expect, it, vi } from "vitest";

import { registerFastApiBridgeHandlers } from "./bridgeHandlerRegistry.mjs";

describe("bridgeHandlerRegistry", () => {
  it("registers the expected IPC channels", () => {
    const ipcMain = { handle: vi.fn() };

    registerFastApiBridgeHandlers({
      ipcMain,
      handleBridgeOperation: vi.fn(),
      runWithRuntimePolicy: vi.fn(),
      apiListDetectors: vi.fn(),
      apiStartSession: vi.fn(),
      apiReadSession: vi.fn(),
      apiCancelSession: vi.fn(),
      apiResolvePlaybackSource: vi.fn(),
      resolveRendererPlaybackSource: vi.fn(),
    });

    expect(ipcMain.handle.mock.calls.map(([channel]) => channel)).toEqual([
      "bridge:list-detectors",
      "bridge:start-session",
      "bridge:read-session",
      "bridge:cancel-session",
      "bridge:resolve-playback-source",
    ]);
  });

  it("wraps bridge operations with the shared runtime policy and response envelope", async () => {
    const handlers = new Map();
    const ipcMain = {
      handle: vi.fn((channel, handler) => {
        handlers.set(channel, handler);
      }),
    };
    const handleBridgeOperation = vi.fn(async (_code, _message, operation) => operation());
    const runWithRuntimePolicy = vi.fn((operation) => operation());
    const apiResolvePlaybackSource = vi.fn().mockResolvedValue({
      source: "/tmp/session/segment_0001.ts",
    });
    const resolveRendererPlaybackSource = vi.fn().mockReturnValue(
      "local-media://media/tmp/session/segment_0001.ts",
    );

    registerFastApiBridgeHandlers({
      ipcMain,
      handleBridgeOperation,
      runWithRuntimePolicy,
      apiListDetectors: vi.fn(),
      apiStartSession: vi.fn(),
      apiReadSession: vi.fn(),
      apiCancelSession: vi.fn(),
      apiResolvePlaybackSource,
      resolveRendererPlaybackSource,
    });

    const result = await handlers.get("bridge:resolve-playback-source")(
      {},
      { source: { kind: "video_segments", path: "/tmp/session/index.m3u8" } },
    );

    expect(runWithRuntimePolicy).toHaveBeenCalledTimes(1);
    expect(apiResolvePlaybackSource).toHaveBeenCalledTimes(1);
    expect(resolveRendererPlaybackSource).toHaveBeenCalledWith("/tmp/session/segment_0001.ts");
    expect(result).toBe("local-media://media/tmp/session/segment_0001.ts");
  });
});
