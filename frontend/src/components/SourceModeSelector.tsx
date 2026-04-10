import type { InputMode } from "../types";

interface SourceModeSelectorProps {
  value: InputMode;
  onChange: (value: InputMode) => void;
  disabled?: boolean;
}

const OPTIONS: Array<{ value: InputMode; label: string }> = [
  { value: "video_segments", label: "Video segments (.ts)" },
  { value: "video_files", label: "Video files (.mp4)" },
  { value: "api_stream", label: "API stream URL" },
];

export function SourceModeSelector({
  value,
  onChange,
  disabled = false,
}: SourceModeSelectorProps) {
  return (
    <label className="field">
      <span className="field__label">Source mode</span>
      <select
        className="field__input"
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value as InputMode)}
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
