import { describe, expect, it, vi } from "vitest";

import {
  FastApiUnavailableError,
  createFastApiRuntimeState,
  runWithFastApiRuntimePolicy,
  waitForFastApiReady,
} from "./fastApiRuntimePolicy.mjs";

describe("FastAPI runtime policy", () => {
  it("marks the runtime ready when health succeeds before timeout", async () => {
    let currentTime = 10_000;
    const now = () => currentTime;
    const delay = vi.fn().mockImplementation(async (ms) => {
      currentTime += ms;
    });

    const state = createFastApiRuntimeState();
    const markReady = vi.fn();
    const markUnavailable = vi.fn();

    const result = await waitForFastApiReady({
      state,
      ensureFastApiProcessStarted: vi.fn(),
      apiGetHealth: vi.fn()
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce({ ok: true }),
      markReady,
      markUnavailable,
      delay,
      timeoutMs: 1500,
      intervalMs: 250,
      now,
    });

    expect(result).toEqual({ status: "ready" });
    expect(state.status).toBe("ready");
    expect(markReady).toHaveBeenCalledTimes(1);
    expect(markUnavailable).not.toHaveBeenCalled();
  });

  it("marks the runtime failed_to_start when health never succeeds before timeout", async () => {
    let currentTime = 10_000;
    const now = () => currentTime;
    const delay = vi.fn().mockImplementation(async (ms) => {
      currentTime += ms;
    });

    const state = createFastApiRuntimeState();
    const markReady = vi.fn();
    const markUnavailable = vi.fn();

    const result = await waitForFastApiReady({
      state,
      ensureFastApiProcessStarted: vi.fn(),
      apiGetHealth: vi.fn().mockRejectedValue(new TypeError("fetch failed")),
      markReady,
      markUnavailable,
      delay,
      timeoutMs: 500,
      intervalMs: 250,
      now,
    });

    expect(result.status).toBe("failed_to_start");
    expect(state.status).toBe("failed_to_start");
    expect(markReady).not.toHaveBeenCalled();
    expect(markUnavailable).toHaveBeenCalledTimes(1);
  });

  it("runs the operation immediately when runtime is already ready", async () => {
    const state = createFastApiRuntimeState();
    state.status = "ready";

    const operation = vi.fn().mockResolvedValue({ ok: true });

    const result = await runWithFastApiRuntimePolicy({
      state,
      waitForFastApiReadyImpl: vi.fn(),
      operation,
    });

    expect(result).toEqual({ ok: true });
    expect(operation).toHaveBeenCalledTimes(1);
  });

  it("throws a clear unavailable error when startup fails", async () => {
    const state = createFastApiRuntimeState();
    const operation = vi.fn();

    await expect(
      runWithFastApiRuntimePolicy({
        state,
        waitForFastApiReadyImpl: vi.fn().mockResolvedValue({ status: "failed_to_start" }),
        operation,
      }),
    ).rejects.toBeInstanceOf(FastApiUnavailableError);

    expect(operation).not.toHaveBeenCalled();
  });

  it("throws immediately when runtime is already failed_to_start", async () => {
    const state = createFastApiRuntimeState();
    state.status = "failed_to_start";

    await expect(
      runWithFastApiRuntimePolicy({
        state,
        waitForFastApiReadyImpl: vi.fn(),
        operation: vi.fn(),
      }),
    ).rejects.toBeInstanceOf(FastApiUnavailableError);
  });
});
