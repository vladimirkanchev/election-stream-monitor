import type { SegmentStartTimes } from "./types";

/**
 * Parse one HLS playlist into a segment-start map keyed by segment filename.
 *
 * This lets local native-HLS playback keep alert reveal timing aligned with
 * playback time even when the browser stack does not expose per-fragment
 * change events like Hls.js does.
 */
export function parseSegmentStartMapFromManifest(manifestText: string): SegmentStartTimes {
  const lines = manifestText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const segmentStarts: SegmentStartTimes = {};
  let pendingDurationSec: number | null = null;
  let nextSegmentStartSec = 0;

  for (const line of lines) {
    if (line.startsWith("#EXTINF:")) {
      pendingDurationSec = parseExtinfDuration(line);
      continue;
    }

    if (line.startsWith("#")) {
      continue;
    }

    const segmentName = getPlaylistSegmentName(line);
    if (segmentName) {
      segmentStarts[segmentName] = nextSegmentStartSec;
    }

    if (pendingDurationSec !== null) {
      nextSegmentStartSec += pendingDurationSec;
      pendingDurationSec = null;
    }
  }

  return segmentStarts;
}

function parseExtinfDuration(line: string): number | null {
  const payload = line.slice("#EXTINF:".length);
  const durationText = payload.split(",", 1)[0]?.trim();
  if (!durationText) {
    return null;
  }

  const durationSec = Number.parseFloat(durationText);
  return Number.isFinite(durationSec) && durationSec >= 0 ? durationSec : null;
}

function getPlaylistSegmentName(line: string): string | null {
  const sanitizedLine = line.split("?", 1)[0]?.trim();
  if (!sanitizedLine) {
    return null;
  }

  const segmentName = sanitizedLine.split("/").pop()?.trim();
  return segmentName || null;
}
