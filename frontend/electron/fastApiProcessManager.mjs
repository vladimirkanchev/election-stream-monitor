/**
 * Low-level FastAPI child-process ownership for the Electron desktop runtime.
 *
 * This module intentionally stays narrow:
 * - spawn and track the child process
 * - stream child stdout/stderr for diagnostics
 * - clear child state on exit/error
 * - stop the child during shutdown
 *
 * Startup/readiness policy belongs in higher-level orchestration rather than
 * here, so this file can stay focused on process lifecycle primitives.
 */

export function createFastApiProcessState() {
  return {
    child: null,
    startupPromise: null,
  };
}

export async function ensureFastApiProcessStarted({
  state,
  hasExternalBaseUrl = false,
  resolveCommand,
  spawnProcess,
  cwd,
  env,
  stdout = process.stdout,
  stderr = process.stderr,
}) {
  if (hasExternalBaseUrl) {
    return null;
  }

  if (state.child && !state.child.killed) {
    return state.child;
  }

  if (state.startupPromise) {
    return state.startupPromise;
  }

  state.startupPromise = (async () => {
    const { command, args } = await resolveCommand();

    const child = spawnProcess(command, args, {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout?.on("data", (chunk) => {
      stdout.write(`[fastapi] ${chunk}`);
    });

    child.stderr?.on("data", (chunk) => {
      stderr.write(`[fastapi] ${chunk}`);
    });

    child.once("exit", () => {
      if (state.child === child) {
        state.child = null;
      }
      state.startupPromise = null;
    });

    child.once("error", () => {
      if (state.child === child) {
        state.child = null;
      }
      state.startupPromise = null;
    });

    state.child = child;
    return child;
  })();

  try {
    return await state.startupPromise;
  } finally {
    state.startupPromise = null;
  }
}

export async function stopFastApiProcess(state) {
  const child = state.child;
  state.child = null;
  state.startupPromise = null;

  if (!child || child.killed) {
    return;
  }

  child.kill("SIGTERM");
}
