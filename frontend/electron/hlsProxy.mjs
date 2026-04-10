import path from "node:path";
import { randomUUID } from "node:crypto";

/**
 * Helpers for the Electron-side remote HLS playback proxy.
 *
 * The renderer cannot reliably fetch arbitrary remote HLS playlists because of
 * browser CORS restrictions. These helpers keep the proxy behavior explicit:
 *
 * - identify which playback URLs need proxying
 * - mint opaque local-media proxy URLs for playlist and segment assets
 * - rewrite playlist bodies so follow-up fetches stay inside the local scheme
 * - classify upstream responses into playlist, asset, blocked, or invalid-body
 *   outcomes before they reach the player
 */

const HLS_CONTENT_TYPES = [
  "application/vnd.apple.mpegurl",
  "application/x-mpegurl",
  "audio/mpegurl",
];

export function isRemoteHttpUrl(value) {
  return value.startsWith("http://") || value.startsWith("https://");
}

export function isRemoteHlsUrl(value) {
  if (!isRemoteHttpUrl(value)) {
    return false;
  }

  try {
    const parsed = new URL(value);
    return parsed.pathname.toLowerCase().endsWith(".m3u8");
  } catch {
    return false;
  }
}

export function createRemoteHlsProxyRegistry({
  maxEntries = 5000,
  maxAgeMs = 60 * 60 * 1000,
} = {}) {
  // The registry intentionally stores opaque token -> URL mappings instead of
  // exposing raw upstream URLs back into the renderer after the first handoff.
  const entries = new Map();

  function prune() {
    const cutoff = Date.now() - maxAgeMs;
    for (const [token, entry] of entries) {
      if (entry.createdAt < cutoff) {
        entries.delete(token);
      }
    }

    while (entries.size > maxEntries) {
      const firstToken = entries.keys().next().value;
      if (!firstToken) {
        break;
      }
      entries.delete(firstToken);
    }
  }

  function register(targetUrl) {
    prune();
    const token = randomUUID();
    const extensionHint = getExtensionHint(targetUrl);
    entries.set(token, {
      targetUrl,
      createdAt: Date.now(),
    });
    return buildProxyMediaUrl(token, extensionHint);
  }

  function resolve(token) {
    const entry = entries.get(token);
    if (!entry) {
      return null;
    }

    entry.createdAt = Date.now();
    return entry.targetUrl;
  }

  return {
    register,
    resolve,
    prune,
  };
}

export function buildProxyMediaUrl(token, extensionHint = ".bin") {
  const safeExtension = extensionHint.startsWith(".") ? extensionHint : `.${extensionHint}`;
  return `local-media://proxy/${token}${safeExtension}`;
}

export function parseProxyToken(requestPathname) {
  const basename = path.basename(requestPathname || "");
  if (!basename) {
    return null;
  }

  const extension = path.extname(basename);
  return extension ? basename.slice(0, -extension.length) : basename;
}

export function rewriteHlsManifest(playlistText, playlistUrl, registerProxyUrl) {
  // HLS playlists are tiny text documents, so whole-document rewriting keeps
  // the proxy logic simple and deterministic for both master and media lists.
  return playlistText
    .split(/\r?\n/)
    .map((line) => rewriteManifestLine(line, playlistUrl, registerProxyUrl))
    .join("\n");
}

export function looksLikeHlsManifest(bodyText) {
  return bodyText.trimStart().startsWith("#EXTM3U");
}

export function looksLikeHtmlDocument(bodyText) {
  const normalized = bodyText.trimStart().toLowerCase();
  return normalized.startsWith("<!doctype html") || normalized.startsWith("<html");
}

export function createRemotePlaybackRequestHeaders(rangeHeader = null) {
  const headers = new Headers({
    "accept": "application/vnd.apple.mpegurl, application/x-mpegURL, video/mp2t, application/octet-stream;q=0.9, */*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 election-stream-monitor/1.0",
  });
  if (rangeHeader) {
    headers.set("range", rangeHeader);
  }
  return headers;
}

export function shouldTreatAsHlsPlaylist(targetUrl, contentType) {
  // Some providers serve playlists with generic or inconsistent content types,
  // so the proxy trusts either the URL shape or a known HLS content type.
  const normalizedContentType = (contentType ?? "").toLowerCase();
  return targetUrl.toLowerCase().includes(".m3u8")
    || HLS_CONTENT_TYPES.some((candidate) => normalizedContentType.includes(candidate));
}

