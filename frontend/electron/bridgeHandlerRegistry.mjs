/**
 * Registers the Electron IPC bridge handlers that share one FastAPI runtime
 * policy and one common bridge response envelope.
 *
 * This keeps `main.mjs` focused on Electron bootstrap while making the current
 * bridge channel map easy to review and test in one place.
 */

export function registerFastApiBridgeHandlers({
  ipcMain,
  handleBridgeOperation,
  runWithRuntimePolicy,
  apiListDetectors,
  apiStartSession,
  apiReadSession,
  apiCancelSession,
  apiResolvePlaybackSource,
  resolveRendererPlaybackSource,
}) {
  registerRuntimePolicyBridgeHandler({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy,
    channel: "bridge:list-detectors",
    errorCode: "DETECTOR_CATALOG_FAILED",
    errorMessage: "Detector catalog request failed",
    operation: (_event, mode) => apiListDetectors(mode),
  });
  registerRuntimePolicyBridgeHandler({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy,
    channel: "bridge:start-session",
    errorCode: "SESSION_START_FAILED",
    errorMessage: "Session start request failed",
    operation: (_event, input) => apiStartSession(input),
  });
  registerRuntimePolicyBridgeHandler({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy,
    channel: "bridge:read-session",
    errorCode: "SESSION_READ_FAILED",
    errorMessage: "Session read request failed",
    operation: (_event, sessionId) => apiReadSession(sessionId),
  });
  registerRuntimePolicyBridgeHandler({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy,
    channel: "bridge:cancel-session",
    errorCode: "SESSION_CANCEL_FAILED",
    errorMessage: "Session cancel request failed",
    operation: (_event, sessionId) => apiCancelSession(sessionId),
  });
  registerRuntimePolicyBridgeHandler({
    ipcMain,
    handleBridgeOperation,
    runWithRuntimePolicy,
    channel: "bridge:resolve-playback-source",
    errorCode: "PLAYBACK_SOURCE_RESOLUTION_FAILED",
    errorMessage: "Playback source resolution failed",
    operation: async (_event, input) => {
      const result = await apiResolvePlaybackSource(input);
      return resolveRendererPlaybackSource(result.source);
    },
  });
}

export function registerRuntimePolicyBridgeHandler({
  ipcMain,
  handleBridgeOperation,
  runWithRuntimePolicy,
  channel,
  errorCode,
  errorMessage,
  operation,
}) {
  ipcMain.handle(channel, async (...args) => {
    return handleBridgeOperation(
      errorCode,
      errorMessage,
      async () => runWithRuntimePolicy(
        () => operation(...args),
      ),
    );
  });
}
