import type { DetectorOption } from "../types";

interface DetectorCatalogProps {
  detectors: DetectorOption[];
  selected: string[];
  onChange: (selectedIds: string[]) => void;
  disabled?: boolean;
}

export function DetectorCatalog({
  detectors,
  selected,
  onChange,
  disabled = false,
}: DetectorCatalogProps) {
  const toggle = (detectorId: string) => {
    if (selected.includes(detectorId)) {
      onChange(selected.filter((id) => id !== detectorId));
      return;
    }
    onChange([...selected, detectorId]);
  };

  return (
    <section className="detector-catalog">
      <div className="detectors__header">
        <h2>Detectors</h2>
        <span>{selected.length} selected</span>
      </div>
      <div className="detector-catalog__grid">
        {detectors.map((detector) => (
          <article
            key={detector.id}
            className={`detector-card ${
              selected.includes(detector.id) ? "detector-card--selected" : ""
            }`}
          >
            <strong>{detector.display_name}</strong>

            <label className="detector-card__toggle">
              <input
                checked={selected.includes(detector.id)}
                disabled={disabled}
                type="checkbox"
                onChange={() => toggle(detector.id)}
              />
              <span>Select</span>
            </label>
          </article>
        ))}
      </div>
    </section>
  );
}
