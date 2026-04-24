/**
 * Focused tests for opaque remote-HLS proxy token and manifest rewrite logic.
 *
 * This file complements:
 *
 * - `playbackSourcePolicy.test.mjs` for renderer URL adaptation
 * - `localMediaRequestPolicy.test.mjs` for protocol routing
 * - `localMediaResponses.test.mjs` for concrete protocol response helpers
 */

import { createServer } from "node:http";

import { describe, expect, it } from "vitest";

import {
  buildProxyMediaUrl,
  createRemotePlaybackRequestHeaders,
  createRemoteHlsProxyRegistry,
  isRemoteHlsUrl,
  looksLikeHlsManifest,
  looksLikeHtmlDocument,
  parseRemoteHlsProxyPayload,
  parseProxyToken,
  rewriteHlsManifest,
  shouldTreatAsHlsPlaylist,
} from "./hlsProxy.mjs";

function playlistResponse(lines, contentType = "application/vnd.apple.mpegurl") {
  return [200, lines.join("\n"), contentType];
}

function assetResponse(
  body,
  contentType = "video/mp2t",
  status = 200,
  headers = {},
) {
  return [status, body, contentType, headers];
}

function expectProxyPath(proxyUrl) {
  expect(proxyUrl).toContain("local-media://proxy/");
}

