import type { BridgeTransport } from "./bridge/contract";

declare global {
  interface Window {
    electionBridge?: BridgeTransport;
  }
}

export {};
