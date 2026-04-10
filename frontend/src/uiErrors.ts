import {
  BridgeTransportError,
  isBridgeTransportError,
  type BridgeErrorCode,
} from "./bridge/contract";
import type { MonitorSource, SessionStatus } from "./types";

export function getSessionStartErrorMessage(
  error?: unknown,
  sourceKind?: MonitorSource["kind"],
): string {
  if (sourceKind === "api_stream") {
    return getApiStreamSessionStartErrorMessage(error);
  }
  if (isBridgeTransportError(error)) {
    return getBridgeAwareSessionMessage(
      error.code,
      "Monitoring could not be started.",
      "Check the selected source and try again.",
    );
  }

  return "Monitoring could not be started. Check the selected source and try again.";
}

export function getSessionStopErrorMessage(error?: unknown): string {
  if (isBridgeTransportError(error)) {
    return getBridgeAwareSessionMessage(
      error.code,
      "Monitoring could not be ended cleanly.",
      "Try ending the session again.",
    );
  }

  return "Monitoring could not be ended cleanly. Try ending the session again.";
}

export function getPlaybackErrorMessage(
  reason:
    | "unavailable"
    | "localVideoOpen"
    | "remoteVideoOpen"
    | "hlsOpen"
    | "hlsMissingManifest"
    | "hlsBlocked"
    | "hlsInvalidManifest"
    | "hlsUnsupported",
): string {
  switch (reason) {
    case "hlsMissingManifest":
      return "The selected HLS playlist could not be found for playback.";
    case "hlsBlocked":
      return "The selected HLS stream blocked playback access.";
    case "hlsInvalidManifest":
      return "The selected HLS source did not return a valid playlist.";
    case "localVideoOpen":
      return "The selected local video could not be opened for playback.";
    case "remoteVideoOpen":
      return "The selected remote media file could not be opened for playback.";
    case "hlsOpen":
      return "The selected HLS stream could not be opened for playback.";
    case "hlsUnsupported":
      return "This environment does not support HLS playback.";
    case "unavailable":
    default:
      return "Playback unavailable";
  }
}

export function getHlsPlaybackErrorMessage(args: {
  details?: string | null;
  responseCode?: number | null;
  responseText?: string | null;
}): string {
  const details = args.details ?? "";
  const responseCode = args.responseCode ?? null;
  const responseText = (args.responseText ?? "").toLowerCase();

  if (responseCode === 401 || responseCode === 403) {
    return getPlaybackErrorMessage("hlsBlocked");
  }
  if (responseCode === 404 || details === "manifestLoadError") {
    return getPlaybackErrorMessage("hlsMissingManifest");
  }
  if (
    details === "manifestParsingError"
    || responseText.includes("instead of a playlist")
    || responseText.includes("invalid playlist")
  ) {
    return getPlaybackErrorMessage("hlsInvalidManifest");
  }
  return getPlaybackErrorMessage("hlsOpen");
}

export function getPlaybackLoadingMessage(sourceKind: MonitorSource["kind"]): string {
  return sourceKind === "video_segments"
    ? "The player is loading the local playlist."
    : "The player is loading the selected media source.";
}

export function getPlaybackUnavailableDescription(): string {
  return "The current local source could not be prepared for playback.";
}

export function getApiStreamOperatorMessage(
  reason:
    | "streamUnavailable"
    | "reconnecting"
    | "reconnectBudgetExhausted"
    | "safetyLimitReached"
    | "directMediaRequired"
    | "unsupportedSource",
): string {
  switch (reason) {
    case "directMediaRequired":
      return "This looks like a webpage URL, not a direct media stream. Paste a direct .m3u8 or .mp4 URL instead.";
    case "reconnecting":
      return "The live stream is temporarily unavailable. Monitoring is reconnecting.";
    case "reconnectBudgetExhausted":
      return "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted.";
    case "safetyLimitReached":
      return "The live stream monitoring run stopped after hitting a runtime safety limit.";
    case "unsupportedSource":
      return "The selected live stream source is not supported by the current monitoring runtime.";
    case "streamUnavailable":
    default:
      return "The selected live stream is unavailable right now.";
  }
}

export function getApiStreamSessionStateMessage(args: {
  status?: SessionStatus | null;
  statusReason?: string | null;
  statusDetail?: string | null;
}): string | null {
  const status = args.status ?? null;
  if (status !== "failed") {
    return null;
  }

  return getApiStreamOperatorMessage(
    classifyApiStreamOperatorReason(args.statusDetail ?? "", args.statusReason ?? null),
  );
}

function getApiStreamSessionStartErrorMessage(error?: unknown): string {
  if (!(error instanceof BridgeTransportError)) {
    return "Monitoring could not be started. Check the selected live stream and try again.";
  }

  const normalizedDetails = `${error.message} ${error.details ?? ""}`.toLowerCase();
  if (normalizedDetails.includes("reconnecting") || normalizedDetails.includes("retryable")) {
    return getApiStreamOperatorMessage("reconnecting");
  }
  return getApiStreamOperatorMessage(
    classifyApiStreamOperatorReason(normalizedDetails),
  );
}

function classifyApiStreamOperatorReason(
  details: string,
  statusReason?: string | null,
):
  | "streamUnavailable"
  | "reconnectBudgetExhausted"
  | "safetyLimitReached"
  | "directMediaRequired"
  | "unsupportedSource" {
  const normalizedDetails = details.toLowerCase();
  if (
    normalizedDetails.includes("reconnect budget exhausted")
    || normalizedDetails.includes("retry budget")
  ) {
    return "reconnectBudgetExhausted";
  }
  if (
    normalizedDetails.includes("session runtime exceeded")
    || normalizedDetails.includes("playlist refresh limit exceeded")
    || normalizedDetails.includes("temp storage exceeded")
    || normalizedDetails.includes("fetch exceeded max byte budget")
  ) {
    return "safetyLimitReached";
  }
  if (
    normalizedDetails.includes("direct .m3u8 or .mp4")
    || normalizedDetails.includes("webpage url")
    || normalizedDetails.includes("webpage")
  ) {
    return "directMediaRequired";
  }
  if (
    normalizedDetails.includes("unsupported")
    || normalizedDetails.includes("not supported")
    || normalizedDetails.includes("master playlist")
    || normalizedDetails.includes("playlist type")
    || normalizedDetails.includes("scheme")
  ) {
    return "unsupportedSource";
  }
  if (
    normalizedDetails.includes("unavailable")
    || normalizedDetails.includes("unreachable")
    || normalizedDetails.includes("timeout")
    || normalizedDetails.includes("timed out")
    || normalizedDetails.includes("connection")
    || normalizedDetails.includes("refused")
    || normalizedDetails.includes("dns")
    || normalizedDetails.includes("upstream returned http")
    || statusReason === "terminal_failure"
  ) {
    return "streamUnavailable";
  }
  return "streamUnavailable";
}

function getBridgeAwareSessionMessage(
  code: BridgeErrorCode,
  fallbackPrefix: string,
  fallbackSuffix: string,
): string {
  switch (code) {
    case "INVALID_BRIDGE_RESPONSE":
      return `${fallbackPrefix} The local bridge returned an invalid response.`;
    case "SESSION_START_FAILED":
    case "SESSION_CANCEL_FAILED":
    case "SESSION_READ_FAILED":
      return `${fallbackPrefix} The local monitoring bridge reported a request failure.`;
    default:
      return `${fallbackPrefix} ${fallbackSuffix}`;
  }
}