describe("electron HLS proxy helpers", () => {
  it("detects direct remote HLS URLs", () => {
    expect(isRemoteHlsUrl("https://cdn.example.com/live/playlist.m3u8")).toBe(true);
    expect(isRemoteHlsUrl("https://video-platform.example/live/channel")).toBe(false);
    expect(isRemoteHlsUrl("https://cdn.example.com/archive/video.mp4")).toBe(false);
  });

  it("registers and resolves opaque proxy tokens", () => {
    const registry = createRemoteHlsProxyRegistry();
    const proxiedUrl = registry.register("https://cdn.example.com/live/playlist.m3u8");
    const token = parseProxyToken(new URL(proxiedUrl).pathname);

    expect(token).toBeTruthy();
    expect(registry.resolve(token)).toBe("https://cdn.example.com/live/playlist.m3u8");
  });

  it("returns null for unknown proxy tokens", () => {
    const registry = createRemoteHlsProxyRegistry();

    expect(registry.resolve("missing-token")).toBeNull();
  });

  it("returns null when a proxy pathname does not include a token", () => {
    expect(parseProxyToken("/")).toBeNull();
  });

  it("drops expired proxy entries during registry pruning", async () => {
    const registry = createRemoteHlsProxyRegistry({ maxAgeMs: 1 });
    const proxiedUrl = registry.register("https://cdn.example.com/live/playlist.m3u8");
    const token = parseProxyToken(new URL(proxiedUrl).pathname);

    await new Promise((resolve) => setTimeout(resolve, 10));
    registry.prune();

    expect(registry.resolve(token)).toBeNull();
  });

  it("rewrites media-playlist segment and key URLs to local proxy URLs", () => {
    const rewritten = rewriteHlsManifest(
      [
        "#EXTM3U",
        '#EXT-X-KEY:METHOD=AES-128,URI="key.key"',
        "#EXTINF:6.0,",
        "segment_0001.ts",
      ].join("\n"),
      "https://cdn.example.com/live/index.m3u8",
      (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
    );

    expect(rewritten).toContain('URI="local-media://proxy/token-key.key.bin"');
    expect(rewritten).toContain("local-media://proxy/token-segment_0001.ts.bin");
  });

  it("rewrites uri attributes and query-string assets without losing playlist structure", () => {
    const seenAssetUrls = [];
    const rewritten = rewriteHlsManifest(
      [
        "#EXTM3U",
        '#EXT-X-MAP:URI="../init.mp4?token=abc"',
        '#EXT-X-KEY:METHOD=AES-128,URI="https://keys.example.com/live/key.bin?sig=1"',
        "#EXTINF:4.0,",
        "segment_0001.ts?token=seg-1",
        "#EXT-X-ENDLIST",
      ].join("\n"),
      "https://cdn.example.com/live/variant/index.m3u8?session=1",
      (assetUrl) => {
        seenAssetUrls.push(assetUrl);
        return buildProxyMediaUrl(`token-${seenAssetUrls.length}`, ".bin");
      },
    );

    expect(seenAssetUrls).toEqual([
      "https://cdn.example.com/live/init.mp4?token=abc",
      "https://keys.example.com/live/key.bin?sig=1",
      "https://cdn.example.com/live/variant/segment_0001.ts?token=seg-1",
    ]);
    expect(rewritten).toContain('URI="local-media://proxy/token-1.bin"');
    expect(rewritten).toContain('URI="local-media://proxy/token-2.bin"');
    expect(rewritten).toContain("local-media://proxy/token-3.bin");
    expect(rewritten).toContain("#EXT-X-ENDLIST");
  });

  it("rewrites master-playlist variant URLs to local proxy URLs", () => {
    const rewritten = rewriteHlsManifest(
      [
        "#EXTM3U",
        "#EXT-X-STREAM-INF:BANDWIDTH=1280000",
        "variant/low.m3u8",
      ].join("\n"),
      "https://cdn.example.com/master/index.m3u8",
      (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
    );

    expect(rewritten).toContain("local-media://proxy/token-low.m3u8.bin");
  });

  it("detects HLS manifest bodies", () => {
    expect(looksLikeHlsManifest("#EXTM3U\n#EXTINF:6.0,\nsegment.ts")).toBe(true);
    expect(looksLikeHlsManifest("<html>challenge</html>")).toBe(false);
  });

  it("treats both m3u8 urls and HLS content types as playlist responses", () => {
    expect(
      shouldTreatAsHlsPlaylist(
        "https://cdn.example.com/live/playlist.m3u8",
        "application/octet-stream",
      ),
    ).toBe(true);
    expect(
      shouldTreatAsHlsPlaylist(
        "https://cdn.example.com/live/playlist",
        "audio/mpegurl",
      ),
    ).toBe(true);
    expect(
      shouldTreatAsHlsPlaylist(
        "https://cdn.example.com/archive/recording.mp4",
        "video/mp4",
      ),
    ).toBe(false);
  });

  it("detects HTML challenge/error pages", () => {
    expect(looksLikeHtmlDocument("<!DOCTYPE html><html></html>")).toBe(true);
    expect(looksLikeHtmlDocument("#EXTM3U\n#EXTINF:6.0,\nsegment.ts")).toBe(false);
  });

  it("proxies a master playlist through to variant and segment assets end-to-end", async () => {
    const routes = {
      "/master.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXT-X-STREAM-INF:BANDWIDTH=1280000",
          "variant/low.m3u8",
        ]),
      "/variant/low.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXTINF:6.0,",
          "segment_0001.ts",
          '#EXT-X-KEY:METHOD=AES-128,URI="enc.key"',
        ]),
      "/variant/segment_0001.ts": assetResponse("segment-body"),
      "/variant/enc.key": assetResponse("secret", "application/octet-stream"),
    };

    await withLocalHttpRoutes(routes, async (baseUrl) => {
      const registry = createRemoteHlsProxyRegistry();
      const masterProxyUrl = registry.register(`${baseUrl}/master.m3u8`);

      const masterPayload = await fetchProxiedAsset(masterProxyUrl, registry);
      expect(masterPayload.kind).toBe("playlist");
      const variantProxyUrl = firstProxiedUrl(masterPayload.bodyText);
      expect(variantProxyUrl).toContain("local-media://proxy/");

      const variantPayload = await fetchProxiedAsset(variantProxyUrl, registry);
      expect(variantPayload.kind).toBe("playlist");
      const proxiedUrls = extractProxiedUrls(variantPayload.bodyText);
      expect(proxiedUrls).toHaveLength(2);

      const segmentPayload = await fetchProxiedAsset(proxiedUrls[0], registry);
      expect(segmentPayload.kind).toBe("asset");
      expect(segmentPayload.status).toBe(200);
      expect(segmentPayload.contentType).toBe("video/mp2t");

      const keyPayload = await fetchProxiedAsset(proxiedUrls[1], registry);
      expect(keyPayload.kind).toBe("asset");
      expect(keyPayload.status).toBe(200);
      expect(keyPayload.contentType).toBe("application/octet-stream");
    });
  });

  it("rewrites redirected playlists against the final upstream url", async () => {
    const server = createServer((request, response) => {
      if (request.url === "/redirect/master.m3u8") {
        response.writeHead(302, { location: "/canonical/master.m3u8" });
        response.end();
        return;
      }
      if (request.url === "/canonical/master.m3u8") {
        const body = ["#EXTM3U", "#EXTINF:6.0,", "segment_0001.ts"].join("\n");
        response.writeHead(200, {
          "content-type": "application/vnd.apple.mpegurl",
          "content-length": Buffer.byteLength(body),
        });
        response.end(body);
        return;
      }
      if (request.url === "/canonical/segment_0001.ts") {
        response.writeHead(200, {
          "content-type": "video/mp2t",
          "content-length": "12",
        });
        response.end("segment-body");
        return;
      }
      response.writeHead(404, { "content-type": "text/plain" });
      response.end("not found");
    });

    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    try {
      const { port } = server.address();
      const baseUrl = `http://127.0.0.1:${port}`;
      const registry = createRemoteHlsProxyRegistry();
      const masterPayload = await fetchProxiedAsset(
        registry.register(`${baseUrl}/redirect/master.m3u8`),
        registry,
      );

      expect(masterPayload.kind).toBe("playlist");
      const segmentPayload = await fetchProxiedAsset(firstProxiedUrl(masterPayload.bodyText), registry);
      expect(segmentPayload.kind).toBe("asset");
      expect(segmentPayload.status).toBe(200);
      expect(segmentPayload.contentType).toBe("video/mp2t");
    } finally {
      await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
    }
  });

  it("supports parallel reads against the same proxied playlist and segment", async () => {
    const routes = {
      "/index.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXTINF:6.0,",
          "segment_0001.ts",
        ]),
      "/segment_0001.ts": assetResponse("segment-body"),
    };

    await withLocalHttpRoutes(routes, async (baseUrl) => {
      const registry = createRemoteHlsProxyRegistry();
      const playlistProxyUrl = registry.register(`${baseUrl}/index.m3u8`);

      const [playlistA, playlistB] = await Promise.all([
        fetchProxiedAsset(playlistProxyUrl, registry),
        fetchProxiedAsset(playlistProxyUrl, registry),
      ]);
      expect(playlistA.kind).toBe("playlist");
      expect(playlistB.kind).toBe("playlist");

      const segmentProxyUrl = firstProxiedUrl(playlistA.bodyText);
      const [segmentA, segmentB] = await Promise.all([
        fetchProxiedAsset(segmentProxyUrl, registry),
        fetchProxiedAsset(segmentProxyUrl, registry),
      ]);
      expect(segmentA.kind).toBe("asset");
      expect(segmentB.kind).toBe("asset");
      expect(segmentA.status).toBe(200);
      expect(segmentB.status).toBe(200);
    });
  });

  it("surfaces missing variant playlists as clean proxy errors", async () => {
    const routes = {
      "/master.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXT-X-STREAM-INF:BANDWIDTH=1280000",
          "variant/missing.m3u8",
        ]),
      "/variant/missing.m3u8": assetResponse("not found", "text/plain", 404),
    };

    await withLocalHttpRoutes(routes, async (baseUrl) => {
      const registry = createRemoteHlsProxyRegistry();
      const masterPayload = await fetchProxiedAsset(
        registry.register(`${baseUrl}/master.m3u8`),
        registry,
      );
      expect(masterPayload.kind).toBe("playlist");

      const variantPayload = await fetchProxiedAsset(firstProxiedUrl(masterPayload.bodyText), registry);
      expect(variantPayload.kind).toBe("error");
      expect(variantPayload.status).toBe(404);
      expect(variantPayload.message).toContain("HTTP 404");
    });
  });

  it("surfaces missing media segments as clean proxy errors", async () => {
    const routes = {
      "/index.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXTINF:6.0,",
          "segment_missing.ts",
        ]),
      "/segment_missing.ts": assetResponse("not found", "text/plain", 404),
    };

    await withLocalHttpRoutes(routes, async (baseUrl) => {
      const registry = createRemoteHlsProxyRegistry();
      const playlistPayload = await fetchProxiedAsset(
        registry.register(`${baseUrl}/index.m3u8`),
        registry,
      );
      expect(playlistPayload.kind).toBe("playlist");

      const segmentPayload = await fetchProxiedAsset(firstProxiedUrl(playlistPayload.bodyText), registry);
      expect(segmentPayload.kind).toBe("error");
      expect(segmentPayload.status).toBe(404);
      expect(segmentPayload.message).toContain("HTTP 404");
    });
  });

  it("surfaces blocked upstream playlists cleanly", async () => {
    const blockedResponse = new Response("forbidden", {
      status: 403,
      headers: { "content-type": "text/plain" },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live.m3u8",
      remoteResponse: blockedResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "application/vnd.apple.mpegurl",
    });

    expect(payload.kind).toBe("error");
    expect(payload.status).toBe(403);
    expect(payload.message).toContain("HTTP 403");
  });

  it("surfaces html responses in place of playlists cleanly", async () => {
    const htmlResponse = new Response("<!DOCTYPE html><html>challenge</html>", {
      status: 200,
      headers: { "content-type": "text/html; charset=UTF-8" },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live.m3u8",
      remoteResponse: htmlResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "application/vnd.apple.mpegurl",
    });

    expect(payload.kind).toBe("invalid_playlist");
    expect(payload.status).toBe(502);
    expect(payload.upstreamKind).toBe("html");
    expect(payload.message).toContain("instead of a playlist");
  });

  it("preserves byte-range headers when proxying media assets", async () => {
    const assetResponse = new Response("partial-segment", {
      status: 206,
      headers: {
        "content-type": "video/mp2t",
        "content-length": "14",
        "accept-ranges": "bytes",
        "content-range": "bytes 0-13/100",
      },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live/segment.ts",
      remoteResponse: assetResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "video/mp2t",
    });

    expect(payload.kind).toBe("asset");
    expect(payload.status).toBe(206);
    expect(payload.headers.get("content-type")).toBe("video/mp2t");
    expect(payload.headers.get("accept-ranges")).toBe("bytes");
    expect(payload.headers.get("content-range")).toBe("bytes 0-13/100");
    expect(payload.headers.get("content-length")).toBe("14");
  });

  it("preserves query strings when rewriting proxied playlist assets", () => {
    const seenAssetUrls = [];
    const rewritten = rewriteHlsManifest(
      [
        "#EXTM3U",
        '#EXT-X-KEY:METHOD=AES-128,URI="enc.key?token=abc"',
        "#EXTINF:6.0,",
        "segment_0001.ts?token=seg-1&part=2",
      ].join("\n"),
      "https://cdn.example.com/live/index.m3u8?session=1",
      (assetUrl) => {
        seenAssetUrls.push(assetUrl);
        return buildProxyMediaUrl(`token-${seenAssetUrls.length}`, ".bin");
      },
    );

    expect(seenAssetUrls).toEqual([
      "https://cdn.example.com/live/enc.key?token=abc",
      "https://cdn.example.com/live/segment_0001.ts?token=seg-1&part=2",
    ]);
    expect(rewritten).toContain('URI="local-media://proxy/token-1.bin"');
    expect(rewritten).toContain("local-media://proxy/token-2.bin");
  });

  it("keeps non-hls remote urls out of the proxy path", () => {
    expect(isRemoteHlsUrl("local-media://proxy/token-segment.ts.bin")).toBe(false);
    expect(isRemoteHlsUrl("file:///tmp/local.m3u8")).toBe(false);
    expect(isRemoteHlsUrl("not-a-url")).toBe(false);
  });

  it("surfaces upstream 503 responses as clean proxy errors", async () => {
    const blockedResponse = new Response("temporary outage", {
      status: 503,
      headers: { "content-type": "text/plain" },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live.m3u8",
      remoteResponse: blockedResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "application/vnd.apple.mpegurl",
    });

    expect(payload.kind).toBe("error");
    expect(payload.status).toBe(503);
    expect(payload.message).toContain("HTTP 503");
  });

  it("does not forward cache-control policy when proxying passthrough media assets", async () => {
    const assetResponse = new Response("segment-body", {
      status: 200,
      headers: {
        "content-type": "video/mp2t",
        "content-length": "12",
        "cache-control": "public, max-age=600",
        "pragma": "cache",
      },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live/segment.ts",
      remoteResponse: assetResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "video/mp2t",
    });

    expect(payload.kind).toBe("asset");
    expect(payload.headers.get("cache-control")).toBe("no-store");
    expect(payload.headers.get("pragma")).toBeNull();
  });

  it("does not leak upstream set-cookie headers through passthrough asset responses", async () => {
    const assetResponse = new Response("segment-body", {
      status: 200,
      headers: {
        "content-type": "video/mp2t",
        "content-length": "12",
        "set-cookie": "session=upstream-secret; HttpOnly",
      },
    });
    const payload = await parseRemoteHlsProxyPayload({
      targetUrl: "https://streams.example.com/live/segment.ts",
      remoteResponse: assetResponse,
      registerProxyUrl: (assetUrl) => buildProxyMediaUrl(`token-${assetUrl.split("/").pop()}`),
      guessContentType: () => "video/mp2t",
    });

    expect(payload.kind).toBe("asset");
    expect(payload.headers.get("set-cookie")).toBeNull();
  });

  it("forwards range headers when creating remote playback requests", () => {
    const headers = createRemotePlaybackRequestHeaders("bytes=0-99");

    expect(headers.get("range")).toBe("bytes=0-99");
    expect(headers.get("accept")).toContain("application/vnd.apple.mpegurl");
  });

  it("does not forward renderer auth or cookie headers when proxying upstream asset requests", async () => {
    const seenHeaders = [];
    const routes = {
      "/index.m3u8": playlistResponse([
          "#EXTM3U",
          "#EXTINF:6.0,",
          "segment_0001.ts",
        ]),
      "/segment_0001.ts": [
        200,
        "segment-body",
        "video/mp2t",
        {},
        (request) => {
          seenHeaders.push({
            authorization: request.headers.authorization ?? null,
            cookie: request.headers.cookie ?? null,
          });
        },
      ],
    };

    await withLocalHttpRoutes(routes, async (baseUrl) => {
      const registry = createRemoteHlsProxyRegistry();
      const playlistPayload = await fetchProxiedAsset(
        registry.register(`${baseUrl}/index.m3u8`),
        registry,
      );
      expect(playlistPayload.kind).toBe("playlist");

      const segmentPayload = await fetchProxiedAsset(firstProxiedUrl(playlistPayload.bodyText), registry);
      expect(segmentPayload.kind).toBe("asset");
    });

    expect(seenHeaders).toEqual([
      {
        authorization: null,
        cookie: null,
      },
    ]);
  });
});

