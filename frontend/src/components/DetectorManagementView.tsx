import type { DetectorOption } from "../types";

interface DetectorManagementViewProps {
  detectors: DetectorOption[];
}

export function DetectorManagementView({
  detectors,
}: DetectorManagementViewProps) {
  return (
    <section className="monitor-card monitor-card--quiet">
      <div className="monitor-card__header">
        <h2>Advanced</h2>
        <span>{detectors.length} available</span>
      </div>

      <p className="management-copy">
        Detector management and AI-assisted detector generation can be added later.
      </p>
    </section>
  );
}
