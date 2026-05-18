/**
 * VideoPlayerPanel coverage for direct remote MP4 playback and fallback error
 * handling when HLS is not used.
 */

// @vitest-environment jsdom

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DIRECT_MP4_SOURCE,
  expectDirectRemotePlaybackMessaging,
  expectRemoteMp4Playback,
  getHlsState,
  makeApiStreamSource,
  renderPanel,
  setDirectRemoteMediaSource,
} from "./VideoPlayerPanel.testSupport";

describe("VideoPlayerPanel direct remote playback", () => {
  const hlsState = getHlsState();

  it("loads a direct remote mp4 source without attaching HLS", async () => {
    setDirectRemoteMediaSource();

    const view = renderPanel(makeApiStreamSource(DIRECT_MP4_SOURCE));

    await waitFor(() => {
      expectRemoteMp4Playback(view);
      expect(hlsState.attachCount).toBe(0);
      expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
      expectDirectRemotePlaybackMessaging();
    });
  });

  it("shows a clean error when a direct remote mp4 source fails to open", async () => {
    setDirectRemoteMediaSource();

    const view = renderPanel(makeApiStreamSource(DIRECT_MP4_SOURCE));

    const video = expectRemoteMp4Playback(view);
    fireEvent.error(video);

    await waitFor(() => {
      expect(
        screen.getByText(
          "The selected remote media file could not be opened for playback.",
        ),
      ).toBeTruthy();
    });
  });
});
