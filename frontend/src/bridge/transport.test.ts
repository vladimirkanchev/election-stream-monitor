import { describe, expect, it, vi } from "vitest";

import type { BridgeTransport } from "./contract";
import { resolveBridgeTransport } from "./transport";

describe("bridge transport resolution", () => {
  it("uses the single explicit preload bridge surface when it exists on window", async () => {
    const transport: BridgeTransport = {
      listDetectors: vi.fn(),
      startSession: vi.fn(),
      readSession: vi.fn(),
      cancelSession: vi.fn(),
      resolvePlaybackSource: vi.fn(),
    };

    const resolved = resolveBridgeTransport({
      electionBridge: transport,
    } as unknown as Window);

    expect(resolved).toBe(transport);
  });

  it("falls back to the demo bridge transport when preload is unavailable", async () => {
    const resolved = resolveBridgeTransport({} as Window);

    await expect(resolved.listDetectors()).resolves.toMatchObject({
      ok: true,
    });
  });
});