function extractProxiedUrls(text) {
  return text.match(/local-media:\/\/proxy\/[^\s"]+/g) ?? [];
}

function firstProxiedUrl(text) {
  const match = extractProxiedUrls(text)[0];
  expect(match).toBeTruthy();
  return match;
}

async function fetchProxiedAsset(proxyUrl, registry) {
  const proxyPath = new URL(proxyUrl).pathname;
  const token = parseProxyToken(proxyPath);
  const targetUrl = registry.resolve(token);
  expect(targetUrl).toBeTruthy();

  const remoteResponse = await fetch(targetUrl, {
    headers: createRemotePlaybackRequestHeaders(),
  });

  return parseRemoteHlsProxyPayload({
    targetUrl,
    remoteResponse,
    registerProxyUrl: (assetUrl) => registry.register(assetUrl),
    guessContentType: guessContentType,
  });
}

async function withLocalHttpRoutes(routes, callback) {
  const server = createServer((request, response) => {
    const rawRoute = routes[request.url] ?? [404, "not found", "text/plain"];
    const route = Array.isArray(rawRoute) && Array.isArray(rawRoute[0]) ? rawRoute[0] : rawRoute;
    const [status, body, contentType, extraHeaders = {}, onRequest = null] = route;
    if (onRequest) {
      onRequest(request);
    }
    response.writeHead(status, {
      "content-type": contentType,
      "content-length": Buffer.byteLength(body),
      ...extraHeaders,
    });
    response.end(body);
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const { port } = server.address();
    await callback(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  }
}

function guessContentType(targetUrl) {
  if (targetUrl.endsWith(".m3u8")) {
    return "application/vnd.apple.mpegurl";
  }
  if (targetUrl.endsWith(".ts")) {
    return "video/mp2t";
  }
  return "application/octet-stream";
}
