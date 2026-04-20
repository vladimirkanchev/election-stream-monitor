import React from "react";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { createNormalizedBridge } from "../bridge/contract";
import type {
  DetectorOption,
  LocalBridge,
  MonitorSource,
  SessionSnapshot,
  SessionSummary,
} from "../types";

export const mockBridge: LocalBridge = {
  listDetectors: vi.fn(),
  startSession: vi.fn(),
  readSession: vi.fn(),
  cancelSession: vi.fn(),
  resolvePlaybackSource: vi.fn(),
};

vi.mock("../bridge", () => ({
  localBridge: createNormalizedBridge(mockBridge),
}));

vi.mock("../components/VideoPlayerPanel", () => ({
  VideoPlayerPanel: ({
    source,
    onPlaybackStatusChange,
    onPlaybackMetricsChange,
    onPlaybackItemChange,
    onPlaybackSegmentMapChange,
  }: {
    source: MonitorSource;
    onPlaybackStatusChange?: (status: "loading" | "playing") => void;
    onPlaybackMetricsChange?: (metrics: {
      time: number;
      duration: number | null;
      isLive: boolean;
    }) => void;
    onPlaybackItemChange?: (item: string | null) => void;
    onPlaybackSegmentMapChange?: (segmentStarts: Record<string, number>) => void;
  }) => {
    React.useEffect(() => {
      const isApiStream = source.kind === "api_stream";
      onPlaybackStatusChange?.("playing");
      onPlaybackMetricsChange?.({
        time: 2,
        duration: isApiStream ? null : 10,
        isLive: isApiStream,
      });
      onPlaybackItemChange?.(isApiStream ? "live-window-001" : "segment_0002.ts");
      onPlaybackSegmentMapChange?.({
        "segment_0001.ts": 1,
        "segment_0002.ts": 2,
      });
    }, [source.kind]);

    return <div>Mock Player</div>;
  },
}));

vi.mock("../components/AlertDetailsDrawer", () => ({
  AlertDetailsDrawer: () => null,
}));

export const DETECTORS: DetectorOption[] = [
  {
    id: "video_blur",
    display_name: "Blur Check",
    description: "Blur detector",
    category: "quality",
    origin: "built_in",
    status: "optional",
    default_rule_id: "video_blur.default_rule",
    default_selected: false,
    produces_alerts: true,
    supported_modes: ["video_segments", "video_files", "api_stream"],
    supported_suffixes: [".ts", ".mp4"],
  },
];

export const RUNNING_SESSION: SessionSummary = {
  session_id: "session-1",
  mode: "video_segments",
  input_path: "/data/streams/segments",
  selected_detectors: ["video_blur"],
  status: "running",
};

export function makeSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    session: RUNNING_SESSION,
    progress: {
      session_id: "session-1",
      status: "running",
      processed_count: 1,
      total_count: 4,
      current_item: "segment_0001.ts",
      latest_result_detector: "video_blur",
      latest_result_detectors: ["video_blur"],
      alert_count: 0,
      last_updated_utc: "2026-04-02 10:00:00",
    },
    alerts: [],
    results: [],
    latest_result: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (mockBridge.listDetectors as ReturnType<typeof vi.fn>).mockResolvedValue(DETECTORS);
  (mockBridge.resolvePlaybackSource as ReturnType<typeof vi.fn>).mockResolvedValue(
    "local-media://segments/index.m3u8",
  );
  (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...RUNNING_SESSION,
    status: "cancelling",
  });
});

afterEach(() => {
  cleanup();
});

export async function renderApp() {
  const App = (await import("../App")).default;
  return render(<App />);
}

export async function enterLocalSource(path = "/data/streams/segments") {
  fireEvent.change(await screen.findByRole("textbox"), {
    target: { value: path },
  });
}

export async function enterApiStreamSource(url: string) {
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "api_stream" },
  });
  fireEvent.change(await screen.findByRole("textbox"), {
    target: { value: url },
  });
}

export async function toggleFirstDetector() {
  fireEvent.click(await screen.findByRole("checkbox"));
}

export function startMonitoring() {
  fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));
}

export function endMonitoring() {
  fireEvent.click(screen.getByRole("button", { name: "End Monitoring" }));
}
