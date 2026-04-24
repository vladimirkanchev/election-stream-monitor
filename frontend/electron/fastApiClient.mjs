import { ApiHttpError } from "./apiErrors.mjs";
import { isApiErrorPayload } from "./bridgeResponses.mjs";

/**
 * Thin JSON client for the Electron-to-FastAPI bridge surface.
 *
 * The main process owns runtime policy and IPC registration, while this module
 * keeps request/response shaping for the backend HTTP surface in one place.
 *
 * It intentionally does not own fallback behavior, IPC registration, or
 * renderer-facing playback URL policy.
 */

export function createFastApiClient({ baseUrl, fetchImpl = fetch }) {
  async function callApi(path, options = {}) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      headers: buildJsonRequestHeaders(options),
      ...options,
    });

    const { isJson, payload } = await readApiPayload(response);

    if (!response.ok) {
      const message = isApiErrorPayload(payload)
        ? payload.detail
        : `FastAPI request failed: ${response.status}`;
      throw new ApiHttpError(message, {
        status: response.status,
        apiPayload: isApiErrorPayload(payload) ? payload : null,
      });
    }

    if (!isJson) {
      throw new ApiHttpError("FastAPI returned a non-JSON response", {
        status: response.status,
      });
    }

    return payload;
  }

  async function apiGetHealth() {
    return callApi("/health");
  }

  async function apiListDetectors(mode) {
    const params = new URLSearchParams();
    if (mode) {
      params.set("mode", mode);
    }
    const query = params.toString();
    return callApi(`/detectors${query ? `?${query}` : ""}`);
  }

  async function apiReadSession(sessionId) {
    return callApi(`/sessions/${encodeURIComponent(sessionId)}`);
  }

  async function apiResolvePlaybackSource(input) {
    return postJson("/playback/resolve", {
      mode: input.source.kind,
      input_path: input.source.path,
      current_item: input.currentItem,
    });
  }

  async function apiStartSession(input) {
    return postJson("/sessions", {
      mode: input.source.kind,
      input_path: input.source.path,
      selected_detectors: input.selectedDetectors ?? [],
    });
  }

  async function apiCancelSession(sessionId) {
    return callApi(`/sessions/${encodeURIComponent(sessionId)}/cancel`, {
      method: "POST",
    });
  }

  return {
    apiGetHealth,
    apiListDetectors,
    apiReadSession,
    apiResolvePlaybackSource,
    apiStartSession,
      apiCancelSession,
  };

  function postJson(path, payload) {
    return callApi(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

function buildJsonRequestHeaders(options) {
  return {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers ?? {}),
  };
}

async function readApiPayload(response) {
  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (isJson) {
    return {
      isJson,
      payload: await response.json(),
    };
  }

  const text = await response.text();
  return {
    isJson,
    payload: text.length > 0 ? text : null,
  };
}
