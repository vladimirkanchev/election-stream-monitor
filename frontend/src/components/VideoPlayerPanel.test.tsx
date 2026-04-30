/**
 * Component-level coverage for playback error mapping and transport choice.
 *
 * The real HLS/runtime stack is replaced with small fakes so this suite can
 * stay focused on the player panel's user-facing behavior: which path is used
 * for HLS vs direct media, and which message appears when playback fails.
 */

// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VideoPlayerPanel } from "./VideoPlayerPanel";

const HLS_SOURCE = "local-media://proxy/test-playlist.m3u8";
const DIRECT_MP4_SOURCE = "https://cdn.example.com/archive/recording.mp4";

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
    const handlePlaybackError = React.useCallback((message: string) => {
      playbackState.playbackError = message;
      playbackState.playbackStatus = "error";
      forceRender();
    }, [forceRender]);

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

type HlsFailure = NonNullable<typeof hlsState.failure>;

function setHlsFailure(failure: HlsFailure) {
  hlsState.failure = failure;
}

// Most cases exercise the api_stream player path, so keep the source builder
// local to this suite instead of repeating the object literal.
function makeApiStreamSource(path = HLS_SOURCE) {
  return {
    kind: "api_stream" as const,
    path,
    access: "api_stream" as const,
  };
}

// Direct remote media tests need the actual <video> element before asserting
// load/error behavior.
function expectRemoteMp4Playback(view: ReturnType<typeof renderPanel>) {
  const video = view.container.querySelector("video") as HTMLVideoElement | null;
  expect(video).toBeTruthy();
  if (!video) {
    throw new Error("Expected remote mp4 playback to render a video element");
  }
  expect(video.src).toBe(DIRECT_MP4_SOURCE);
  return video;
}

describe("VideoPlayerPanel playback failures", () => {
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

  it.each([
    [
      "shows a 404 playlist message for HLS manifest load failures",
      {
        type: "networkError",
        details: "manifestLoadError",
        fatal: true,
        response: {
          code: 404,
          text: "Not Found",
        },
      } satisfies HlsFailure,
      "The selected HLS playlist could not be found for playback.",
    ],
    [
      "shows a 403 blocked-source message for HLS manifest load failures",
      {
        type: "networkError",
        details: "manifestLoadError",
        fatal: true,
        response: {
          code: 403,
          text: "Forbidden",
        },
      } satisfies HlsFailure,
      "The selected HLS stream blocked playback access.",
    ],
    [
      "shows an invalid-playlist message when the source body is not a valid HLS manifest",
      {
        type: "networkError",
        details: "manifestParsingError",
        fatal: true,
        response: {
          code: 502,
          text: "Remote HLS source returned html instead of a playlist",
        },
      } satisfies HlsFailure,
      "The selected HLS source did not return a valid playlist.",
    ],
  ])("%s", async (_label, failure, expectedMessage) => {
    setHlsFailure(failure);

    renderPanel();

    await waitFor(() => {
      expect(screen.getByText(expectedMessage)).toBeTruthy();
    });
  });

  it("shows that proxied remote HLS playback is routed through the local proxy", async () => {
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText("Local HLS proxy")).toBeTruthy();
      expect(
        screen.getByText("Remote HLS playback is routed through the local proxy."),
      ).toBeTruthy();
    });
  });

  it("does not repeatedly reattach HLS for the same media source across rerenders", async () => {
    const firstStatusChange = vi.fn();
    const secondStatusChange = vi.fn();

    const { rerender } = render(
      <VideoPlayerPanel
        source={makeApiStreamSource()}
        currentItem={null}
        playbackRequested
        onPlaybackStatusChange={firstStatusChange}
      />,
    );

    await waitFor(() => {
      expect(hlsState.attachCount).toBe(1);
    });

    rerender(
      <VideoPlayerPanel
        source={makeApiStreamSource()}
        currentItem={null}
        playbackRequested
        onPlaybackStatusChange={secondStatusChange}
      />,
    );

    await waitFor(() => {
      expect(hlsState.attachCount).toBe(1);
    });
  });

  it("loads a direct remote mp4 source without attaching HLS", async () => {
    playbackState.mediaSource = DIRECT_MP4_SOURCE;

    const view = renderPanel(makeApiStreamSource(DIRECT_MP4_SOURCE));

    await waitFor(() => {
      expectRemoteMp4Playback(view);
      expect(hlsState.attachCount).toBe(0);
      expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
      expect(screen.getByText("Direct remote media")).toBeTruthy();
      expect(screen.getByText("Playback is using the direct remote media file.")).toBeTruthy();
    });
  });

  it("shows a clean error when a direct remote mp4 source fails to open", async () => {
    playbackState.mediaSource = DIRECT_MP4_SOURCE;

    const view = renderPanel(makeApiStreamSource(DIRECT_MP4_SOURCE));

    const video = expectRemoteMp4Playback(view);
    fireEvent.error(video);

    await waitFor(() => {
      expect(
        screen.getByText("The selected remote media file could not be opened for playback."),
      ).toBeTruthy();
    });
  });
});

function renderPanel(
  source: {
    kind: "api_stream" | "video_files";
    path: string;
    access: "api_stream" | "local_path";
  } = {
    kind: "api_stream",
    path: "local-media://proxy/test-playlist.m3u8",
    access: "api_stream",
  },
) {
  return render(
    <VideoPlayerPanel
      source={source}
      currentItem={null}
      playbackRequested
    />,
  );
}
