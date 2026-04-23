import {
  isRemoteHttpUrl,
  parseProxyToken,
} from "./hlsProxy.mjs";

import path from "node:path";

export function ensureAllowedLocalMediaRequestMethod(method) {
  const normalizedMethod = String(method ?? "").toUpperCase();
  if (normalizedMethod === "GET" || normalizedMethod === "HEAD") {
    return null;
  }

  return new Response("Method not allowed for local media", {
    status: 405,
    headers: {
      Allow: "GET, HEAD",
    },
  });
}

export function createLocalMediaProtocolHandler({
  handleRemoteHlsProxyRequest,
  handleLocalMediaRequest,
  allowedRoots = null,
}) {
  return async function routeLocalMediaRequest(request) {
    const rejectedMethodResponse = ensureAllowedLocalMediaRequestMethod(request.method);
    if (rejectedMethodResponse) {
      return rejectedMethodResponse;
    }

    const requestUrl = new URL(request.url);
    const classifiedRequest = classifyLocalMediaRequestUrl(requestUrl, {
      allowedRoots,
    });
    if (classifiedRequest.kind === "error") {
      return classifiedRequest.response;
    }
    if (classifiedRequest.kind === "proxy") {
      return handleRemoteHlsProxyRequest(request, requestUrl);
    }
    return handleLocalMediaRequest(request, classifiedRequest.filePath);
  };
}

export function classifyLocalMediaRequestUrl(requestUrl, { allowedRoots = null } = {}) {
  if (requestUrl.hostname === "proxy") {
    return { kind: "proxy" };
  }

  if (requestUrl.hostname !== "media") {
    return {
      kind: "error",
      response: new Response("Unknown local media target", { status: 404 }),
    };
  }

  try {
    const filePath = decodeURIComponent(requestUrl.pathname);
    if (!filePath) {
      return {
        kind: "error",
        response: new Response("Missing media path", { status: 400 }),
      };
    }

    if (allowedRoots && !isAllowedLocalMediaPath(filePath, allowedRoots)) {
      return {
        kind: "error",
        response: new Response("Local media path is outside the allowed roots", { status: 403 }),
      };
    }

    return {
      kind: "media",
      filePath,
    };
  } catch {
    return {
      kind: "error",
      response: new Response("Malformed media path", { status: 400 }),
    };
  }
}

export function resolveRemoteHlsProxyTarget(requestUrl, registry) {
  const token = parseProxyToken(requestUrl.pathname);
  if (!token) {
    return {
      kind: "error",
      response: new Response("Missing proxy token", { status: 400 }),
    };
  }

  const targetUrl = registry.resolve(token);
  if (!targetUrl || !isRemoteHttpUrl(targetUrl)) {
    return {
      kind: "error",
      response: new Response("Unknown proxied media target", { status: 404 }),
    };
  }

  return {
    kind: "ok",
    targetUrl,
  };
}

export function isAllowedLocalMediaPath(filePath, allowedRoots) {
  const resolvedPath = path.resolve(filePath);
  return allowedRoots.some((root) => {
    const resolvedRoot = path.resolve(root);
    return resolvedPath === resolvedRoot || resolvedPath.startsWith(`${resolvedRoot}${path.sep}`);
  });
}
