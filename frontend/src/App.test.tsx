// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { createNormalizedBridge, fail } from "./bridge/contract";
import type {
  DetectorOption,
  LocalBridge,
  MonitorSource,
  RunSessionInput,
  SessionSnapshot,
  SessionSummary,
} from "./types";

const mockBridge: LocalBridge = {
  listDetectors: vi.fn(),
  startSession: vi.fn(),
  readSession: vi.fn(),
  cancelSession: vi.fn(),
  resolvePlaybackSource: vi.fn(),
};

vi.mock("./bridge", () => ({
  localBridge: createNormalizedBridge(mockBridge),
}));

vi.mock("./components/VideoPlayerPanel", () => ({
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

vi.mock("./components/AlertDetailsDrawer", () => ({
  AlertDetailsDrawer: () => null,
}));

const DETECTORS: DetectorOption[] = [
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

const RUNNING_SESSION: SessionSummary = {
  session_id: "session-1",
  mode: "video_segments",
  input_path: "/data/streams/segments",
  selected_detectors: ["video_blur"],
  status: "running",
};

function makeSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
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

describe("App integration", () => {
  it("starts monitoring, freezes detector selection, and can end the session", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        ...RUNNING_SESSION,
        selected_detectors: input.selectedDetectors,
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());

    render(<App />);

    const pathInput = await screen.findByRole("textbox");
    fireEvent.change(pathInput, {
      target: { value: "/data/streams/segments" },
    });

    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "video_segments",
          path: "/data/streams/segments",
          access: "local_path",
        },
        selectedDetectors: ["video_blur"],
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });

    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "End Monitoring" }));
    await waitFor(() => {
      expect(mockBridge.cancelSession).toHaveBeenCalledWith("session-1");
    });
  });

  it("updates status from polling and shows completed state", async () => {
    const App = (await import("./App")).default;
    const completedSnapshot = makeSnapshot({
      session: {
        ...RUNNING_SESSION,
        status: "completed",
      },
      progress: {
        session_id: "session-1",
        status: "completed",
        processed_count: 4,
        total_count: 4,
        current_item: "segment_0004.ts",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 1,
        last_updated_utc: "2026-04-02 10:00:04",
      },
    });
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValueOnce(completedSnapshot)
      .mockResolvedValue(completedSnapshot);

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => expect(screen.getByText("Running")).toBeTruthy());

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeTruthy();
      expect(screen.getByText("Monitoring finished successfully for the current source.")).toBeTruthy();
    });
  });

  it("shows a start error message when monitoring cannot be started", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be started. Check the selected source and try again.")).toBeTruthy();
    });
  });

  it("shows a start error message when the initial session read fails after start", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("read failed"));

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be started. Check the selected source and try again.")).toBeTruthy();
    });
  });

  it("shows a start error message when the bridge returns a malformed start payload", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      mode: "video_segments",
      input_path: "/data/streams/segments",
      selected_detectors: ["video_blur"],
      status: "running",
    } as unknown as SessionSummary);

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be started. The local bridge returned an invalid response.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows a bridge-specific start error message for typed transport failures", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail("SESSION_START_FAILED", "Session start request failed", "cli crashed"),
    );

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be started. The local monitoring bridge reported a request failure.",
        ),
      ).toBeTruthy();
    });
  });

  it("keeps the last good session state when a polling read fails", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeSnapshot())
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(makeSnapshot());

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a reconnecting message for api stream polling failures and clears it on recovery", async () => {
    const App = (await import("./App")).default;
    const liveSession: SessionSummary = {
      session_id: "session-api-reconnect",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const liveSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-reconnect",
        status: "running",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:00",
      },
    });
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(liveSnapshot)
      .mockRejectedValueOnce(new Error("poll failed"))
      .mockResolvedValue(liveSnapshot);

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(
        screen.getByText("The live stream is temporarily unavailable. Monitoring is reconnecting."),
      ).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(
        screen.queryByText("The live stream is temporarily unavailable. Monitoring is reconnecting."),
      ).toBeNull();
      expect(screen.getByText("Live monitoring is active and currently analyzing live-window-001.")).toBeTruthy();
    });
  });

  it("shows a safety-limit message when a running api stream snapshot turns terminal", async () => {
    const App = (await import("./App")).default;
    const liveSession: SessionSummary = {
      session_id: "session-api-failed-runtime",
      mode: "api_stream",
      input_path: "https://example.com/live/playlist.m3u8",
      selected_detectors: ["video_blur"],
      status: "running",
    };
    const runningSnapshot = makeSnapshot({
      session: liveSession,
      progress: {
        session_id: "session-api-failed-runtime",
        status: "running",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:00",
        status_reason: null,
        status_detail: null,
      },
    });
    const failedSnapshot = makeSnapshot({
      session: { ...liveSession, status: "failed" },
      progress: {
        session_id: "session-api-failed-runtime",
        status: "failed",
        processed_count: 1,
        total_count: 4,
        current_item: "live-window-001",
        latest_result_detector: "video_blur",
        latest_result_detectors: ["video_blur"],
        alert_count: 0,
        last_updated_utc: "2026-04-04 09:00:01",
        status_reason: "terminal_failure",
        status_detail: "api_stream session runtime exceeded max duration",
      },
    });

    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(liveSession);
    (mockBridge.readSession as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(runningSnapshot)
      .mockResolvedValue(failedSnapshot);

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    await new Promise((resolve) => window.setTimeout(resolve, 1100));

    await waitFor(() => {
      expect(
        screen.getByText("The live stream monitoring run stopped after hitting a runtime safety limit."),
      ).toBeTruthy();
      expect(screen.getByText("Failed")).toBeTruthy();
    });
  });

  it("shows a retry-budget-exhausted start message for typed api stream bridge failures", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail(
        "SESSION_START_FAILED",
        "Session start request failed",
        "api_stream reconnect budget exhausted",
      ),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows direct-media guidance for unsupported webpage-style api stream inputs", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail(
        "SESSION_START_FAILED",
        "Session start request failed",
        "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
      ),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://video-platform.example/live/channel" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "This looks like a webpage URL, not a direct media stream. Paste a direct .m3u8 or .mp4 URL instead.",
        ),
      ).toBeTruthy();
    });
  });

  it("normalizes missing snapshot collections from backend reads", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      session: null,
      progress: null,
    } as unknown as SessionSnapshot);

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a stop error message when the cancel request fails", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("cancel failed"));

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "End Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Monitoring could not be ended cleanly. Try ending the session again.")).toBeTruthy();
    });
  });

  it("shows a stop error message when the bridge returns a malformed cancel payload", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      session_id: "session-1",
    } as unknown as SessionSummary);

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "End Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText("Monitoring could not be ended cleanly. The local bridge returned an invalid response."),
      ).toBeTruthy();
    });
  });

  it("shows a bridge-specific stop error message for typed cancel failures", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockResolvedValue(RUNNING_SESSION);
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(makeSnapshot());
    (mockBridge.cancelSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      fail("SESSION_CANCEL_FAILED", "Session cancel request failed", "cli crashed"),
    );

    render(<App />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "/data/streams/segments" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "End Monitoring" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Monitoring could not be ended cleanly. The local monitoring bridge reported a request failure.",
        ),
      ).toBeTruthy();
    });
  });

  it("starts api stream sessions with remote source payloads", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        session_id: "session-api-1",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-1",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "running",
        },
        progress: {
          session_id: "session-api-1",
          status: "running",
          processed_count: 1,
          total_count: 4,
          current_item: "live-window-001",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-04 09:00:00",
        },
      }),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/playlist.m3u8",
          access: "api_stream",
        },
        selectedDetectors: ["video_blur"],
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("API stream")).toBeTruthy();
      expect(screen.getByText("Mock Player")).toBeTruthy();
    });
  });

  it("shows a remote-source start error when the api stream cannot be reached", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("remote source unreachable"),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/unreachable.m3u8" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(mockBridge.startSession).toHaveBeenCalledWith({
        source: {
          kind: "api_stream",
          path: "https://example.com/live/unreachable.m3u8",
          access: "api_stream",
        },
        selectedDetectors: [],
      });
      expect(
        screen.getByText("Monitoring could not be started. Check the selected live stream and try again."),
      ).toBeTruthy();
    });
  });

  it("shows live session status details for api stream runs", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        session_id: "session-api-live",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-live",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "running",
        },
        progress: {
          session_id: "session-api-live",
          status: "running",
          processed_count: 1,
          total_count: 4,
          current_item: "live-window-001",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 0,
          last_updated_utc: "2026-04-04 09:00:00",
        },
      }),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Running")).toBeTruthy();
      expect(screen.getByText("API stream")).toBeTruthy();
      expect(screen.getByText("Live, 1 chunk analyzed")).toBeTruthy();
      expect(screen.getByText("1 chunk analyzed, 4 discovered")).toBeTruthy();
      expect(screen.getByText("00:02 live")).toBeTruthy();
      expect(
        screen.getByText("Live monitoring is active and currently analyzing live-window-001."),
      ).toBeTruthy();
    });
  });

  it("shows failed live-session status details for api stream runs", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        session_id: "session-api-failed",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "failed",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-failed",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "failed",
        },
        progress: {
          session_id: "session-api-failed",
          status: "failed",
          processed_count: 4,
          total_count: 6,
          current_item: "live-window-004",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 1,
          last_updated_utc: "2026-04-04 09:00:04",
        },
      }),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeTruthy();
      expect(screen.getByText("Live, 4 chunks analyzed")).toBeTruthy();
      expect(
        screen.getByText(
          "Live monitoring ended with an error. The stream may be unavailable or the reconnect budget may have been exhausted.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows longer-run live progress wording for api stream runs", async () => {
    const App = (await import("./App")).default;
    (mockBridge.startSession as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RunSessionInput) => ({
        session_id: "session-api-long",
        mode: input.source.kind,
        input_path: input.source.path,
        selected_detectors: input.selectedDetectors,
        status: "running",
      }),
    );
    (mockBridge.readSession as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeSnapshot({
        session: {
          session_id: "session-api-long",
          mode: "api_stream",
          input_path: "https://example.com/live/playlist.m3u8",
          selected_detectors: ["video_blur"],
          status: "running",
        },
        progress: {
          session_id: "session-api-long",
          status: "running",
          processed_count: 6,
          total_count: 9,
          current_item: "live-window-006",
          latest_result_detector: "video_blur",
          latest_result_detectors: ["video_blur"],
          alert_count: 1,
          last_updated_utc: "2026-04-04 09:00:06",
        },
      }),
    );

    render(<App />);

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "api_stream" },
    });
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "https://example.com/live/playlist.m3u8" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start Monitoring" }));

    await waitFor(() => {
      expect(screen.getByText("Live, 6 chunks analyzed")).toBeTruthy();
      expect(screen.getByText("6 chunks analyzed, 9 discovered")).toBeTruthy();
      expect(
        screen.getByText("Live monitoring is active and currently analyzing live-window-006."),
      ).toBeTruthy();
    });
  });
});