export async function parseRemoteHlsProxyPayload(args) {
  // This is the policy boundary for upstream responses. The Electron main
  // process later only needs to turn these classified payloads into Responses.
  const { targetUrl, remoteResponse, registerProxyUrl, guessContentType } = args;
  const effectiveTargetUrl = remoteResponse.url || targetUrl;
  const contentType = remoteResponse.headers.get("content-type") ?? guessContentType(effectiveTargetUrl);

  if (!remoteResponse.ok) {
    return buildRemoteHlsProxyErrorPayload({
      targetUrl: effectiveTargetUrl,
      status: remoteResponse.status,
      contentType,
      preview: await safeReadTextPreview(remoteResponse),
    });
  }

  if (shouldTreatAsHlsPlaylist(effectiveTargetUrl, contentType)) {
    const playlistBody = await remoteResponse.text();
    if (!looksLikeHlsManifest(playlistBody)) {
      const upstreamKind = looksLikeHtmlDocument(playlistBody) ? "html" : "non-hls";
      return buildRemoteHlsProxyInvalidPlaylistPayload({
        targetUrl: effectiveTargetUrl,
        contentType,
        upstreamKind,
        preview: previewBody(playlistBody),
      });
    }

    return {
      kind: "playlist",
      status: 200,
      contentType: "application/vnd.apple.mpegurl",
      bodyText: rewriteHlsManifest(playlistBody, effectiveTargetUrl, registerProxyUrl),
    };
  }

  return {
    kind: "asset",
    status: remoteResponse.status,
    contentType,
    headers: buildPassthroughHeaders(remoteResponse.headers, contentType),
  };
}

export function buildRemoteHlsProxyErrorPayload({
  targetUrl,
  status,
  contentType,
  preview = null,
}) {
  /** Return the canonical non-OK upstream result used by the proxy boundary. */
  return {
    kind: "error",
    status,
    contentType,
    preview,
    message: `Remote media request failed with HTTP ${status} for ${targetUrl}`,
  };
}

export function buildRemoteHlsProxyInvalidPlaylistPayload({
  targetUrl,
  contentType,
  upstreamKind,
  preview,
}) {
  /** Return the canonical invalid-playlist result used by the proxy boundary. */
  return {
    kind: "invalid_playlist",
    status: 502,
    contentType,
    upstreamKind,
    preview,
    message: `Remote HLS source returned ${upstreamKind} instead of a playlist for ${targetUrl}`,
  };
}

function rewriteManifestLine(line, playlistUrl, registerProxyUrl) {
  const trimmedLine = line.trim();
  if (!trimmedLine) {
    return line;
  }

  if (trimmedLine.startsWith("#")) {
    return rewriteManifestUriAttributes(line, playlistUrl, registerProxyUrl);
  }

  return registerProxyUrl(new URL(trimmedLine, playlistUrl).toString());
}

function rewriteManifestUriAttributes(line, playlistUrl, registerProxyUrl) {
  return line.replace(/URI="([^"]+)"/g, (_match, uriValue) => {
    const absoluteUrl = new URL(uriValue, playlistUrl).toString();
    return `URI="${registerProxyUrl(absoluteUrl)}"`;
  });
}

function getExtensionHint(targetUrl) {
  try {
    const parsed = new URL(targetUrl);
    const extension = path.extname(parsed.pathname);
    if (extension) {
      return extension;
    }
  } catch {
    // Fall through to the generic binary extension below.
  }

  return ".bin";
}

function buildPassthroughHeaders(sourceHeaders, contentType) {
  // Asset responses should preserve enough HTTP metadata for the media stack
  // to continue byte-range playback without leaking upstream cache policy.
  const headers = new Headers({
    "cache-control": "no-store",
    "content-type": contentType,
  });
  const contentLength = sourceHeaders.get("content-length");
  if (contentLength) {
    headers.set("content-length", contentLength);
  }
  const acceptRanges = sourceHeaders.get("accept-ranges");
  if (acceptRanges) {
    headers.set("accept-ranges", acceptRanges);
  }
  const contentRange = sourceHeaders.get("content-range");
  if (contentRange) {
    headers.set("content-range", contentRange);
  }
  return headers;
}

async function safeReadTextPreview(response) {
  try {
    const cloned = response.clone();
    return previewBody(await cloned.text());
  } catch {
    return null;
  }
}

function previewBody(bodyText) {
  return bodyText.replace(/\s+/g, " ").slice(0, 200);
}
