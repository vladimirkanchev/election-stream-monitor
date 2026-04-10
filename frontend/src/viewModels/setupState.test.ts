import { describe, expect, it } from "vitest";

import type { DetectorOption } from "../types";
import {
  getNextSelectedDetectors,
  getVisibleDetectors,
} from "./setupState";

const demoDetectors: DetectorOption[] = [
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
    supported_modes: ["video_segments", "video_files"],
    supported_suffixes: [".ts", ".mp4"],
  },
  {
    id: "video_blur",
    display_name: "Blur",
    description: "",
    category: "quality",
    origin: "built_in",
    status: "optional",
    default_rule_id: "video_blur.default_rule",
    default_selected: true,
    produces_alerts: true,
    supported_modes: ["video_segments", "video_files"],
    supported_suffixes: [".ts", ".mp4"],
  },
];

describe("getNextSelectedDetectors", () => {
  it("keeps detector selection frozen once monitoring has started", () => {
    expect(
      getNextSelectedDetectors(["video_metrics"], demoDetectors, true),
    ).toEqual(["video_metrics"]);
  });

  it("falls back to visible defaults when setup is not frozen", () => {
    expect(
      getNextSelectedDetectors(
        [],
        getVisibleDetectors(demoDetectors, "video_segments"),
        false,
      ),
    ).toEqual(["video_blur"]);
  });

  it("returns the visible detector set for the selected mode", () => {
    expect(
      getVisibleDetectors(demoDetectors, "video_files").map((detector) => detector.id),
    ).toEqual(["video_metrics", "video_blur"]);
  });

  it("preserves still-valid detector ids across a mode switch", () => {
    expect(
      getNextSelectedDetectors(
        ["video_metrics", "video_blur"],
        getVisibleDetectors(demoDetectors, "video_files"),
        false,
      ),
    ).toEqual(["video_metrics", "video_blur"]);
  });
});
