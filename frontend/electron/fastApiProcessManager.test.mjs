import { describe, expect, it, vi } from "vitest";

import {
  createFastApiProcessState,
  ensureFastApiProcessStarted,
  stopFastApiProcess,
} from "./fastApiProcessManager.mjs";

function createMockChild() {
  const listeners = new Map();

  return {
    killed: false,
    stdout: { on: vi.fn() },
    stderr: { on: vi.fn() },
    once: vi.fn((event, handler) => {
      listeners.set(event, handler);
    }),
    kill: vi.fn((signal) => {
      void signal;
    }),
    emit(event) {
      const handler = listeners.get(event);
      if (handler) {
        handler();
      }
    },
  };
}

describe("FastAPI process manager", () => {
  it("starts the FastAPI process only once for repeated startup requests", async () => {
    const state = createFastApiProcessState();
    const child = createMockChild();
    const spawnProcess = vi.fn().mockReturnValue(child);

    const first = await ensureFastApiProcessStarted({
      state,
      resolveCommand: vi.fn().mockResolvedValue({
        command: "python3",
        args: ["-m", "uvicorn"],
      }),
      spawnProcess,
      cwd: "/repo",
      env: {},
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    const second = await ensureFastApiProcessStarted({
      state,
      resolveCommand: vi.fn(),
      spawnProcess,
      cwd: "/repo",
      env: {},
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    expect(first).toBe(child);
    expect(second).toBe(child);
    expect(spawnProcess).toHaveBeenCalledTimes(1);
  });

  it("clears process state after the child exits so a later call can respawn", async () => {
    const state = createFastApiProcessState();
    const firstChild = createMockChild();
    const secondChild = createMockChild();
    const spawnProcess = vi.fn()
      .mockReturnValueOnce(firstChild)
      .mockReturnValueOnce(secondChild);

    await ensureFastApiProcessStarted({
      state,
      resolveCommand: vi.fn().mockResolvedValue({
        command: "python3",
        args: ["-m", "uvicorn"],
      }),
      spawnProcess,
      cwd: "/repo",
      env: {},
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    firstChild.emit("exit");

    const respawned = await ensureFastApiProcessStarted({
      state,
      resolveCommand: vi.fn().mockResolvedValue({
        command: "python3",
        args: ["-m", "uvicorn"],
      }),
      spawnProcess,
      cwd: "/repo",
      env: {},
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    expect(respawned).toBe(secondChild);
    expect(spawnProcess).toHaveBeenCalledTimes(2);
  });

  it("does not spawn a local process when an external FastAPI base URL is configured", async () => {
    const state = createFastApiProcessState();
    const spawnProcess = vi.fn();

    const result = await ensureFastApiProcessStarted({
      state,
      hasExternalBaseUrl: true,
      resolveCommand: vi.fn(),
      spawnProcess,
      cwd: "/repo",
      env: {},
      stdout: { write: vi.fn() },
      stderr: { write: vi.fn() },
    });

    expect(result).toBeNull();
    expect(spawnProcess).not.toHaveBeenCalled();
  });

  it("stops the running process and clears state", async () => {
    const state = createFastApiProcessState();
    const child = createMockChild();
    state.child = child;
    state.startupPromise = Promise.resolve(child);

    await stopFastApiProcess(state);

    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
    expect(state.child).toBeNull();
    expect(state.startupPromise).toBeNull();
  });
});
