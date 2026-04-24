/**
 * Detector-catalog normalization for the frontend bridge contract.
 *
 * This file owns detector-list coercion only; transport envelopes and typed
 * errors stay in `contractErrors`, and session normalization stays separate.
 */

import type { DetectorOption } from "../types";
import {
  isDetectorCategory,
  isDetectorOrigin,
  isDetectorStatus,
  isInputMode,
  isNonEmptyString,
  isRecord,
  isStringArray,
} from "./contractShared";

export function normalizeDetectorOptions(value: unknown): DetectorOption[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(isDetectorOption);
}

function isDetectorOption(value: unknown): value is DetectorOption {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.id) &&
    typeof value.display_name === "string" &&
    typeof value.description === "string" &&
    isDetectorCategory(value.category) &&
    isDetectorOrigin(value.origin) &&
    isDetectorStatus(value.status) &&
    (typeof value.default_rule_id === "string" || value.default_rule_id === null) &&
    typeof value.default_selected === "boolean" &&
    typeof value.produces_alerts === "boolean" &&
    Array.isArray(value.supported_modes) &&
    value.supported_modes.every(isInputMode) &&
    isStringArray(value.supported_suffixes)
  );
}
