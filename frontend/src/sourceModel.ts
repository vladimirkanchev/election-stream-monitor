import type { InputMode, MonitorSource, MonitorSourceAccess } from "./types";

const API_STREAM_PROTOCOLS = new Set(["http:", "https:"]);
const API_STREAM_DIRECT_SUFFIXES = [".m3u8", ".mp4"];

export function createMonitorSource(kind: InputMode, path: string | null | undefined): MonitorSource {
  return {
    kind,
    path: normalizeSourcePath(path),
    access: inferMonitorSourceAccess(path),
  };
}

export function updateMonitorSourcePath(
  source: MonitorSource,
  path: string | null | undefined,
): MonitorSource {
  return {
    ...source,
    path: normalizeSourcePath(path),
    access: inferMonitorSourceAccess(path),
  };
}

export function inferMonitorSourceAccess(path: string | null | undefined): MonitorSourceAccess {
  if (isSupportedApiStreamPath(path)) {
    return "api_stream";
  }
  return "local_path";
}

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
