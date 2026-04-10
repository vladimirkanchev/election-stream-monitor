import type { AlertEvent } from "../types";
import type { AlertFeedItem } from "../presenters/alertFeed";

interface AlertFeedProps {
  items: AlertFeedItem[];
  onSelect: (alert: AlertEvent) => void;
  monitoringStarted: boolean;
  totalRaisedCount?: number;
}

export function AlertFeed({
  items,
  onSelect,
  monitoringStarted,
  totalRaisedCount,
}: AlertFeedProps) {
  return (
    <section className="monitor-card">
      <div className="monitor-card__header">
        <h2>Alerts</h2>
        <span>
          {items.length} shown
          {typeof totalRaisedCount === "number" ? ` / ${totalRaisedCount} raised` : ""}
        </span>
      </div>
      {typeof totalRaisedCount === "number" ? (
        <p className="alert-feed__summary">
          Shown follows playback. Raised follows backend analysis.
        </p>
      ) : null}

      <div className="alert-feed">
        {items.length === 0 ? (
          <p className="empty-state">
            {monitoringStarted
              ? "No alerts have been raised for this session yet."
              : "Alerts will appear here after monitoring starts."}
          </p>
        ) : (
          items.map((item) => (
            <button
              key={item.key}
              className={`alert-row alert-row--${item.severity}`}
              type="button"
              onClick={() => onSelect(item.alert)}
            >
              <div className="alert-row__summary">
                <strong>{item.title}</strong>
                <p className="alert-row__message">{item.message}</p>
              </div>
              <div className="alert-row__meta">
                <span>{item.sourceLabel}</span>
                <span>{item.timestampLabel}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </section>
  );
}
