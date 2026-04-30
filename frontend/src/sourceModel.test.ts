/**
 * Focused contract coverage for frontend source normalization and access
 * inference across local modes and `api_stream`.
 */

import { describe, expect, it } from "vitest";

import {
  createMonitorSource,
  inferMonitorSourceAccess,
  isSupportedApiStreamPath,
  updateMonitorSourceKind,
  updateMonitorSourcePath,
} from "./sourceModel";

describe("source model groundwork", () => {
  it.each([
    ["api_stream", "https://example.com/live/playlist.m3u8", "api_stream"],
    ["api_stream", "https://example.com/archive/recording.mp4", "api_stream"],
    ["api_stream", "https://example.com/live/playlist.m3u8?token=abc", "api_stream"],
    ["video_files", "https://example.com/live/playlist.m3u8", "local_path"],
    ["video_segments", "https://example.com/archive/recording.mp4", "local_path"],
  ] as const)(
    "infers %s source access for %s mode and %s path",
    (kind, path, expectedAccess) => {
      expect(inferMonitorSourceAccess(kind, path)).toBe(expectedAccess);
    },
  );

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
    expect(
      inferMonitorSourceAccess("api_stream", "ftp://example.com/live/playlist.m3u8"),
    ).toBe("local_path");
  });

  it("rejects webpage-style remote URLs during api_stream access inference", () => {
    expect(isSupportedApiStreamPath("https://video-platform.example/live/channel")).toBe(false);
    expect(isSupportedApiStreamPath("https://portal.example/player.html")).toBe(false);
    expect(
      inferMonitorSourceAccess("api_stream", "https://video-platform.example/live/channel"),
    ).toBe("local_path");
  });

  it("keeps local modes on local access for both filesystem and remote-looking paths", () => {
    expect(createMonitorSource("video_files", "/data/streams/local").access).toBe("local_path");
    expect(createMonitorSource("video_files", "https://example.com/live/playlist.m3u8").access).toBe(
      "local_path",
    );
    expect(
      createMonitorSource("video_segments", "https://example.com/archive/recording.mp4").access,
    ).toBe("local_path");
  });

  it("recomputes access from the current mode when the source path changes", () => {
    const apiStreamSource = createMonitorSource("api_stream", "");
    expect(
      updateMonitorSourcePath(apiStreamSource, "https://example.com/live/playlist.m3u8"),
    ).toEqual({
      kind: "api_stream",
      path: "https://example.com/live/playlist.m3u8",
      access: "api_stream",
    });

    const localSource = createMonitorSource("video_files", "");
    expect(
      updateMonitorSourcePath(localSource, "https://example.com/live/playlist.m3u8"),
    ).toEqual({
      kind: "video_files",
      path: "https://example.com/live/playlist.m3u8",
      access: "local_path",
    });
  });

  it("recomputes access from the current path when the selected mode changes", () => {
    const localSource = createMonitorSource(
      "video_files",
      "https://example.com/live/playlist.m3u8",
    );
    expect(updateMonitorSourceKind(localSource, "api_stream")).toEqual({
      kind: "api_stream",
      path: "https://example.com/live/playlist.m3u8",
      access: "api_stream",
    });

    const apiStreamSource = createMonitorSource(
      "api_stream",
      "https://example.com/live/playlist.m3u8",
    );
    expect(updateMonitorSourceKind(apiStreamSource, "video_files")).toEqual({
      kind: "video_files",
      path: "https://example.com/live/playlist.m3u8",
      access: "local_path",
    });
  });

  it("tolerates missing source paths without crashing", () => {
    expect(createMonitorSource("video_segments", undefined).path).toBe("");
    expect(inferMonitorSourceAccess("video_segments", undefined)).toBe("local_path");
    expect(inferMonitorSourceAccess("api_stream", undefined)).toBe("local_path");
  });
});
