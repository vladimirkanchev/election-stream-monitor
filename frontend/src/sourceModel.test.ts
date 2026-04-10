import { describe, expect, it } from "vitest";

import {
  createMonitorSource,
  inferMonitorSourceAccess,
  isSupportedApiStreamPath,
} from "./sourceModel";

describe("source model groundwork", () => {
  it("classifies http sources as api streams", () => {
    expect(inferMonitorSourceAccess("https://example.com/live/playlist.m3u8")).toBe("api_stream");
    expect(inferMonitorSourceAccess("https://example.com/archive/recording.mp4")).toBe("api_stream");
  });

  it("creates api stream monitor sources with remote access metadata", () => {
    expect(
      createMonitorSource("api_stream", " https://example.com/live/playlist.m3u8 "),
    ).toEqual({
      kind: "api_stream",
      path: "https://example.com/live/playlist.m3u8",
      access: "api_stream",
    });
  });

  it("rejects unsupported api stream schemes during access inference", () => {
    expect(isSupportedApiStreamPath("ftp://example.com/live/playlist.m3u8")).toBe(false);
    expect(inferMonitorSourceAccess("ftp://example.com/live/playlist.m3u8")).toBe("local_path");
  });

  it("rejects webpage-style remote URLs during api_stream access inference", () => {
    expect(isSupportedApiStreamPath("https://video-platform.example/live/channel")).toBe(false);
    expect(isSupportedApiStreamPath("https://portal.example/player.html")).toBe(false);
    expect(inferMonitorSourceAccess("https://video-platform.example/live/channel")).toBe("local_path");
  });

  it("classifies filesystem-style paths as local sources", () => {
    expect(createMonitorSource("video_files", "/data/streams/local").access).toBe("local_path");
  });

  it("tolerates missing source paths without crashing", () => {
    expect(createMonitorSource("video_segments", undefined).path).toBe("");
    expect(inferMonitorSourceAccess(undefined)).toBe("local_path");
  });
});
