import type { AlertEvent } from "../types";
import type { AlertFeedItem } from "../presenters/alertFeed";

interface AlertFeedProps {
  items: AlertFeedItem[];
  onSelect: (alert: AlertEvent) => void;
  monitoringStarted: boolean;
  totalRaisedCount?: number;
  playbackFiltered?: boolean;
}

export function AlertFeed({
  items,
  onSelect,
  monitoringStarted,
  totalRaisedCount,
  playbackFiltered = false,
}: AlertFeedProps) {
  const hiddenRaisedAlerts = typeof totalRaisedCount === "number"
    ? Math.max(0, totalRaisedCount - items.length)
    : 0;

  return (
    <section className="monitor-card">
      <div className="monitor-card__header">
        <h2>Alerts</h2>
        <span>
          {formatAlertCountLabel({
            visibleCount: items.length,
            totalRaisedCount,
            playbackFiltered,
          })}
        </span>
      </div>
      {typeof totalRaisedCount === "number" && playbackFiltered ? (
        <p className="alert-feed__summary">
          Visible now follows playback. Raised follows backend analysis.
        </p>
      ) : null}

      <div className="alert-feed">
        {items.length === 0 ? (
          <p className="empty-state">
            {buildEmptyStateMessage({
              monitoringStarted,
              hiddenRaisedAlerts,
            })}
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

function buildEmptyStateMessage(args: {
  monitoringStarted: boolean;
  hiddenRaisedAlerts: number;
}): string {
  const { monitoringStarted, hiddenRaisedAlerts } = args;

  if (hiddenRaisedAlerts > 0) {
    return "Alerts have already been raised and will appear here as playback reaches them.";
  }

  if (monitoringStarted) {
    return "No alerts have been raised for this session yet.";
  }

  return "Alerts will appear here after monitoring starts.";
}

function formatAlertCountLabel(args: {
  visibleCount: number;
  totalRaisedCount?: number;
  playbackFiltered: boolean;
}): string {
  const { visibleCount, totalRaisedCount, playbackFiltered } = args;

  if (typeof totalRaisedCount !== "number") {
    return `${visibleCount} visible`;
  }

  if (playbackFiltered) {
    return `${visibleCount} visible now / ${totalRaisedCount} raised`;
  }

  return `${totalRaisedCount} raised`;
}
