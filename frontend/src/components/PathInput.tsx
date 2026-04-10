import type { InputMode } from "../types";
import { getSourcePathHint, getSourcePathPlaceholder } from "../uiText";

interface PathInputProps {
  mode: InputMode;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function PathInput({
  mode,
  value,
  onChange,
  disabled = false,
}: PathInputProps) {
  return (
    <label className="field">
      <span className="field__label">File or folder path</span>
      <input
        className="field__input"
        disabled={disabled}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={getSourcePathPlaceholder(mode)}
      />
      <span className="field__hint">{getSourcePathHint(mode)}</span>
    </label>
  );
}
