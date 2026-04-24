/**
 * Focused tests for extracted `local-media://` response helpers.
 */

import { describe, expect, it } from "vitest";

import {
  buildPlaylistResponse,
  guessContentType,
  parseLocalMediaRangeRequest,
} from "./localMediaResponses.mjs";

describe("localMediaResponses", () => {
  it("parses valid partial range requests for mp4 playback", () => {
    expect(
      parseLocalMediaRangeRequest({
        rangeHeader: "bytes=10-19",
        totalSize: 100,
        allowPartialResponse: true,
      }),
    ).toEqual({
      kind: "ok",
      start: 10,
      end: 19,
      status: 206,
    });
  });

  it("falls back to whole-file responses when partial range support is disabled", () => {
    expect(
      parseLocalMediaRangeRequest({
        rangeHeader: "bytes=10-19",
        totalSize: 100,
        allowPartialResponse: false,
      }),
    ).toEqual({
      kind: "ok",
      start: 0,
      end: 99,
      status: 200,
    });
  });

  it("rejects out-of-bounds ranges", () => {
    expect(
      parseLocalMediaRangeRequest({
        rangeHeader: "bytes=100-120",
        totalSize: 100,
        allowPartialResponse: true,
      }),
    ).toEqual({ kind: "invalid" });
  });

  it("builds no-store playlist responses", async () => {
    const response = buildPlaylistResponse(
      "#EXTM3U\n#EXT-X-ENDLIST",
      "application/vnd.apple.mpegurl",
      206,
    );

    expect(response.status).toBe(206);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("content-type")).toBe("application/vnd.apple.mpegurl");
    await expect(response.text()).resolves.toContain("#EXTM3U");
  });

  it("guesses the expected media content types", () => {
    expect(guessContentType("/tmp/file.mp4")).toBe("video/mp4");
    expect(guessContentType("/tmp/live/index.m3u8")).toBe("application/vnd.apple.mpegurl");
    expect(guessContentType("/tmp/live/segment_0001.ts")).toBe("video/mp2t");
    expect(guessContentType("/tmp/file.bin")).toBe("application/octet-stream");
  });
});
