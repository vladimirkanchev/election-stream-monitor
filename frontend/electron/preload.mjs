import { contextBridge, ipcRenderer } from "electron";

const electionBridge = Object.freeze({
  listDetectors: (mode) => ipcRenderer.invoke("bridge:list-detectors", mode),
  startSession: (input) => ipcRenderer.invoke("bridge:start-session", input),
  readSession: (sessionId) => ipcRenderer.invoke("bridge:read-session", sessionId),
  cancelSession: (sessionId) => ipcRenderer.invoke("bridge:cancel-session", sessionId),
  resolvePlaybackSource: (input) =>
    ipcRenderer.invoke("bridge:resolve-playback-source", input),
});

contextBridge.exposeInMainWorld("electionBridge", electionBridge);
