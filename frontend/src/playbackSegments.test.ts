/**
 * Parser coverage for native-HLS segment timing alignment used by the alert
 * feed when the browser stack does not expose fragment-change callbacks.
 */

import { describe, expect, it } from "vitest";

import { parseSegmentStartMapFromManifest } from "./playbackSegments";

describe("parseSegmentStartMapFromManifest", () => {
  it("builds cumulative starts from one basic HLS playlist", () => {
    const manifest = `#EXTM3U
#EXT-X-VERSION:3
#EXTINF:1.0,
segment_0000.ts
#EXTINF:1.0,
segment_0001.ts
#EXTINF:0.9,
segment_0002.ts
`;

    expect(parseSegmentStartMapFromManifest(manifest)).toEqual({
      "segment_0000.ts": 0,
      "segment_0001.ts": 1,
      "segment_0002.ts": 2,
    });
  });

  it("normalizes nested playlist paths and query strings", () => {
    const manifest = `#EXTM3U
#EXTINF:4.0,
segments/segment_0100.ts?token=abc
#EXTINF:4.0,
segments/segment_0101.ts?token=def
`;

    expect(parseSegmentStartMapFromManifest(manifest)).toEqual({
      "segment_0100.ts": 0,
      "segment_0101.ts": 4,
    });
  });
});
