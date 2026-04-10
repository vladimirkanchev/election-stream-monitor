import type { SessionProgress, SessionSummary } from "../types";

interface SessionStatusProps {
  session: SessionSummary | null;
  progress: SessionProgress | null;
}

export function SessionStatus({ session, progress }: SessionStatusProps) {
  return (
    <section className="monitor-card">
      <div className="monitor-card__header">
        <h2>Session Status</h2>
        <span>{progress?.status ?? session?.status ?? "pending"}</span>
      </div>

      <dl className="status-grid">
        <div>
          <dt>Session ID</dt>
          <dd>{session?.session_id ?? "not started"}</dd>
        </div>
        <div>
          <dt>Processed</dt>
          <dd>
            {progress ? `${progress.processed_count}/${progress.total_count}` : "0/0"}
          </dd>
        </div>
        <div>
          <dt>Alerts</dt>
          <dd>{progress?.alert_count ?? 0}</dd>
        </div>
        <div>
          <dt>Latest detector</dt>
          <dd>{progress?.latest_result_detector ?? "waiting"}</dd>
        </div>
      </dl>
    </section>
  );
}
