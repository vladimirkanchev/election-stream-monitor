import type { DetectorOption, SessionSummary } from "../types";

interface SessionSummaryCardProps {
  summary: SessionSummary | null;
  detectors: DetectorOption[];
}

export function SessionSummaryCard({
  summary,
  detectors,
}: SessionSummaryCardProps) {
  if (!summary) {
    return (
      <section className="summary-card summary-card--empty">
        <h2>Session Summary</h2>
        <p>No session has been run yet.</p>
      </section>
    );
  }

  const selectedNames = summary.selected_detectors.map(
    (detectorId) =>
      detectors.find((detector) => detector.id === detectorId)?.display_name ??
      detectorId,
  );

  return (
    <section className="summary-card">
      <h2>Session Summary</h2>
      <dl>
        <div>
          <dt>Session ID</dt>
          <dd>{summary.session_id}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{summary.status}</dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{summary.mode}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{summary.input_path}</dd>
        </div>
        <div>
          <dt>Chosen detectors</dt>
          <dd>{selectedNames.join(", ") || "None"}</dd>
        </div>
      </dl>
    </section>
  );
}
