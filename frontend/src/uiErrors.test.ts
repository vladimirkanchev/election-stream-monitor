import { describe, expect, it } from "vitest";

import { BridgeTransportError } from "./bridge/contract";
import {
  getApiStreamOperatorMessage,
  getApiStreamSessionStateMessage,
  getHlsPlaybackErrorMessage,
  getSessionStartErrorMessage,
} from "./uiErrors";

describe("ui error messages", () => {
  it("maps unavailable api_stream start failures to an operator-safe message", () => {
    const error = new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "stream unavailable: upstream timeout",
    });

    expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
      "The selected live stream is unavailable right now.",
    );
  });

  it("maps reconnect-budget failures for api_stream to a specific operator message", () => {
    const error = new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "api_stream reconnect budget exhausted",
    });

    expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
      "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted.",
    );
  });

  it("keeps frontend-safe operator wording aligned with current backend api_stream failure text", () => {
    const cases = [
      {
        details: "api_stream fetch timed out",
        expected: "The selected live stream is unavailable right now.",
      },
      {
        details: "api_stream upstream connection failed: [Errno 111] Connection refused",
        expected: "The selected live stream is unavailable right now.",
      },
      {
        details: "api_stream upstream returned HTTP 503",
        expected: "The selected live stream is unavailable right now.",
      },
      {
        details: "Unsupported api_stream playlist/source",
        expected: "The selected live stream source is not supported by the current monitoring runtime.",
      },
      {
        details: "Unsupported api_stream URL scheme: file",
        expected: "The selected live stream source is not supported by the current monitoring runtime.",
      },
      {
        details: "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
        expected: "This looks like a webpage URL, not a direct media stream. Paste a direct .m3u8 or .mp4 URL instead.",
      },
      {
        details: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
        expected: "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted.",
      },
      {
        details: "api_stream session runtime exceeded max duration",
        expected: "The live stream monitoring run stopped after hitting a runtime safety limit.",
      },
      {
        details: "api_stream playlist refresh limit exceeded",
        expected: "The live stream monitoring run stopped after hitting a runtime safety limit.",
      },
    ];

    for (const testCase of cases) {
      const error = new BridgeTransportError({
        code: "SESSION_START_FAILED",
        message: "Session start request failed",
        details: testCase.details,
      });

      expect(getSessionStartErrorMessage(error, "api_stream")).toBe(testCase.expected);
    }
  });

  it("maps unsupported api_stream sources to a frontend-safe message", () => {
    const error = new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "unsupported master playlist source",
    });

    expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
      "The selected live stream source is not supported by the current monitoring runtime.",
    );
  });

  it("maps webpage-style api_stream inputs to a direct-media guidance message", () => {
    const error = new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
    });

    expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
      "This looks like a webpage URL, not a direct media stream. Paste a direct .m3u8 or .mp4 URL instead.",
    );
  });

  it("keeps generic local start failures unchanged for non-live sources", () => {
    const error = new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details: "cli crashed",
    });

    expect(getSessionStartErrorMessage(error, "video_segments")).toBe(
      "Monitoring could not be started. The local monitoring bridge reported a request failure.",
    );
  });

  it("exports explicit api_stream runtime messages for future live UI states", () => {
    expect(getApiStreamOperatorMessage("reconnecting")).toBe(
      "The live stream is temporarily unavailable. Monitoring is reconnecting.",
    );
  });

  it("maps failed api_stream session snapshots to operator-safe terminal messages", () => {
    expect(
      getApiStreamSessionStateMessage({
        status: "failed",
        statusReason: "terminal_failure",
        statusDetail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
      }),
    ).toBe(
      "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted.",
    );

    expect(
      getApiStreamSessionStateMessage({
        status: "failed",
        statusReason: "terminal_failure",
        statusDetail: "api_stream session runtime exceeded max duration",
      }),
    ).toBe("The live stream monitoring run stopped after hitting a runtime safety limit.");

    expect(
      getApiStreamSessionStateMessage({
        status: "completed",
        statusReason: "idle_poll_budget_exhausted",
        statusDetail: null,
      }),
    ).toBeNull();
  });

  it("maps missing HLS playlists to a specific playback message", () => {
    expect(
      getHlsPlaybackErrorMessage({
        details: "manifestLoadError",
        responseCode: 404,
        responseText: "Not Found",
      }),
    ).toBe("The selected HLS playlist could not be found for playback.");
  });

  it("maps blocked HLS access to a specific playback message", () => {
    expect(
      getHlsPlaybackErrorMessage({
        details: "manifestLoadError",
        responseCode: 403,
        responseText: "Forbidden",
      }),
    ).toBe("The selected HLS stream blocked playback access.");
  });

  it("maps invalid HLS manifests to a specific playback message", () => {
    expect(
      getHlsPlaybackErrorMessage({
        details: "manifestParsingError",
        responseCode: 502,
        responseText: "Remote HLS source returned html instead of a playlist",
      }),
    ).toBe("The selected HLS source did not return a valid playlist.");
  });
});
