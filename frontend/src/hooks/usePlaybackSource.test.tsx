// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createNormalizedBridge } from "../bridge/contract";
import type { LocalBridge, MonitorSource } from "../types";
import { usePlaybackSource } from "./usePlaybackSource";

const { mockBridge } = vi.hoisted(() => ({
  mockBridge: {
    listDetectors: vi.fn(),
    startSession: vi.fn(),
    readSession: vi.fn(),
    cancelSession: vi.fn(),
    resolvePlaybackSource: vi.fn(),
  } satisfies LocalBridge,
}));

vi.mock("../bridge", () => ({
  localBridge: createNormalizedBridge(mockBridge),
}));

function HookProbe({ source }: { source: MonitorSource }) {
  const state = usePlaybackSource({
    source,
    currentItem: null,
    playbackRequested: true,
  });

  return (
    <dl>
      <dt>status</dt>
      <dd data-testid="playback-status">{state.playbackStatus}</dd>
      <dt>error</dt>
      <dd data-testid="playback-error">{state.playbackError ?? "none"}</dd>
      <dt>live</dt>
      <dd data-testid="playback-live">{String(state.isLivePlayback)}</dd>
      <dt>media</dt>
      <dd data-testid="playback-media">{state.mediaSource ?? "none"}</dd>
    </dl>
  );
}

describe("usePlaybackSource api stream contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("marks api streams as live and surfaces playback failure when no remote source resolves", async () => {
    (mockBridge.resolvePlaybackSource as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    render(
      <HookProbe
        source={{
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("playback-status").textContent).toBe("error");
      expect(screen.getByTestId("playback-error").textContent).toBe("Playback unavailable");
      expect(screen.getByTestId("playback-live").textContent).toBe("true");
    });
  });

  it("keeps direct remote playback urls for api streams", async () => {
    (mockBridge.resolvePlaybackSource as ReturnType<typeof vi.fn>).mockResolvedValue(
      "https://example.com/live/playlist.m3u8",
    );

    render(
      <HookProbe
        source={{
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("playback-media").textContent).toBe(
        "https://example.com/live/playlist.m3u8",
      );
      expect(screen.getByTestId("playback-status").textContent).toBe("loading");
      expect(screen.getByTestId("playback-live").textContent).toBe("true");
    });
  });

  it("surfaces playback failure when remote playback resolution rejects", async () => {
    (mockBridge.resolvePlaybackSource as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network failed"),
    );

    render(
      <HookProbe
        source={{
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("playback-status").textContent).toBe("error");
      expect(screen.getByTestId("playback-error").textContent).toBe("Playback unavailable");
      expect(screen.getByTestId("playback-live").textContent).toBe("true");
    });
  });

  it("treats malformed playback-source payloads as unavailable", async () => {
    (mockBridge.resolvePlaybackSource as ReturnType<typeof vi.fn>).mockResolvedValue(
      { source: "https://example.com/live/playlist.m3u8" } as unknown as string,
    );

    render(
      <HookProbe
        source={{
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("playback-status").textContent).toBe("error");
      expect(screen.getByTestId("playback-error").textContent).toBe("Playback unavailable");
      expect(screen.getByTestId("playback-media").textContent).toBe("none");
    });
  });
});
