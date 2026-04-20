export class FastApiUnavailableError extends Error {
  constructor(message = "Local FastAPI backend is unavailable") {
    super(message);
    this.name = "FastApiUnavailableError";
  }
}

export function createFastApiRuntimeState() {
  return {
    status: "idle",
  };
}

export async function waitForFastApiReady({
  state,
  ensureFastApiProcessStarted,
  apiGetHealth,
  markReady,
  markUnavailable,
  delay,
  timeoutMs,
  intervalMs,
  now = Date.now,
}) {
  state.status = "starting";
  await ensureFastApiProcessStarted();

  const deadline = now() + timeoutMs;
  let lastError = null;

  while (now() < deadline) {
    try {
      await apiGetHealth();
      markReady();
      state.status = "ready";
      return { status: "ready" };
    } catch (error) {
      lastError = error;
      await delay(intervalMs);
    }
  }

  markUnavailable();
  state.status = "failed_to_start";
  return {
    status: "failed_to_start",
    error: lastError,
  };
}

export async function runWithFastApiRuntimePolicy({
  state,
  waitForFastApiReadyImpl,
  operation,
}) {
  if (state.status === "idle" || state.status === "starting") {
    const readiness = await waitForFastApiReadyImpl();
    if (readiness.status !== "ready") {
      throw new FastApiUnavailableError();
    }
  }

  if (state.status === "failed_to_start") {
    throw new FastApiUnavailableError();
  }

  return operation();
}
