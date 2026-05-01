import type { DetectorOption, InputMode } from "../types";

export function getVisibleDetectors(
  detectors: DetectorOption[],
  sourceKind: InputMode,
): DetectorOption[] {
  return detectors.filter((detector) => detector.supported_modes.includes(sourceKind));
}

export function getDefaultDetectorIds(detectors: DetectorOption[]): string[] {
  return detectors
    .filter((detector) => detector.default_selected)
    .map((detector) => detector.id);
}

export function getNextSelectedDetectors(
  current: string[],
  visibleDetectors: DetectorOption[],
  frozen: boolean,
): string[] {
  if (frozen) {
    return current;
  }

  const supportedDetectorIds = new Set(visibleDetectors.map((detector) => detector.id));
  const defaultDetectorIds = getDefaultDetectorIds(visibleDetectors);
  const preserved = current.filter((detectorId) => supportedDetectorIds.has(detectorId));
  return preserved.length > 0 ? preserved : defaultDetectorIds;
}

export function haveSameIds(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }

  return true;
}
