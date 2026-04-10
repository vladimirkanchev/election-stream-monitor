import { getAlertPlaybackMomentLabel } from "../playbackMoments";
import type { AlertEvent, DetectorOption, InputMode } from "../types";
import type { SegmentStartTimes } from "../types";

interface AlertDetailsDrawerProps {
  alert: AlertEvent | null;
  detectors: DetectorOption[];
  sourceKind: InputMode;
  segmentStartTimes: SegmentStartTimes;
  onClose: () => void;
}

export function AlertDetailsDrawer({
  alert,
  detectors,
  sourceKind,
  segmentStartTimes,
  onClose,
}: AlertDetailsDrawerProps) {
  if (!alert) {
    return null;
  }

  const detectorName =
    detectors.find((detector) => detector.id === alert.detector_id)?.display_name ??
    alert.detector_id;
  const playbackMomentLabel = getAlertPlaybackMomentLabel(
    alert,
    sourceKind,
    segmentStartTimes,
  );

  return (
    <aside className="drawer-backdrop" onClick={onClose}>
      <div
        className="drawer"
        onClick={(event) => {
          event.stopPropagation();
        }}
      >
        <div className="drawer__header">
          <div>
            <h2>{alert.title}</h2>
            <p>{detectorName}</p>
          </div>
          <button className="drawer__close" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <dl className="drawer__grid">
          <div>
            <dt>Severity</dt>
            <dd>{alert.severity}</dd>
          </div>
          <div>
            <dt>Playback moment</dt>
            <dd>{playbackMomentLabel}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{alert.source_name}</dd>
          </div>
          <div>
            <dt>Detector</dt>
            <dd>{detectorName}</dd>
          </div>
          <div>
            <dt>Detected at</dt>
            <dd>{alert.timestamp_utc}</dd>
          </div>
        </dl>
        <p className="drawer__message">{alert.message}</p>
      </div>
    </aside>
  );
}
