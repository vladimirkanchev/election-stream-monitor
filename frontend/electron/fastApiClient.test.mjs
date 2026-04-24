/**
 * Focused tests for the extracted FastAPI JSON client used by `main.mjs`.
 */

import { describe, expect, it, vi } from "vitest";

import { ApiHttpError } from "./apiErrors.mjs";
import { createFastApiClient } from "./fastApiClient.mjs";

describe("fastApiClient", () => {
  it("sends the expected session-start payload", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ session_id: "session-123", status: "pending" }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    const client = createFastApiClient({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl,
    });

    const result = await client.apiStartSession({
      source: {
        kind: "video_files",
        path: "/tmp/video.mp4",
      },
      selectedDetectors: ["video_metrics"],
    });

    expect(result).toEqual({ session_id: "session-123", status: "pending" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          mode: "video_files",
          input_path: "/tmp/video.mp4",
          selected_detectors: ["video_metrics"],
        }),
      }),
    );
  });

  it("preserves structured API errors", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Session not found",
          error_code: "session_not_found",
          status_reason: "session_not_found",
          status_detail: "No persisted session snapshot found",
        }),
        {
          status: 404,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    const client = createFastApiClient({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl,
    });

    await expect(client.apiReadSession("session-404")).rejects.toMatchObject({
      name: "ApiHttpError",
      status: 404,
      apiPayload: {
        error_code: "session_not_found",
        status_reason: "session_not_found",
      },
    });
  });

  it("rejects non-JSON success responses", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
        headers: { "content-type": "text/plain" },
      }),
    );
    const client = createFastApiClient({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl,
    });

    await expect(client.apiGetHealth()).rejects.toMatchObject({
      name: "ApiHttpError",
      message: "FastAPI returned a non-JSON response",
      status: 200,
    });
  });
});
