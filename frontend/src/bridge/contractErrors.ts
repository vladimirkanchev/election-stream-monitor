/**
 * Transport envelope and typed error helpers for the frontend bridge.
 *
 * This module is the owning source for bridge error codes/payloads plus the
 * success/failure envelope helpers consumed by the public contract facade.
 */

import { normalizeNullableString, isRecord } from "./contractShared";

export type BridgeErrorCode =
  | "DETECTOR_CATALOG_FAILED"
  | "SESSION_START_FAILED"
  | "SESSION_READ_FAILED"
  | "SESSION_CANCEL_FAILED"
  | "PLAYBACK_SOURCE_RESOLUTION_FAILED"
  | "INVALID_BRIDGE_RESPONSE";

export interface BridgeErrorPayload {
  code: BridgeErrorCode;
  message: string;
  details?: string | null;
  backend_error_code?: string | null;
  status_reason?: string | null;
  status_detail?: string | null;
}

const INVALID_BRIDGE_ERROR_PAYLOAD: BridgeErrorPayload = {
  code: "INVALID_BRIDGE_RESPONSE",
  message: "invalid bridge error response",
  details: null,
  backend_error_code: null,
  status_reason: null,
  status_detail: null,
};

export type BridgeSuccess<T> = {
  ok: true;
  data: T;
};

export type BridgeFailure = {
  ok: false;
  error: BridgeErrorPayload;
};

export type BridgeResponse<T> = BridgeSuccess<T> | BridgeFailure;

export class BridgeTransportError extends Error {
  readonly code: BridgeErrorCode;
  readonly details: string | null;
  readonly backendErrorCode: string | null;
  readonly statusReason: string | null;
  readonly statusDetail: string | null;

  constructor(error: BridgeErrorPayload) {
    super(error.message);
    this.name = "BridgeTransportError";
    this.code = error.code;
    this.details = error.details ?? null;
    this.backendErrorCode = error.backend_error_code ?? null;
    this.statusReason = error.status_reason ?? null;
    this.statusDetail = error.status_detail ?? null;
  }
}

export function isBridgeTransportError(error: unknown): error is BridgeTransportError {
  return error instanceof BridgeTransportError;
}

export function ok<T>(data: T): BridgeSuccess<T> {
  return { ok: true, data };
}

export function fail(
  code: BridgeErrorCode,
  message: string,
  details?: string | null,
  metadata?: {
    backend_error_code?: string | null;
    status_reason?: string | null;
    status_detail?: string | null;
  },
): BridgeFailure {
  return {
    ok: false,
    error: {
      code,
      message,
      details: details ?? null,
      backend_error_code: metadata?.backend_error_code ?? null,
      status_reason: metadata?.status_reason ?? null,
      status_detail: metadata?.status_detail ?? null,
    },
  };
}

export function unwrapBridgeValue<T>(value: T | BridgeResponse<T>): T {
  if (isBridgeResponse(value)) {
    if (!value.ok) {
      throw new BridgeTransportError(normalizeBridgeErrorPayload(value.error));
    }
    return value.data;
  }

  return value;
}

export function normalizeBridgeErrorPayload(value: unknown): BridgeErrorPayload {
  if (!isRecord(value)) {
    return INVALID_BRIDGE_ERROR_PAYLOAD;
  }

  return {
    code: isBridgeErrorCode(value["code"]) ? value["code"] : "INVALID_BRIDGE_RESPONSE",
    message:
      typeof value["message"] === "string" && value["message"].trim().length > 0
        ? value["message"]
        : "invalid bridge error response",
    details: normalizeNullableString(value["details"]),
    backend_error_code: normalizeNullableString(value["backend_error_code"]),
    status_reason: normalizeNullableString(value["status_reason"]),
    status_detail: normalizeNullableString(value["status_detail"]),
  };
}

export function isBridgeResponse<T>(
  value: T | BridgeResponse<T>,
): value is BridgeResponse<T> {
  return isRecord(value) && typeof value["ok"] === "boolean";
}

export function isBridgeErrorCode(value: unknown): value is BridgeErrorCode {
  return (
    value === "DETECTOR_CATALOG_FAILED" ||
    value === "SESSION_START_FAILED" ||
    value === "SESSION_READ_FAILED" ||
    value === "SESSION_CANCEL_FAILED" ||
    value === "PLAYBACK_SOURCE_RESOLUTION_FAILED" ||
    value === "INVALID_BRIDGE_RESPONSE"
  );
}
