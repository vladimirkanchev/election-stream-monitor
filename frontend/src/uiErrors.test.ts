/**
 * Operator-facing wording tests for typed bridge errors normalized by the
 * frontend bridge contract.
 */

import { describe, expect, it } from "vitest";

import { BridgeTransportError } from "./bridge/contract";
import {
  getApiStreamOperatorMessage,
  getApiStreamSessionStateMessage,
  getHlsPlaybackErrorMessage,
  getSessionStopErrorMessage,
  getSessionStartErrorMessage,
} from "./uiErrors";

describe("ui error messages", () => {
  function startFailure(
    details: string,
    metadata?: {
      backend_error_code?: string;
      status_reason?: string;
      status_detail?: string;
    },
  ) {
    return new BridgeTransportError({
      code: "SESSION_START_FAILED",
      message: "Session start request failed",
      details,
      ...metadata,
    });
  }

  function cancelFailure(
    details: string,
    metadata?: {
      backend_error_code?: string;
      status_reason?: string;
      status_detail?: string;
    },
  ) {
    return new BridgeTransportError({
      code: "SESSION_CANCEL_FAILED",
      message: "Session cancel request failed",
      details,
      ...metadata,
    });
  }

  describe("session start messaging", () => {
    it("maps unavailable api_stream start failures to an operator-safe message", () => {
      const error = startFailure("stream unavailable: upstream timeout");

      expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
        "The selected live stream is unavailable right now.",
      );
    });

    it("maps reconnect-budget failures for api_stream to a specific operator message", () => {
      const error = startFailure("api_stream reconnect budget exhausted");

      expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
        "Monitoring could not reconnect to the live stream, so it has ended.",
      );
    });

    it("uses backend error metadata when api_stream start failures carry structured FastAPI context", () => {
      const error = startFailure("Request validation failed", {
        backend_error_code: "validation_failed",
        status_reason: "validation_failed",
        status_detail: "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
      });

      expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
        "This link opens a webpage, not the video stream itself. Paste the direct video link (.m3u8 or .mp4) instead.",
      );
    });

    it("normalizes current api_stream backend failure details into stable operator wording", () => {
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
          expected: "This live stream link is not supported here.",
        },
        {
          details: "Unsupported api_stream URL scheme: file",
          expected: "This live stream link is not supported here.",
        },
        {
          details: "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
          expected:
            "This link opens a webpage, not the video stream itself. Paste the direct video link (.m3u8 or .mp4) instead.",
        },
        {
          details: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
          expected: "Monitoring could not reconnect to the live stream, so it has ended.",
        },
        {
          details: "api_stream session runtime exceeded max duration",
          expected: "Monitoring ended because this live run was taking too long.",
        },
        {
          details: "api_stream playlist refresh limit exceeded",
          expected: "Monitoring ended because this live run was taking too long.",
        },
      ];

      for (const testCase of cases) {
        const error = startFailure(testCase.details);

        expect(getSessionStartErrorMessage(error, "api_stream")).toBe(testCase.expected);
      }
    });

    it("maps reconnecting api_stream start failures from structured retry metadata", () => {
      const error = startFailure("temporary retryable upstream failure", {
        status_detail: "retryable upstream failure while reconnecting",
      });

      expect(getSessionStartErrorMessage(error, "api_stream")).toBe(
        "The live stream dropped for a moment. Monitoring is trying to reconnect.",
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
  });

  describe("session stop messaging", () => {
    it("maps invalid cancel-state bridge failures to a more specific stop message", () => {
      const error = cancelFailure("Session session-123 is already completed.", {
        backend_error_code: "cancel_failed",
        status_reason: "cancel_failed",
        status_detail: "Session session-123 is already completed.",
      });

      expect(getSessionStopErrorMessage(error)).toBe(
        "Monitoring was already ending or had already finished.",
      );
    });

    it("keeps missing-session cancel failures on the generic bridge-aware stop wording", () => {
      const error = cancelFailure(
        "No persisted session snapshot found for session_id=session-123",
        {
          backend_error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found for session_id=session-123",
        },
      );

      expect(getSessionStopErrorMessage(error)).toBe(
        "Monitoring could not be ended cleanly. The local monitoring bridge reported a request failure.",
      );
    });

    it("maps invalid bridge stop responses to the bridge-invalid-response wording", () => {
      const error = new BridgeTransportError({
        code: "INVALID_BRIDGE_RESPONSE",
        message: "invalid bridge cancel response",
      });

      expect(getSessionStopErrorMessage(error)).toBe(
        "Monitoring could not be ended cleanly. The local bridge returned an invalid response.",
      );
    });
  });

  describe("live session runtime messaging", () => {
    it("exports explicit api_stream runtime messages for reconnecting and idle-bounded completion", () => {
      expect(getApiStreamOperatorMessage("reconnecting")).toBe(
        "The live stream dropped for a moment. Monitoring is trying to reconnect.",
      );
      expect(getApiStreamOperatorMessage("idlePollBudgetExhausted")).toBe(
        "The live stream stopped sending new video, so monitoring has ended.",
      );
    });

    it("maps api_stream session snapshots to operator-safe terminal and warning messages", () => {
      expect(
        getApiStreamSessionStateMessage({
          status: "failed",
          statusReason: "source_unreachable",
          statusDetail: "api_stream reconnect budget exhausted: api_stream upstream returned HTTP 503",
        }),
      ).toBe(
        "Monitoring could not reconnect to the live stream, so it has ended.",
      );

      expect(
        getApiStreamSessionStateMessage({
          status: "failed",
          statusReason: "source_unreachable",
          statusDetail: "api_stream session runtime exceeded max duration",
        }),
      ).toBe("Monitoring ended because this live run was taking too long.");

      expect(
        getApiStreamSessionStateMessage({
          status: "completed",
          statusReason: "idle_poll_budget_exhausted",
          statusDetail: null,
        }),
      ).toBe(
        "The live stream stopped sending new video, so monitoring has ended.",
      );
    });

    it("returns no operator message for non-failed non-warning api_stream states", () => {
      expect(
        getApiStreamSessionStateMessage({
          status: "running",
          statusReason: "running",
          statusDetail: null,
        }),
      ).toBeNull();

      expect(
        getApiStreamSessionStateMessage({
          status: "cancelled",
          statusReason: "cancelled_by_user",
          statusDetail: "Stopped from the desktop UI",
        }),
      ).toBeNull();
    });
  });

  describe("playback messaging", () => {
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

    it("falls back to the generic HLS open message for uncategorized playback failures", () => {
      expect(
        getHlsPlaybackErrorMessage({
          details: "networkError",
          responseCode: 500,
          responseText: "upstream timeout",
        }),
      ).toBe("The selected HLS stream could not be opened for playback.");
    });
  });
});
