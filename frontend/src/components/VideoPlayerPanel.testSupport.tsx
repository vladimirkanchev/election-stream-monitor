/**
 * Shared test support for VideoPlayerPanel transport and playback tests.
 */

// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, vi } from "vitest";

import { VideoPlayerPanel } from "./VideoPlayerPanel";

export const HLS_SOURCE = "local-media://proxy/test-playlist.m3u8";
export const DIRECT_MP4_SOURCE =
  "https://cdn.example.com/archive/recording.mp4";

type PlaybackSource = {
  kind: "api_stream" | "video_files";
  path: string;
  access: "api_stream" | "local_path";
};

const hlsState = vi.hoisted(() => ({
  attachCount: 0,
  failure: null as null | {
    type: string;
    details: string;
    fatal: boolean;
    response?: { code?: number | null; text?: string | null };
  },
}));

const playbackState = vi.hoisted(() => ({
  mediaSource: "local-media://proxy/test-playlist.m3u8",
  playbackStatus: "loading" as "loading" | "error" | "playing",
  playbackError: null as string | null,
  play: vi.fn(async () => {}),
  stop: vi.fn(),
  handlePlaybackReady: vi.fn(async () => {}),
  handlePlaybackTimeChange: vi.fn(),
  handlePlaybackMetadataChange: vi.fn(),
}));

vi.mock("hls.js", () => {
  const Events = {
    MANIFEST_PARSED: "manifestParsed",
    LEVEL_LOADED: "levelLoaded",
    FRAG_CHANGED: "fragChanged",
    ERROR: "error",
  } as const;

  class FakeHls {
    static Events = Events;

    static isSupported() {
      return true;
    }

    private listeners = new Map<string, (event: unknown, data: unknown) => void>();

    loadSource(_source: string) {}

    attachMedia(_media: HTMLVideoElement) {
      hlsState.attachCount += 1;
      queueMicrotask(() => {
        if (hlsState.failure) {
          this.listeners.get(Events.ERROR)?.(undefined, hlsState.failure);
        }
      });
    }

    on(event: string, handler: (event: unknown, data: unknown) => void) {
      this.listeners.set(event, handler);
    }

    destroy() {}
  }

  return {
    default: FakeHls,
  };
});

vi.mock("../hooks/usePlaybackSource", () => ({
  usePlaybackSource: ({ source }: { source: { kind: string } }) => {
    const [, forceRender] = React.useReducer((value) => value + 1, 0);
    const videoRef = React.useRef<HTMLVideoElement | null>(null);
    const handlePlaybackError = React.useCallback(
      (message: string) => {
        playbackState.playbackError = message;
        playbackState.playbackStatus = "error";
        forceRender();
      },
      [forceRender],
    );

    return {
      mediaSource: playbackState.mediaSource,
      playbackStatus: playbackState.playbackStatus,
      playbackTime: 0,
      playbackDuration: null,
      isLivePlayback: source.kind === "api_stream",
      playbackError: playbackState.playbackError,
      play: playbackState.play,
      stop: playbackState.stop,
      videoRef,
      handlePlaybackReady: playbackState.handlePlaybackReady,
      handlePlaybackTimeChange: playbackState.handlePlaybackTimeChange,
      handlePlaybackMetadataChange: playbackState.handlePlaybackMetadataChange,
      handlePlaybackError,
    };
  },
}));

export type HlsFailure = NonNullable<typeof hlsState.failure>;

/**
 * Returns the shared fake HLS runtime state so tests can assert attach counts
 * without needing to know how the mock module is wired.
 */
export function getHlsState() {
  return hlsState;
}

/**
 * Returns the shared fake playback-hook state used by the panel tests.
 */
export function getPlaybackState() {
  return playbackState;
}

/**
 * Configures the next HLS attach cycle to surface a fatal failure payload.
 */
export function setHlsFailure(failure: HlsFailure) {
  hlsState.failure = failure;
}

/**
 * Builds the standard `api_stream` source object used by panel tests.
 */
export function makeApiStreamSource(path = HLS_SOURCE) {
  return {
    kind: "api_stream" as const,
    path,
    access: "api_stream" as const,
  };
}

/**
 * Switches the mocked playback hook onto a direct remote media file.
 */
export function setDirectRemoteMediaSource(path = DIRECT_MP4_SOURCE) {
  playbackState.mediaSource = path;
}

/**
 * Renders the panel with the lightweight fake playback runtime used by these
 * transport-specific tests.
 */
export function renderPanel(source: PlaybackSource = makeApiStreamSource()) {
  return render(
    <VideoPlayerPanel
      source={source}
      currentItem={null}
      playbackRequested
    />,
  );
}

/**
 * Returns the rendered `<video>` element for direct-MP4 playback and asserts
 * that it points at the expected remote source.
 */
export function expectRemoteMp4Playback(view: ReturnType<typeof renderPanel>) {
  const video = view.container.querySelector("video") as HTMLVideoElement | null;
  expect(video).toBeTruthy();
  if (!video) {
    throw new Error("Expected remote mp4 playback to render a video element");
  }
  expect(video.src).toBe(DIRECT_MP4_SOURCE);
  return video;
}

/**
 * Asserts the proxy-specific transport copy shown for remote HLS playback.
 */
export function expectProxyPlaybackMessaging() {
  expect(screen.getByText("Local HLS proxy")).toBeTruthy();
  expect(
    screen.getByText("Remote HLS playback is routed through the local proxy."),
  ).toBeTruthy();
}

/**
 * Asserts the direct-remote-media transport copy shown for MP4 playback.
 */
export function expectDirectRemotePlaybackMessaging() {
  expect(screen.getByText("Direct remote media")).toBeTruthy();
  expect(
    screen.getByText("Playback is using the direct remote media file."),
  ).toBeTruthy();
}

beforeEach(() => {
  hlsState.attachCount = 0;
  hlsState.failure = null;
  playbackState.mediaSource = HLS_SOURCE;
  playbackState.playbackStatus = "loading";
  playbackState.playbackError = null;
  playbackState.play.mockClear();
  playbackState.stop.mockClear();
  playbackState.handlePlaybackReady.mockClear();
  playbackState.handlePlaybackTimeChange.mockClear();
  playbackState.handlePlaybackMetadataChange.mockClear();
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
