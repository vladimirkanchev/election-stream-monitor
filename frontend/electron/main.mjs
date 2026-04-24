import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handleBridgeOperation } from "./bridgeResponses.mjs";
import { registerFastApiBridgeHandlers } from "./bridgeHandlerRegistry.mjs";
import { createFastApiClient } from "./fastApiClient.mjs";
import { createFastApiStartupOrchestrator } from "./fastApiStartupOrchestrator.mjs";
import {
  createRemoteHlsProxyRegistry,
  isRemoteHlsUrl,
} from "./hlsProxy.mjs";
import { createLocalMediaResponseHandlers } from "./localMediaResponses.mjs";
import {
  createLocalMediaProtocolHandler,
} from "./localMediaRequestPolicy.mjs";
import { toRendererMediaUrl } from "./playbackSourcePolicy.mjs";

const require = createRequire(import.meta.url);
const { app, BrowserWindow, ipcMain, protocol } = require("electron");

/**
 * Electron main-process bridge for the local-first monitoring app.
 *
 * Responsibilities here are intentionally narrow and mostly compositional:
 *
 * - compose the Electron desktop runtime from focused helper modules
 * - own local FastAPI startup/readiness for the desktop runtime
 * - register the shared bridge/runtime wiring used by the renderer IPC surface
 * - expose a privileged `local-media://` protocol for local files
 * - proxy remote HLS assets through that local scheme when renderer playback
 *   would otherwise fail because of CORS
 *
 * Business rules such as source validation, monitoring lifecycle, and alert
 * semantics stay on the Python/backend side. Python CLI entry points remain
 * available for tooling/debugging, not as the normal runtime transport.
 *
 * Detailed ownership now lives in:
 *
 * - `bridgeHandlerRegistry.mjs` for IPC channel registration
 * - `fastApiClient.mjs` for FastAPI request/response shaping
 * - `playbackSourcePolicy.mjs` for renderer-safe playback URLs
 * - `localMediaResponses.mjs` for concrete protocol responses
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

const {
  apiGetHealth,
  apiListDetectors,
  apiReadSession,
  apiResolvePlaybackSource,
  apiStartSession,
  apiCancelSession,
} = createFastApiClient({
  baseUrl: FASTAPI_BASE_URL,
});

// `main.mjs` composes the startup/readiness seam but does not own its
// low-level process mechanics or readiness policy details.
const fastApiStartup = createFastApiStartupOrchestrator({
  repoRoot,
  host: FASTAPI_HOST,
  port: FASTAPI_PORT,
  hasExternalBaseUrl: Boolean(process.env.ELECTION_API_BASE_URL),
  startupTimeoutMs: FASTAPI_STARTUP_TIMEOUT_MS,
  healthcheckIntervalMs: FASTAPI_HEALTHCHECK_INTERVAL_MS,
  apiGetHealth,
});

const { handleRemoteHlsProxyRequest, handleLocalMediaRequest } = createLocalMediaResponseHandlers({
  remoteHlsProxyRegistry,
});

function resolveRendererPlaybackSource(source) {
  return toRendererMediaUrl(source, {
    isRemoteHlsUrl,
    registerRemoteHlsProxyUrl: (assetUrl) => remoteHlsProxyRegistry.register(assetUrl),
  });
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

function registerBridgeHandlers() {
  registerFastApiBridgeHandlers({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy: (operation) => fastApiStartup.runWithRuntimePolicy(operation),
    apiListDetectors,
    apiStartSession,
    apiReadSession,
    apiCancelSession,
    apiResolvePlaybackSource,
    resolveRendererPlaybackSource,
  });
}

function registerAppLifecycleHandlers() {
  app.on("before-quit", () => {
    // App lifecycle wiring stays here; the orchestrator handles the backend
    // policy/details behind this single shutdown call.
    void fastApiStartup.stopProcess();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}

function registerLocalMediaProtocol() {
  protocol.handle(
    "local-media",
    createLocalMediaProtocolHandler({
      handleRemoteHlsProxyRequest,
      handleLocalMediaRequest,
    }),
  );
}

async function initializeDesktopRuntime() {
  const readiness = await fastApiStartup.waitForReady();

  if (readiness.status === "failed_to_start") {
    console.error("[fastapi] failed to become ready", readiness.error);
  }

  registerLocalMediaProtocol();
  createWindow();
}

registerBridgeHandlers();
registerAppLifecycleHandlers();
app.whenReady().then(initializeDesktopRuntime);
