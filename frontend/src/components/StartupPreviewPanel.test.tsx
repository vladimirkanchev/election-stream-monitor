// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StartupPreviewPanel } from "./StartupPreviewPanel";
import type { MonitorSource } from "../types";

const VIDEO_SEGMENTS_SOURCE: MonitorSource = {
  kind: "video_segments",
  path: "/tests/fixtures/media/video_segments/black_recovery_realert_long",
  access: "local_path",
};

const EMPTY_API_STREAM_SOURCE: MonitorSource = {
  kind: "api_stream",
  path: "",
  access: "api_stream",
};

afterEach(() => {
  cleanup();
});

describe("StartupPreviewPanel", () => {
  it("keeps the preview placeholder quiet once a source path is selected", () => {
    render(<StartupPreviewPanel source={VIDEO_SEGMENTS_SOURCE} />);

    expect(screen.getByText("Live View")).toBeTruthy();
    expect(screen.getByText("Video segments")).toBeTruthy();
    expect(screen.queryByText("Waiting to start")).toBeNull();
    expect(
      screen.queryByText(
        /The player is ready for video segments from \/tests\/fixtures\/media\/video_segments\/black_recovery_realert_long\./,
      ),
    ).toBeNull();
  });

  it("keeps the empty-source guidance when no stream URL is selected yet", () => {
    render(<StartupPreviewPanel source={EMPTY_API_STREAM_SOURCE} />);

    expect(
      screen.getByText("Paste a direct .m3u8 or .mp4 URL and start monitoring to begin playback."),
    ).toBeTruthy();
  });
});
