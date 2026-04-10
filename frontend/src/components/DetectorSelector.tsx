import type { DetectorOption } from "../types";

interface DetectorSelectorProps {
  detectors: DetectorOption[];
  selected: string[];
  onChange: (selectedIds: string[]) => void;
}

export function DetectorSelector({
  detectors,
  selected,
  onChange,
}: DetectorSelectorProps) {
  const toggle = (detectorId: string) => {
    if (selected.includes(detectorId)) {
      onChange(selected.filter((id) => id !== detectorId));
      return;
    }
    onChange([...selected, detectorId]);
  };

  return (
    <section className="detectors">
      <div className="detectors__header">
        <h2>Detectors For This Session</h2>
        <span>{selected.length} selected</span>
      </div>

      <div className="detectors__list">
        {detectors.map((detector) => (
          <label key={detector.id} className="detector-row">
            <input
              type="checkbox"
              checked={selected.includes(detector.id)}
              onChange={() => toggle(detector.id)}
            />
            <div className="detector-row__text">
              <div className="detector-row__title">
                <strong>{detector.display_name}</strong>
                <span>{detector.status}</span>
              </div>
              <p>{detector.description}</p>
            </div>
          </label>
        ))}
      </div>
    </section>
  );
}
