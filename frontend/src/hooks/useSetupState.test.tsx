/**
 * Hook-level coverage for setup-source state transitions.
 *
 * These tests protect the runtime seam where mode switches must recompute
 * source access, not just the pure helper contract in `sourceModel.ts`.
 */

// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { DetectorOption } from "../types";
import { useSetupState } from "./useSetupState";

const DETECTORS: DetectorOption[] = [
  {
    id: "video_metrics",
    display_name: "Black Screen",
    description: "",
    category: "quality",
    origin: "built_in",
    status: "core",
    default_rule_id: "video_metrics.default_rule",
    default_selected: false,
    produces_alerts: false,
    supported_modes: ["video_segments", "video_files", "api_stream"],
    supported_suffixes: [".ts", ".mp4", ".m3u8"],
  },
];

function HookProbe() {
  const state = useSetupState({
    detectors: DETECTORS,
    frozen: false,
  });

  return (
    <div>
      <button onClick={() => state.setSourcePath("https://example.com/live/playlist.m3u8")}>
        SetRemotePath
      </button>
      <button onClick={() => state.setSourceKind("api_stream")}>SetApiStream</button>
      <button onClick={() => state.setSourceKind("video_files")}>SetVideoFiles</button>
      <dl>
        <dt>kind</dt>
        <dd data-testid="source-kind">{state.source.kind}</dd>
        <dt>access</dt>
        <dd data-testid="source-access">{state.source.access}</dd>
        <dt>path</dt>
        <dd data-testid="source-path">{state.source.path}</dd>
      </dl>
    </div>
  );
}

describe("useSetupState source contract", () => {
  afterEach(() => {
    cleanup();
  });

  it("recomputes source access when the selected mode changes", () => {
    render(<HookProbe />);

    fireEvent.click(screen.getByRole("button", { name: "SetRemotePath" }));
    expect(screen.getByTestId("source-kind").textContent).toBe("video_segments");
    expect(screen.getByTestId("source-access").textContent).toBe("local_path");

    fireEvent.click(screen.getByRole("button", { name: "SetApiStream" }));
    expect(screen.getByTestId("source-kind").textContent).toBe("api_stream");
    expect(screen.getByTestId("source-access").textContent).toBe("api_stream");

    fireEvent.click(screen.getByRole("button", { name: "SetVideoFiles" }));
    expect(screen.getByTestId("source-kind").textContent).toBe("video_files");
    expect(screen.getByTestId("source-access").textContent).toBe("local_path");
  });
});
