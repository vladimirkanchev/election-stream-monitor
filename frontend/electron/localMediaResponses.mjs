import { access, readFile, stat } from "node:fs/promises";
import { constants as fsConstants, createReadStream } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import {
  createRemotePlaybackRequestHeaders,
  parseRemoteHlsProxyPayload,
} from "./hlsProxy.mjs";
import { resolveRemoteHlsProxyTarget } from "./localMediaRequestPolicy.mjs";

/**
 * Response builders for the privileged `local-media://` protocol.
 *
 * `main.mjs` wires this module into Electron protocol registration, while this
 * module owns the concrete file-serving and remote-HLS-proxy response logic.
 *
 * It keeps three concerns together because they share one protocol surface:
 *
 * - local file existence/read checks
 * - range-aware binary media responses
 * - remote HLS proxy response shaping after upstream fetch/parsing
 */

const CONTENT_TYPES = {
  ".mp4": "video/mp4",
  ".m3u8": "application/vnd.apple.mpegurl",
  ".ts": "video/mp2t",
};

export function createLocalMediaResponseHandlers({
  remoteHlsProxyRegistry,
  log = console,
  fetchImpl = fetch,
  accessImpl = access,
  readFileImpl = readFile,
  statImpl = stat,
  createReadStreamImpl = createReadStream,
}) {
  async function handleRemoteHlsProxyRequest(request, requestUrl) {
    const resolvedTarget = resolveRemoteHlsProxyTarget(requestUrl, remoteHlsProxyRegistry);
    if (resolvedTarget.kind === "error") {
      return resolvedTarget.response;
    }
    const { targetUrl } = resolvedTarget;

    log.info("[remote-hls-proxy]", request.method, targetUrl);

    try {
      const remoteResponse = await fetchImpl(targetUrl, {
        method: "GET",
        headers: createRemotePlaybackRequestHeaders(request.headers.get("range")),
      });
      const proxyPayload = await parseRemoteHlsProxyPayload({
        targetUrl,
        remoteResponse,
        registerProxyUrl: (assetUrl) => remoteHlsProxyRegistry.register(assetUrl),
        guessContentType,
      });
      log.info("[remote-hls-proxy] upstream response", JSON.stringify(
        summarizeProxyPayload(targetUrl, proxyPayload),
      ));

      return buildRemoteProxyResponse({
        remoteResponse,
        proxyPayload,
        targetUrl,
        log,
      });
    } catch (error) {
      log.error("[remote-hls-proxy] failed", targetUrl, error);
      return buildTextResponse("Failed to proxy remote HLS asset", 502);
    }
  }

  async function handleLocalMediaRequest(request, filePath) {
    log.info("[local-media]", request.method, filePath);

    try {
      await accessImpl(filePath, fsConstants.R_OK);
    } catch {
      log.error("[local-media] missing file", filePath);
      return buildTextResponse("Media file not found", 404);
    }

    const extension = path.extname(filePath).toLowerCase();
    if (extension === ".m3u8") {
      return buildPlaylistResponse(
        await readFileImpl(filePath, "utf-8"),
        guessContentType(filePath),
      );
    }
    return buildLocalBinaryMediaResponse({
      filePath,
      request,
      extension,
      statImpl,
      createReadStreamImpl,
    });
  }

  return {
    handleRemoteHlsProxyRequest,
    handleLocalMediaRequest,
  };
}

export async function buildLocalBinaryMediaResponse({
  filePath,
  request,
  extension,
  statImpl = stat,
  createReadStreamImpl = createReadStream,
}) {
  const statResult = await statImpl(filePath);
  const totalSize = statResult.size;
  const range = parseLocalMediaRangeRequest({
    rangeHeader: request.headers.get("range"),
    totalSize,
    allowPartialResponse: extension === ".mp4",
  });

  if (range.kind === "invalid") {
    return buildRangeNotSatisfiableResponse(totalSize);
  }

  const headers = buildLocalBinaryMediaHeaders({
    filePath,
    range,
    totalSize,
  });

  const stream = createReadStreamImpl(filePath, {
    start: range.start,
    end: range.end,
  });
  return new Response(Readable.toWeb(stream), {
    status: range.status,
    headers,
  });
}

export function parseLocalMediaRangeRequest({
  rangeHeader,
  totalSize,
  allowPartialResponse,
}) {
  let start = 0;
  let end = totalSize > 0 ? totalSize - 1 : 0;
  let status = 200;

  if (allowPartialResponse && rangeHeader) {
    const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
    if (match) {
      if (match[1]) {
        start = Number.parseInt(match[1], 10);
      }
      if (match[2]) {
        end = Number.parseInt(match[2], 10);
      }
      if (!match[2] && totalSize > 0) {
        end = totalSize - 1;
      }
      status = 206;
    }
  }

  if (start > end || start >= totalSize) {
    return { kind: "invalid" };
  }

  return {
    kind: "ok",
    start,
    end,
    status,
  };
}

export function buildPlaylistResponse(playlistBody, contentType, status = 200) {
  return new Response(playlistBody, { status, headers: buildPlaylistHeaders(contentType) });
}

export function buildProxyAssetResponse(remoteResponse, proxyPayload) {
  return new Response(remoteResponse.body, {
    status: proxyPayload.status,
    headers: proxyPayload.headers,
  });
}

export function guessContentType(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  return CONTENT_TYPES[extension] ?? "application/octet-stream";
}

function summarizeProxyPayload(targetUrl, proxyPayload) {
  return {
    targetUrl,
    status: proxyPayload.status,
    contentType: proxyPayload.contentType,
  };
}

function buildRemoteProxyResponse({
  remoteResponse,
  proxyPayload,
  targetUrl,
  log,
}) {
  if (proxyPayload.kind === "playlist") {
    return buildPlaylistResponse(
      proxyPayload.bodyText,
      proxyPayload.contentType,
      proxyPayload.status,
    );
  }

  if (proxyPayload.kind === "error") {
    if (proxyPayload.preview) {
      log.error(
        "[remote-hls-proxy] upstream error preview",
        JSON.stringify({
          targetUrl,
          status: proxyPayload.status,
          preview: proxyPayload.preview,
        }),
      );
    }
    return buildTextResponse(proxyPayload.message, proxyPayload.status);
  }

  if (proxyPayload.kind === "invalid_playlist") {
    log.error(
      "[remote-hls-proxy] invalid playlist response",
      JSON.stringify({
        targetUrl,
        contentType: proxyPayload.contentType,
        upstreamKind: proxyPayload.upstreamKind,
        preview: proxyPayload.preview,
      }),
    );
    return buildTextResponse(proxyPayload.message, proxyPayload.status);
  }

  return buildProxyAssetResponse(remoteResponse, proxyPayload);
}

function buildTextResponse(message, status) {
  return new Response(message, { status });
}

function buildRangeNotSatisfiableResponse(totalSize) {
  return new Response("Requested range not satisfiable", {
    status: 416,
    headers: {
      "content-range": `bytes */${totalSize}`,
    },
  });
}

function buildLocalBinaryMediaHeaders({ filePath, range, totalSize }) {
  const headers = new Headers({
    "accept-ranges": "bytes",
    "cache-control": "no-store",
    "content-type": guessContentType(filePath),
    "content-length": String(range.end - range.start + 1),
  });
  if (range.status === 206) {
    headers.set("content-range", `bytes ${range.start}-${range.end}/${totalSize}`);
  }
  return headers;
}

function buildPlaylistHeaders(contentType) {
  return {
    "cache-control": "no-store",
    "content-type": contentType,
  };
}
