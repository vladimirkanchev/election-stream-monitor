import { useEffect, useState } from "react";

import {
  createMonitorSource,
  updateMonitorSourceKind,
  updateMonitorSourcePath,
} from "../sourceModel";
import type { DetectorOption, InputMode, MonitorSource } from "../types";
import {
  getNextSelectedDetectors,
  getVisibleDetectors,
  haveSameIds,
} from "../viewModels/setupState";

interface UseSetupStateArgs {
  detectors: DetectorOption[];
  frozen: boolean;
}

interface UseSetupStateResult {
  source: MonitorSource;
  visibleDetectors: DetectorOption[];
  selectedDetectors: string[];
  setSourceKind: (kind: InputMode) => void;
  setSourcePath: (path: string) => void;
  setSelectedDetectors: (selectedIds: string[]) => void;
}

/**
 * Own the setup-screen source and detector selection state.
 *
 * Source updates always go through the source-model helpers so `kind`, `path`,
 * and `access` stay in sync when the user edits the path or switches modes.
 */
export function useSetupState({
  detectors,
  frozen,
}: UseSetupStateArgs): UseSetupStateResult {
  const [source, setSource] = useState<MonitorSource>(
    createMonitorSource("video_segments", "/data/streams/segments"),
  );
  const [selectedDetectors, setSelectedDetectors] = useState<string[]>([]);

  const visibleDetectors = getVisibleDetectors(detectors, source.kind);

  useEffect(() => {
    setSelectedDetectors((current) => {
      const nextSelection = getNextSelectedDetectors(current, visibleDetectors, frozen);
      if (haveSameIds(current, nextSelection)) {
        return current;
      }
      return nextSelection;
    });
  }, [frozen, visibleDetectors]);

  const setSourceKind = (kind: InputMode) => {
    setSource((current) => updateMonitorSourceKind(current, kind));
  };

  const setSourcePath = (path: string) => {
    setSource((current) => updateMonitorSourcePath(current, path));
  };

  return {
    source,
    visibleDetectors,
    selectedDetectors,
    setSourceKind,
    setSourcePath,
    setSelectedDetectors,
  };
}
