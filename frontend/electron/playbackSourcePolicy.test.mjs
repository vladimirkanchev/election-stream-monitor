/**
 * Focused tests for renderer-facing playback URL adaptation.
 */

import { describe, expect, it, vi } from "vitest";

import {
  isAllowedRemotePlaybackSource,
  toRendererMediaUrl,
} from "./playbackSourcePolicy.mjs";

describe("playbackSourcePolicy", () => {
  it("allows only http and https remote playback urls", () => {
    expect(isAllowedRemotePlaybackSource("https://example.com/live.m3u8")).toBe(true);
    expect(isAllowedRemotePlaybackSource("http://example.com/video.mp4")).toBe(true);
    expect(isAllowedRemotePlaybackSource("ftp://example.com/video.mp4")).toBe(false);
  });

  it("routes remote HLS urls through the proxy registry", () => {
    const registerRemoteHlsProxyUrl = vi.fn().mockReturnValue("local-media://proxy/token.m3u8.bin");

    const result = toRendererMediaUrl("https://cdn.example.com/live/index.m3u8", {
      isRemoteHlsUrl: (source) => source.endsWith(".m3u8"),
      registerRemoteHlsProxyUrl,
    });

    expect(result).toBe("local-media://proxy/token.m3u8.bin");
    expect(registerRemoteHlsProxyUrl).toHaveBeenCalledWith(
      "https://cdn.example.com/live/index.m3u8",
    );
  });

  it("keeps direct remote non-HLS playback urls unchanged", () => {
    const result = toRendererMediaUrl("https://cdn.example.com/archive/recording.mp4", {
      isRemoteHlsUrl: () => false,
      registerRemoteHlsProxyUrl: vi.fn(),
    });

    expect(result).toBe("https://cdn.example.com/archive/recording.mp4");
  });

  it("maps local file paths into the renderer-safe local-media scheme", () => {
    const result = toRendererMediaUrl("/tmp/session/segment_0001.ts", {
      isRemoteHlsUrl: () => false,
      registerRemoteHlsProxyUrl: vi.fn(),
    });

    expect(result).toBe("local-media://media/tmp/session/segment_0001.ts");
  });

  it("rejects unsupported non-file schemes returned by the backend", () => {
    expect(() => toRendererMediaUrl("ftp://example.com/video.mp4", {
      isRemoteHlsUrl: () => false,
      registerRemoteHlsProxyUrl: vi.fn(),
    })).toThrow("Unsupported playback source scheme returned by backend");
  });
});
