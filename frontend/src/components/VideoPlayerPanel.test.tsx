// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VideoPlayerPanel } from "./VideoPlayerPanel";

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

describe("VideoPlayerPanel playback failures", () => {
  beforeEach(() => {
    hlsState.attachCount = 0;
    hlsState.failure = null;
    playbackState.mediaSource = "local-media://proxy/test-playlist.m3u8";
    playbackState.playbackStatus = "loading";
    playbackState.playbackError = null;
    playbackState.play.mockClear();
    playbackState.stop.mockClear();
    playbackState.handlePlaybackReady.mockClear();
    playbackState.handlePlaybackTimeChange.mockClear();
    playbackState.handlePlaybackMetadataChange.mockClear();
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows a 404 playlist message for HLS manifest load failures", async () => {
    hlsState.failure = {
      type: "networkError",
      details: "manifestLoadError",
      fatal: true,
      response: {
        code: 404,
        text: "Not Found",
      },
    };

    renderPanel();

    await waitFor(() => {
      expect(
        screen.getByText("The selected HLS playlist could not be found for playback."),
      ).toBeTruthy();
    });
  });

  it("shows a 403 blocked-source message for HLS manifest load failures", async () => {
    hlsState.failure = {
      type: "networkError",
      details: "manifestLoadError",
      fatal: true,
      response: {
        code: 403,
        text: "Forbidden",
      },
    };

    renderPanel();

    await waitFor(() => {
      expect(
        screen.getByText("The selected HLS stream blocked playback access."),
      ).toBeTruthy();
    });
  });

  it("shows an invalid-playlist message when the source body is not a valid HLS manifest", async () => {
    hlsState.failure = {
      type: "networkError",
      details: "manifestParsingError",
      fatal: true,
      response: {
        code: 502,
        text: "Remote HLS source returned html instead of a playlist",
      },
    };

    renderPanel();

    await waitFor(() => {
      expect(
        screen.getByText("The selected HLS source did not return a valid playlist."),
      ).toBeTruthy();
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
        source={{
          kind: "api_stream",
          path: "local-media://proxy/test-playlist.m3u8",
          access: "api_stream",
        }}
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
        source={{
          kind: "api_stream",
          path: "local-media://proxy/test-playlist.m3u8",
          access: "api_stream",
        }}
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
    playbackState.mediaSource = "https://cdn.example.com/archive/recording.mp4";

    const view = renderPanel({
      kind: "api_stream",
      path: "https://cdn.example.com/archive/recording.mp4",
      access: "api_stream",
    });

    await waitFor(() => {
      const video = view.container.querySelector("video") as HTMLVideoElement | null;
      expect(video).toBeTruthy();
      if (!video) {
        throw new Error("Expected remote mp4 playback to render a video element");
      }
      expect(video.src).toBe("https://cdn.example.com/archive/recording.mp4");
      expect(hlsState.attachCount).toBe(0);
      expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
      expect(screen.getByText("Direct remote media")).toBeTruthy();
      expect(screen.getByText("Playback is using the direct remote media file.")).toBeTruthy();
    });
  });

  it("shows a clean error when a direct remote mp4 source fails to open", async () => {
    playbackState.mediaSource = "https://cdn.example.com/archive/recording.mp4";

    const view = renderPanel({
      kind: "api_stream",
      path: "https://cdn.example.com/archive/recording.mp4",
      access: "api_stream",
    });

    const video = view.container.querySelector("video") as HTMLVideoElement | null;
    expect(video).toBeTruthy();
    if (!video) {
      throw new Error("Expected remote mp4 playback to render a video element");
    }
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
