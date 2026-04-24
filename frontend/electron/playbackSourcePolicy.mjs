import { pathToFileURL } from "node:url";

/**
 * Renderer-facing playback URL policy for the Electron bridge.
 *
 * The backend remains the source of truth for which sources are valid; this
 * module only adapts already-resolved playback sources into renderer-safe URLs.
 *
 * In practice that means:
 *
 * - direct remote MP4/HLS URLs may stay remote
 * - remote HLS manifests may be rewritten into opaque local proxy URLs
 * - local file paths are always mapped into `local-media://`
 */

export function isAllowedRemotePlaybackSource(source) {
  return source.startsWith("http://") || source.startsWith("https://");
}

export function toRendererMediaUrl(
  source,
  {
    isRemoteHlsUrl,
    registerRemoteHlsProxyUrl,
    pathToFileUrl = pathToFileURL,
  },
) {
  if (!source) {
    return null;
  }

  if (isAllowedRemotePlaybackSource(source)) {
    if (isRemoteHlsUrl(source)) {
      return registerRemoteHlsProxyUrl(source);
    }
    return source;
  }

  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(source)) {
    throw new Error("Unsupported playback source scheme returned by backend");
  }

  const fileUrl = pathToFileUrl(source);
  return `local-media://media${fileUrl.pathname}`;
}
