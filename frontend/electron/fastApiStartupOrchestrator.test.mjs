import { describe, expect, it, vi } from "vitest";

import { createFastApiStartupOrchestrator } from "./fastApiStartupOrchestrator.mjs";

function createMockChild() {
  const listeners = new Map();

  return {
    killed: false,
    stdout: { on: vi.fn() },
    stderr: { on: vi.fn() },
    once: vi.fn((event, handler) => {
      listeners.set(event, handler);
    }),
    kill: vi.fn(),
    emit(event) {
      const handler = listeners.get(event);
      if (handler) {
        handler();
      }
    },
  };
}

describe("FastAPI startup orchestrator", () => {
  it("starts the local backend and marks readiness through the composed policy", async () => {
    const child = createMockChild();
    const spawnProcess = vi.fn().mockReturnValue(child);
    const apiGetHealth = vi.fn()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce({ ok: true });

    let currentTime = 1_000;
    const orchestrator = createFastApiStartupOrchestrator({
      repoRoot: "/repo",
      host: "127.0.0.1",
      port: 8000,
      startupTimeoutMs: 1_000,
      healthcheckIntervalMs: 100,
      apiGetHealth,
      spawnProcess,
      accessExecutable: vi.fn().mockResolvedValue(undefined),
      delayImpl: vi.fn().mockImplementation(async (ms) => {
        currentTime += ms;
      }),
      now: () => currentTime,
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    const readiness = await orchestrator.waitForReady();
    const result = await orchestrator.runWithRuntimePolicy(
      vi.fn().mockResolvedValue({ ok: true }),
    );

    expect(readiness).toEqual({ status: "ready" });
    expect(result).toEqual({ ok: true });
    expect(spawnProcess).toHaveBeenCalledWith(
      "/repo/.venv/bin/python",
      [
        "-m",
        "uvicorn",
        "api.app:app",
        "--app-dir",
        "src",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
      ],
      expect.objectContaining({
        cwd: "/repo",
        env: expect.objectContaining({ PYTHONUNBUFFERED: "1" }),
      }),
    );
  });

  it("falls back to python3 and stops the spawned process cleanly", async () => {
    const child = createMockChild();
    const spawnProcess = vi.fn().mockReturnValue(child);

    const orchestrator = createFastApiStartupOrchestrator({
      repoRoot: "/repo",
      host: "127.0.0.1",
      port: 8000,
      startupTimeoutMs: 500,
      healthcheckIntervalMs: 100,
      apiGetHealth: vi.fn().mockResolvedValue({ ok: true }),
      spawnProcess,
      accessExecutable: vi.fn().mockRejectedValue(new Error("missing venv")),
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    await orchestrator.waitForReady();
    await orchestrator.stopProcess();

    expect(spawnProcess).toHaveBeenCalledWith(
      "python3",
      expect.any(Array),
      expect.any(Object),
    );
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
  });
});
