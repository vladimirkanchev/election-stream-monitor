import { describe, expect, it, vi } from "vitest";

import {
  classifyLocalMediaRequestUrl,
  createLocalMediaProtocolHandler,
  ensureAllowedLocalMediaRequestMethod,
  isAllowedLocalMediaPath,
  resolveRemoteHlsProxyTarget,
} from "./localMediaRequestPolicy.mjs";

describe("local media request policy", () => {
  it("rejects non-read methods with a narrow allowlist response", () => {
    const response = ensureAllowedLocalMediaRequestMethod("POST");

    expect(response).toBeInstanceOf(Response);
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET, HEAD");
  });

  it("returns media file paths only for the explicit media host", () => {
    expect(
      classifyLocalMediaRequestUrl(new URL("local-media://media/tmp/session/segment_0001.ts")),
    ).toEqual({
      kind: "media",
      filePath: "/tmp/session/segment_0001.ts",
    });
  });

  it("allows local-media file paths that stay under explicitly allowed roots", () => {
    expect(
      isAllowedLocalMediaPath(
        "/workspace/project/data/streams/segment_0001.ts",
        ["/workspace/project/data", "/tmp/session"],
      ),
    ).toBe(true);
  });

  it("rejects local-media file paths that fall outside the explicitly allowed roots", async () => {
    const result = classifyLocalMediaRequestUrl(
      new URL("local-media://media/etc/passwd"),
      { allowedRoots: ["/workspace/project/data", "/tmp/session"] },
    );

    expect(result.kind).toBe("error");
    expect(result.response.status).toBe(403);
    await expect(result.response.text()).resolves.toBe(
      "Local media path is outside the allowed roots",
    );
  });

  it.each([
    {
      label: "blocks unknown proxy-token requests before any upstream fetch is attempted",
      url: "local-media://proxy/token-unknown.bin",
      registry: { resolve: () => null },
    },
    {
      label: "fails closed on path-trick proxy requests with unexpected suffix structure",
      url: "local-media://proxy/token.bin/extra",
      registry: { resolve: () => null },
    },
    {
      label: "rejects proxy targets that resolve to non-http schemes before any fetch is possible",
      url: "local-media://proxy/token-unsafe.bin",
      registry: { resolve: () => "file:///etc/passwd" },
    },
  ])("$label", async ({ url, registry }) => {
    const result = resolveRemoteHlsProxyTarget(new URL(url), registry);

    expect(result.kind).toBe("error");
    expect(result.response.status).toBe(404);
    await expect(result.response.text()).resolves.toBe("Unknown proxied media target");
  });

  it("routes unknown local-media hostnames to a protocol-level 404 without touching downstream handlers", async () => {
    const handleRemoteHlsProxyRequest = vi.fn();
    const handleLocalMediaRequest = vi.fn();
    const routeLocalMediaRequest = createLocalMediaProtocolHandler({
      handleRemoteHlsProxyRequest,
      handleLocalMediaRequest,
    });

    const response = await routeLocalMediaRequest({
      method: "GET",
      url: "local-media://unexpected/tmp/video.mp4",
    });

    expect(response.status).toBe(404);
    await expect(response.text()).resolves.toBe("Unknown local media target");
    expect(handleRemoteHlsProxyRequest).not.toHaveBeenCalled();
    expect(handleLocalMediaRequest).not.toHaveBeenCalled();
  });

  it("routes malformed local-media paths to a protocol-level 400 without touching file serving", async () => {
    const handleRemoteHlsProxyRequest = vi.fn();
    const handleLocalMediaRequest = vi.fn();
    const routeLocalMediaRequest = createLocalMediaProtocolHandler({
      handleRemoteHlsProxyRequest,
      handleLocalMediaRequest,
    });

    const response = await routeLocalMediaRequest({
      method: "GET",
      url: "local-media://media/%E0%A4%A",
    });

    expect(response.status).toBe(400);
    await expect(response.text()).resolves.toBe("Malformed media path");
    expect(handleRemoteHlsProxyRequest).not.toHaveBeenCalled();
    expect(handleLocalMediaRequest).not.toHaveBeenCalled();
  });

  it("routes valid media requests to the local file handler", async () => {
    const handleRemoteHlsProxyRequest = vi.fn();
    const handleLocalMediaRequest = vi.fn().mockResolvedValue(new Response("ok", { status: 200 }));
    const routeLocalMediaRequest = createLocalMediaProtocolHandler({
      handleRemoteHlsProxyRequest,
      handleLocalMediaRequest,
    });

    const response = await routeLocalMediaRequest({
      method: "GET",
      url: "local-media://media/tmp/session/segment_0001.ts",
    });

    expect(response.status).toBe(200);
    expect(handleRemoteHlsProxyRequest).not.toHaveBeenCalled();
    expect(handleLocalMediaRequest).toHaveBeenCalledWith(
      expect.objectContaining({ method: "GET" }),
      "/tmp/session/segment_0001.ts",
    );
  });

  it("routes valid proxy requests to the remote HLS proxy handler", async () => {
    const handleRemoteHlsProxyRequest = vi.fn().mockResolvedValue(
      new Response("proxied", { status: 200 }),
    );
    const handleLocalMediaRequest = vi.fn();
    const routeLocalMediaRequest = createLocalMediaProtocolHandler({
      handleRemoteHlsProxyRequest,
      handleLocalMediaRequest,
    });

    const response = await routeLocalMediaRequest({
      method: "GET",
      url: "local-media://proxy/token-valid.bin",
    });

    expect(response.status).toBe(200);
    expect(handleRemoteHlsProxyRequest).toHaveBeenCalledTimes(1);
    expect(handleLocalMediaRequest).not.toHaveBeenCalled();
  });
});
