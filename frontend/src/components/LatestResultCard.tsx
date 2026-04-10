import type { DetectorOption, ResultEvent } from "../types";

interface LatestResultCardProps {
  latestResult: ResultEvent | null;
  detectors: DetectorOption[];
  onOpenDetails: () => void;
}

export function LatestResultCard({
  latestResult,
  detectors,
  onOpenDetails,
}: LatestResultCardProps) {
  const detectorName = latestResult
    ? detectors.find((detector) => detector.id === latestResult.detector_id)
        ?.display_name ?? latestResult.detector_id
    : "No result yet";

  return (
    <section className="monitor-card">
      <div className="monitor-card__header">
        <h2>Latest Result</h2>
        <span>{detectorName}</span>
      </div>

      {latestResult ? (
        <>
          <pre className="result-preview">
            {JSON.stringify(latestResult.payload, null, 2)}
          </pre>
          <button className="detail-button" type="button" onClick={onOpenDetails}>
            Open detail drawer
          </button>
        </>
      ) : (
        <p className="empty-state">Detector output will appear here while the session runs.</p>
      )}
    </section>
  );
}
