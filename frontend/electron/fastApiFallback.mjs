export class ApiHttpError extends Error {
  constructor(message, { status, apiPayload } = {}) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status ?? null;
    this.apiPayload = apiPayload ?? null;
  }
}

export function createFastApiReadinessState() {
  return {
    checkedAt: 0,
    available: false,
  };
}

export function isFastApiUnavailableError(error) {
  if (error instanceof TypeError) {
    return true;
  }

  if (error instanceof ApiHttpError) {
    return error.status === null;
  }

  return false;
}

export async function isFastApiAvailable({
  state,
  apiGetHealth,
  ttlMs = 1500,
  now = Date.now,
}) {
  const currentTime = now();
  if (currentTime - state.checkedAt < ttlMs) {
    return state.available;
  }

  try {
    await apiGetHealth();
    state.checkedAt = currentTime;
    state.available = true;
    return true;
  } catch {
    state.checkedAt = currentTime;
    state.available = false;
    return false;
  }
}

export async function withFastApiFallback({
  state,
  apiGetHealth,
  operationName,
  apiOperation,
  cliOperation,
  ttlMs = 1500,
  now = Date.now,
  warn = console.warn,
}) {
  const available = await isFastApiAvailable({
    state,
    apiGetHealth,
    ttlMs,
    now,
  });

  if (!available) {
    warn(`[bridge] FastAPI unavailable, falling back to CLI for ${operationName}`);
    return cliOperation();
  }

  try {
    return await apiOperation();
  } catch (error) {
    if (isFastApiUnavailableError(error)) {
      state.checkedAt = now();
      state.available = false;
      warn(
        `[bridge] FastAPI request failed, falling back to CLI for ${operationName}`,
        error,
      );
      return cliOperation();
    }

    throw error;
  }
}

export async function resolvePlaybackSourceWithFallback({
  state,
  apiGetHealth,
  apiResolvePlaybackSource,
  cliResolvePlaybackSource,
  input,
  toRendererMediaUrl,
  ttlMs = 1500,
  now = Date.now,
  warn = console.warn,
}) {
  const result = await withFastApiFallback({
    state,
    apiGetHealth,
    operationName: "bridge:resolve-playback-source",
    apiOperation: () => apiResolvePlaybackSource(input),
    cliOperation: () => cliResolvePlaybackSource(input),
    ttlMs,
    now,
    warn,
  });

  return toRendererMediaUrl(result.source);
}
