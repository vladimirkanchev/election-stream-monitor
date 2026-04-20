import { app, BrowserWindow, ipcMain, protocol } from "electron";
import { access, readFile, stat } from "node:fs/promises";
import { constants as fsConstants, createReadStream } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawn } from "node:child_process";
import { Readable } from "node:stream";
import {
  ApiHttpError,
  createFastApiReadinessState,
} from "./fastApiFallback.mjs";
import {
  createFastApiProcessState,
  ensureFastApiProcessStarted as ensureFastApiProcessStartedWithState,
  stopFastApiProcess as stopFastApiProcessWithState,
} from "./fastApiProcessManager.mjs";
import {
  createFastApiRuntimeState,
  runWithFastApiRuntimePolicy,
  waitForFastApiReady,
} from "./fastApiRuntimePolicy.mjs";
import { handleBridgeOperation, isApiErrorPayload } from "./bridgeResponses.mjs";
import {
  createRemotePlaybackRequestHeaders,
  createRemoteHlsProxyRegistry,
  isRemoteHlsUrl,
  isRemoteHttpUrl,
  parseProxyToken,
  parseRemoteHlsProxyPayload,
} from "./hlsProxy.mjs";

/**
 * Electron main-process bridge for the local-first monitoring app.
 *
 * Responsibilities here are intentionally narrow:
 *
 * - translate IPC requests into FastAPI-backed backend calls under one shared
 *   runtime policy, including local FastAPI startup/readiness ownership
 * - expose a privileged ``local-media://`` protocol for local files
 * - proxy remote HLS assets through that local scheme when renderer playback
 *   would otherwise fail because of CORS
 *
 * Business rules such as source validation, monitoring lifecycle, and alert
 * semantics stay on the Python/backend side. Python CLI entry points remain
 * available for tooling/debugging, not as the normal runtime transport.
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const preloadPath = path.join(__dirname, "preload.mjs");
const remoteHlsProxyRegistry = createRemoteHlsProxyRegistry();
const FASTAPI_HOST = "127.0.0.1";
const FASTAPI_PORT = Number(process.env.ELECTION_API_PORT ?? "8000");
const FASTAPI_BASE_URL =
  process.env.ELECTION_API_BASE_URL ?? `http://${FASTAPI_HOST}:${FASTAPI_PORT}`;
const FASTAPI_STARTUP_TIMEOUT_MS = 10_000;
const FASTAPI_HEALTHCHECK_INTERVAL_MS = 250;

let fastApiReadiness = createFastApiReadinessState();
let fastApiRuntimeState = createFastApiRuntimeState();
let fastApiProcessState = createFastApiProcessState();

protocol.registerSchemesAsPrivileged([
  {
    scheme: "local-media",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

// Keep the Electron shell conservative on Linux dev machines where GPU or
// Wayland issues can prevent the app window from opening at all.
app.disableHardwareAcceleration();
app.commandLine.appendSwitch("no-sandbox");
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-software-rasterizer");
app.commandLine.appendSwitch("disable-dev-shm-usage");
app.commandLine.appendSwitch("in-process-gpu");
app.commandLine.appendSwitch("ignore-gpu-blocklist");
app.commandLine.appendSwitch("disable-features", "UseOzonePlatform");
app.commandLine.appendSwitch("ozone-platform", "x11");

async function resolvePythonExecutable() {
  const venvPython = path.join(repoRoot, ".venv", "bin", "python");
  try {
    await access(venvPython, fsConstants.X_OK);
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
      FASTAPI_HOST,
      "--port",
      String(FASTAPI_PORT),
    ],
  };
}

async function ensureCurrentFastApiProcessStarted() {
  return ensureFastApiProcessStartedWithState({
    state: fastApiProcessState,
    hasExternalBaseUrl: Boolean(process.env.ELECTION_API_BASE_URL),
    resolveCommand: resolveFastApiCommand,
    spawnProcess: spawn,
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
    },
  });
}

async function stopFastApiProcess() {
  return stopFastApiProcessWithState(fastApiProcessState);
}

async function callApi(path, options = {}) {
  const response = await fetch(`${FASTAPI_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  let payload = null;
  if (isJson) {
    payload = await response.json();
  } else {
    const text = await response.text();
    payload = text.length > 0 ? text : null;
  }

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

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
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
  return callApi("/playback/resolve", {
    method: "POST",
    body: JSON.stringify({
      mode: input.source.kind,
      input_path: input.source.path,
      current_item: input.currentItem,
    }),
  });
}

async function apiStartSession(input) {
  return callApi("/sessions", {
    method: "POST",
    body: JSON.stringify({
      mode: input.source.kind,
      input_path: input.source.path,
      selected_detectors: input.selectedDetectors ?? [],
    }),
  });
}

async function apiCancelSession(sessionId) {
  return callApi(`/sessions/${encodeURIComponent(sessionId)}/cancel`, {
    method: "POST",
  });
}

function markFastApiReady() {
  fastApiReadiness = createFastApiReadinessState();
  fastApiReadiness.checkedAt = Date.now();
  fastApiReadiness.available = true;
}

function markFastApiUnavailable() {
  fastApiReadiness = createFastApiReadinessState();
  fastApiReadiness.checkedAt = Date.now();
  fastApiReadiness.available = false;
}

async function waitForCurrentFastApiReady() {
  return waitForFastApiReady({
    state: fastApiRuntimeState,
    ensureFastApiProcessStarted: ensureCurrentFastApiProcessStarted,
    apiGetHealth,
    markReady: markFastApiReady,
    markUnavailable: markFastApiUnavailable,
    delay,
    timeoutMs: FASTAPI_STARTUP_TIMEOUT_MS,
    intervalMs: FASTAPI_HEALTHCHECK_INTERVAL_MS,
  });
}

async function runWithCurrentFastApiRuntimePolicy(operation) {
  return runWithFastApiRuntimePolicy({
    state: fastApiRuntimeState,
    waitForFastApiReadyImpl: waitForCurrentFastApiReady,
    operation,
  });
}

function isAllowedRemotePlaybackSource(source) {
  return source.startsWith("http://") || source.startsWith("https://");
}

function toRendererMediaUrl(source) {
  if (!source) {
    return null;
  }

  if (isAllowedRemotePlaybackSource(source)) {
    if (isRemoteHlsUrl(source)) {
      return remoteHlsProxyRegistry.register(source);
    }
    return source;
  }

  // Only the backend decides which remote schemes are safe. Anything else that
  // still looks like a scheme here is rejected instead of being forwarded into
  // the renderer as a playable source.
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(source)) {
    throw new Error("Unsupported playback source scheme returned by backend");
  }

  const fileUrl = pathToFileURL(source);
  return `local-media://media${fileUrl.pathname}`;
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1180,
    minHeight: 820,
    backgroundColor: "#f6f1e8",
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (app.isPackaged) {
    window.loadFile(path.join(frontendRoot, "dist", "index.html"));
  } else {
    window.loadURL("http://127.0.0.1:5173");
  }
}

ipcMain.handle("bridge:list-detectors", async (_event, mode) => {
  return handleBridgeOperation(
    "DETECTOR_CATALOG_FAILED",
    "Detector catalog request failed",
    async () => runWithCurrentFastApiRuntimePolicy(
      () => apiListDetectors(mode),
    ),
  );
});

ipcMain.handle("bridge:start-session", async (_event, input) => {
  return handleBridgeOperation(
    "SESSION_START_FAILED",
    "Session start request failed",
    async () => runWithCurrentFastApiRuntimePolicy(
      () => apiStartSession(input),
    ),
  );
});

ipcMain.handle("bridge:read-session", async (_event, sessionId) => {
  return handleBridgeOperation(
    "SESSION_READ_FAILED",
    "Session read request failed",
    async () => runWithCurrentFastApiRuntimePolicy(
      () => apiReadSession(sessionId),
    ),
  );
});

ipcMain.handle("bridge:cancel-session", async (_event, sessionId) => {
  return handleBridgeOperation(
    "SESSION_CANCEL_FAILED",
    "Session cancel request failed",
    async () => runWithCurrentFastApiRuntimePolicy(
      () => apiCancelSession(sessionId),
    ),
  );
});

ipcMain.handle("bridge:resolve-playback-source", async (_event, input) => {
  return handleBridgeOperation(
    "PLAYBACK_SOURCE_RESOLUTION_FAILED",
    "Playback source resolution failed",
    async () => runWithCurrentFastApiRuntimePolicy(async () => {
      const result = await apiResolvePlaybackSource(input);
      return toRendererMediaUrl(result.source);
    }),
  );
});

app.on("before-quit", () => {
  void stopFastApiProcess();
});

app.whenReady().then(async () => {
  const readiness = await waitForCurrentFastApiReady();

  if (readiness.status === "failed_to_start") {
    console.error("[fastapi] failed to become ready", readiness.error);
  }

  protocol.handle("local-media", async (request) => {
    const requestUrl = new URL(request.url);
    if (requestUrl.hostname === "proxy") {
      return handleRemoteHlsProxyRequest(request, requestUrl);
    }
    return handleLocalMediaRequest(request, requestUrl);
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

async function handleRemoteHlsProxyRequest(request, requestUrl) {
  // Proxy tokens are opaque renderer-facing identifiers. Only the main
  // process knows the upstream target URL they resolve to.
  const token = parseProxyToken(requestUrl.pathname);
  if (!token) {
    return new Response("Missing proxy token", { status: 400 });
  }

  const targetUrl = remoteHlsProxyRegistry.resolve(token);
  if (!targetUrl || !isRemoteHttpUrl(targetUrl)) {
    return new Response("Unknown proxied media target", { status: 404 });
  }

  console.info("[remote-hls-proxy]", request.method, targetUrl);

  try {
    const remoteResponse = await fetchRemotePlaybackAsset(targetUrl, request);
    const proxyPayload = await parseRemoteHlsProxyPayload({
      targetUrl,
      remoteResponse,
      registerProxyUrl: (assetUrl) => remoteHlsProxyRegistry.register(assetUrl),
      guessContentType,
    });
    console.info(
      "[remote-hls-proxy] upstream response",
      JSON.stringify({
        targetUrl,
        status: proxyPayload.status,
        contentType: proxyPayload.contentType,
      }),
    );

    if (proxyPayload.kind === "error") {
      if (proxyPayload.preview) {
        console.error(
          "[remote-hls-proxy] upstream error preview",
          JSON.stringify({
            targetUrl,
            status: proxyPayload.status,
            preview: proxyPayload.preview,
          }),
        );
      }
      return new Response(proxyPayload.message, { status: proxyPayload.status });
    }

    if (proxyPayload.kind === "invalid_playlist") {
      console.error(
        "[remote-hls-proxy] invalid playlist response",
        JSON.stringify({
          targetUrl,
          contentType: proxyPayload.contentType,
          upstreamKind: proxyPayload.upstreamKind,
          preview: proxyPayload.preview,
        }),
      );
      return new Response(proxyPayload.message, { status: proxyPayload.status });
    }

    if (proxyPayload.kind === "playlist") {
      return buildPlaylistResponse(proxyPayload.bodyText, proxyPayload.contentType, proxyPayload.status);
    }

    return buildProxyAssetResponse(remoteResponse, proxyPayload);
  } catch (error) {
    console.error("[remote-hls-proxy] failed", targetUrl, error);
    return new Response("Failed to proxy remote HLS asset", { status: 502 });
  }
}

async function fetchRemotePlaybackAsset(targetUrl, request) {
  return fetch(targetUrl, {
    method: "GET",
    headers: createRemotePlaybackRequestHeaders(request.headers.get("range")),
  });
}

async function handleLocalMediaRequest(request, requestUrl) {
  // The local-media protocol serves both checked-in local fixtures and
  // backend-resolved local file paths through one renderer-safe URL space.
  const filePath = decodeURIComponent(requestUrl.pathname);
  if (!filePath) {
    return new Response("Missing media path", { status: 400 });
  }

  console.info("[local-media]", request.method, filePath);

  try {
    await access(filePath, fsConstants.R_OK);
  } catch {
    console.error("[local-media] missing file", filePath);
    return new Response("Media file not found", { status: 404 });
  }

  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".m3u8") {
    return buildLocalPlaylistResponse(filePath);
  }
  return buildLocalBinaryMediaResponse(filePath, request, extension);
}

async function buildLocalPlaylistResponse(filePath) {
  return buildPlaylistResponse(
    await readFile(filePath, "utf-8"),
    guessContentType(filePath),
  );
}

async function buildLocalBinaryMediaResponse(filePath, request, extension) {
  // We currently support range responses primarily for MP4 playback, because
  // that is the path Chromium most often probes with byte-range requests.
  const statResult = await stat(filePath);
  const totalSize = statResult.size;
  const range = parseLocalMediaRangeRequest({
    rangeHeader: request.headers.get("range"),
    totalSize,
    allowPartialResponse: extension === ".mp4",
  });

  if (range.kind === "invalid") {
    return new Response("Requested range not satisfiable", {
      status: 416,
      headers: {
        "content-range": `bytes */${totalSize}`,
      },
    });
  }

  const headers = new Headers({
    "accept-ranges": "bytes",
    "cache-control": "no-store",
    "content-type": guessContentType(filePath),
    "content-length": String(range.end - range.start + 1),
  });
  if (range.status === 206) {
    headers.set("content-range", `bytes ${range.start}-${range.end}/${totalSize}`);
  }

  const stream = createReadStream(filePath, { start: range.start, end: range.end });
  return new Response(Readable.toWeb(stream), {
    status: range.status,
    headers,
  });
}

function parseLocalMediaRangeRequest({ rangeHeader, totalSize, allowPartialResponse }) {
  // Keep range parsing intentionally conservative. If we cannot parse a sane
  // range, the caller either falls back to a whole-file response or returns a
  // standard 416 for out-of-bounds ranges.
  let start = 0;
  let end = totalSize > 0 ? totalSize - 1 : 0;
  let status = 200;

  if (allowPartialResponse && rangeHeader) {
    const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
    if (match) {
      if (match[1]) {
        start = Number.parseInt(match[1], 10);
      }
      if (match[2]) {
        end = Number.parseInt(match[2], 10);
      }
      if (!match[2] && totalSize > 0) {
        end = totalSize - 1;
      }
      status = 206;
    }
  }

  if (start > end || start >= totalSize) {
    return { kind: "invalid" };
  }

  return {
    kind: "ok",
    start,
    end,
    status,
  };
}

function buildPlaylistResponse(playlistBody, contentType, status = 200) {
  // Playlist responses are always no-store because both local HLS fixtures and
  // proxied remote playlists can change between refreshes.
  return new Response(playlistBody, {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": contentType,
    },
  });
}

function buildProxyAssetResponse(remoteResponse, proxyPayload) {
  // Non-playlist assets already carry the content stream from the upstream
  // fetch, so the main process only needs to attach the sanitized headers.
  return new Response(remoteResponse.body, {
    status: proxyPayload.status,
    headers: proxyPayload.headers,
  });
}

function guessContentType(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".mp4") {
    return "video/mp4";
  }
  if (extension === ".m3u8") {
    return "application/vnd.apple.mpegurl";
  }
  if (extension === ".ts") {
    return "video/mp2t";
  }
  return "application/octet-stream";
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
