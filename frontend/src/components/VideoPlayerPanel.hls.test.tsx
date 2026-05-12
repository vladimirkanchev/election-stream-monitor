/**
 * VideoPlayerPanel coverage for HLS transport choice and fatal HLS failures.
 */

// @vitest-environment jsdom

import { screen, waitFor, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  expectProxyPlaybackMessaging,
  getHlsState,
  type HlsFailure,
  makeApiStreamSource,
  renderPanel,
  setHlsFailure,
} from "./VideoPlayerPanel.testSupport";
import { VideoPlayerPanel } from "./VideoPlayerPanel";

describe("VideoPlayerPanel HLS playback handling", () => {
  const hlsState = getHlsState();

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
      expectProxyPlaybackMessaging();
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
});
