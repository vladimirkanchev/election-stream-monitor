import { access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

import { createFastApiReadinessState } from "./fastApiFallback.mjs";
import {
  createFastApiProcessState,
  ensureFastApiProcessStarted,
  stopFastApiProcess,
} from "./fastApiProcessManager.mjs";
import {
  createFastApiRuntimeState,
  runWithFastApiRuntimePolicy,
  waitForFastApiReady,
} from "./fastApiRuntimePolicy.mjs";

/**
 * Compose Electron-side FastAPI startup and readiness policy behind one seam.
 *
 * Ownership here is intentionally limited to:
 * - resolving the local uvicorn command when needed
 * - asking the low-level process manager to start/stop the backend
 * - tracking readiness state and gating bridge operations on it
 *
 * Low-level child-process mechanics stay in `fastApiProcessManager.mjs`, while
 * `main.mjs` remains responsible for app/window wiring and IPC registration.
 */

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function createFastApiStartupOrchestrator({
  repoRoot,
  host,
  port,
  hasExternalBaseUrl = false,
  startupTimeoutMs,
  healthcheckIntervalMs,
  apiGetHealth,
  env = process.env,
  spawnProcess = spawn,
  now = Date.now,
  accessExecutable = access,
  stdout = process.stdout,
  stderr = process.stderr,
  delayImpl = delay,
}) {
  let readinessState = createFastApiReadinessState();
  const runtimeState = createFastApiRuntimeState();
  const processState = createFastApiProcessState();

  async function resolvePythonExecutable() {
    const venvPython = path.join(repoRoot, ".venv", "bin", "python");
    try {
      await accessExecutable(venvPython, fsConstants.X_OK);
      return venvPython;
    } catch {
      return "python3";
    }
  }

  async function resolveFastApiCommand() {
    const pythonExecutable = await resolvePythonExecutable();
    return {
      command: pythonExecutable,
      args: [
        "-m",
        "uvicorn",
        "api.app:app",
        "--app-dir",
        "src",
        "--host",
        host,
        "--port",
        String(port),
      ],
    };
  }

  function markReady() {
    readinessState = createFastApiReadinessState();
    readinessState.checkedAt = now();
    readinessState.available = true;
  }

  function markUnavailable() {
    readinessState = createFastApiReadinessState();
    readinessState.checkedAt = now();
    readinessState.available = false;
  }

  async function ensureCurrentFastApiProcessStarted() {
    return ensureFastApiProcessStarted({
      state: processState,
      hasExternalBaseUrl,
      resolveCommand: resolveFastApiCommand,
      spawnProcess,
      cwd: repoRoot,
      env: {
        ...env,
        PYTHONUNBUFFERED: "1",
      },
      stdout,
      stderr,
    });
  }

  async function waitForReady() {
    return waitForFastApiReady({
      state: runtimeState,
      ensureFastApiProcessStarted: ensureCurrentFastApiProcessStarted,
      apiGetHealth,
      markReady,
      markUnavailable,
      delay: delayImpl,
      timeoutMs: startupTimeoutMs,
      intervalMs: healthcheckIntervalMs,
      now,
    });
  }

  async function runWithRuntimePolicy(operation) {
    return runWithFastApiRuntimePolicy({
      state: runtimeState,
      waitForFastApiReadyImpl: waitForReady,
      operation,
    });
  }

  return {
    // Shutdown integration stays in `main.mjs`; this just exposes the
    // orchestrator-owned process stop hook.
    stopProcess: () => stopFastApiProcess(processState),
    waitForReady,
    runWithRuntimePolicy,
  };
}
