import type { DetectorOption, SessionSummary } from "../types";

interface SessionHistoryProps {
  sessions: SessionSummary[];
  detectors: DetectorOption[];
}

export function SessionHistory({ sessions, detectors }: SessionHistoryProps) {
  return (
    <section className="monitor-card">
      <div className="monitor-card__header">
        <h2>Alerts</h2>
        <span>{sessions.length} recorded</span>
      </div>

      <div className="history-list">
        {sessions.length === 0 ? (
          <p className="empty-state">Alerts will appear here after monitoring starts.</p>
        ) : (
          sessions.map((session) => (
            <article key={session.session_id} className="history-row">
              <div>
                <strong>{session.session_id}</strong>
                <p>{session.input_path}</p>
              </div>
              <div className="history-row__meta">
                <span>{session.status}</span>
                <span>{formatDetectors(session.selected_detectors, detectors)}</span>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function formatDetectors(ids: string[], detectors: DetectorOption[]): string {
  return ids
    .map(
      (id) =>
        detectors.find((detector) => detector.id === id)?.display_name ?? id,
    )
    .join(", ");
}
