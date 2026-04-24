/**
 * Shared low-level validators and enum guards used by bridge normalizers.
 *
 * Keep this file intentionally small and infrastructure-focused so the domain
 * normalizers can read top-down without repeating tiny shape checks.
 */

import type { DetectorOption, InputMode, SessionSummary } from "../types";

export const VALID_INPUT_MODES: InputMode[] = [
  "video_segments",
  "video_files",
  "api_stream",
];

export const VALID_SESSION_STATUSES = [
  "pending",
  "running",
  "cancelling",
  "cancelled",
  "completed",
  "failed",
] as const;

export const VALID_DETECTOR_STATUSES = ["core", "optional", "experimental"] as const;
export const VALID_DETECTOR_ORIGINS = ["built_in", "user"] as const;
export const VALID_DETECTOR_CATEGORIES = ["quality", "visibility", "stability"] as const;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isInputMode(value: unknown): value is InputMode {
  return typeof value === "string" && VALID_INPUT_MODES.includes(value as InputMode);
}

export function isSessionStatus(
  value: unknown,
): value is SessionSummary["status"] {
  return (
    typeof value === "string" &&
    VALID_SESSION_STATUSES.includes(value as SessionSummary["status"])
  );
}

export function isDetectorStatus(
  value: unknown,
): value is DetectorOption["status"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_STATUSES.includes(value as DetectorOption["status"])
  );
}

export function isDetectorOrigin(
  value: unknown,
): value is DetectorOption["origin"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_ORIGINS.includes(value as DetectorOption["origin"])
  );
}

export function isDetectorCategory(
  value: unknown,
): value is DetectorOption["category"] {
  return (
    typeof value === "string" &&
    VALID_DETECTOR_CATEGORIES.includes(value as DetectorOption["category"])
  );
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

export function normalizeNullableString(value: unknown): string | null {
  return isNullableString(value) ? value : null;
}
