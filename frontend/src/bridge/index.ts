import { createNormalizedBridge } from "./contract";
import { resolveBridgeTransport } from "./transport";

const rawTransport = resolveBridgeTransport(window);

export const localBridge = createNormalizedBridge(rawTransport);
