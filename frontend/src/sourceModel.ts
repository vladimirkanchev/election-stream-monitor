import type { InputMode, MonitorSource, MonitorSourceAccess } from "./types";

const API_STREAM_PROTOCOLS = new Set(["http:", "https:"]);
const API_STREAM_DIRECT_SUFFIXES = [".m3u8", ".mp4"];

/**
 * Build one normalized monitor source for the selected mode.
 *
 * The selected mode stays authoritative for access semantics: local modes keep
 * `local_path`, while `api_stream` only becomes remote access when the path is
 * a supported direct stream URL.
 */
export function createMonitorSource(kind: InputMode, path: string | null | undefined): MonitorSource {
  return buildMonitorSource(kind, path);
}

/** Rebuild a source after the path changes while keeping the current mode. */
export function updateMonitorSourcePath(
  source: MonitorSource,
  path: string | null | undefined,
): MonitorSource {
  return buildMonitorSource(source.kind, path);
}

/** Rebuild a source after the mode changes while keeping the current path. */
export function updateMonitorSourceKind(source: MonitorSource, kind: InputMode): MonitorSource {
  return buildMonitorSource(kind, source.path);
}

/** Infer source access from the selected mode plus the normalized source path. */
export function inferMonitorSourceAccess(
  kind: InputMode,
  path: string | null | undefined,
): MonitorSourceAccess {
  if (kind === "api_stream" && isSupportedApiStreamPath(path)) {
    return "api_stream";
  }
  return "local_path";
}

/** Return whether a path matches the current direct `api_stream` URL contract. */
export function isSupportedApiStreamPath(path: string | null | undefined): boolean {
  const normalizedPath = normalizeSourcePath(path);
  if (!normalizedPath) {
    return false;
  }

  try {
    const parsed = new URL(normalizedPath);
    return (
      API_STREAM_PROTOCOLS.has(parsed.protocol)
      && parsed.hostname.length > 0
      && API_STREAM_DIRECT_SUFFIXES.some((suffix) => parsed.pathname.toLowerCase().endsWith(suffix))
    );
  } catch {
    return false;
  }
}

function normalizeSourcePath(path: string | null | undefined): string {
  return typeof path === "string" ? path.trim() : "";
}

function buildMonitorSource(kind: InputMode, path: string | null | undefined): MonitorSource {
  const normalizedPath = normalizeSourcePath(path);
  return {
    kind,
    path: normalizedPath,
    access: inferMonitorSourceAccess(kind, normalizedPath),
  };
}
