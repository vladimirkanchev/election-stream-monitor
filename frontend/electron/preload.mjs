import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { contextBridge, ipcRenderer } = require("electron");

// Expose the stable renderer bridge; Electron runtime policy lives in main.
const electionBridge = Object.freeze({
  listDetectors: (mode) => ipcRenderer.invoke("bridge:list-detectors", mode),
  startSession: (input) => ipcRenderer.invoke("bridge:start-session", input),
  readSession: (sessionId) => ipcRenderer.invoke("bridge:read-session", sessionId),
  cancelSession: (sessionId) => ipcRenderer.invoke("bridge:cancel-session", sessionId),
  resolvePlaybackSource: (input) =>
    ipcRenderer.invoke("bridge:resolve-playback-source", input),
});

contextBridge.exposeInMainWorld("electionBridge", electionBridge);
