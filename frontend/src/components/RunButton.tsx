interface RunButtonProps {
  disabled: boolean;
  running: boolean;
  onClick: () => void;
  label?: string;
}

export function RunButton({
  disabled,
  running,
  onClick,
  label = "Start Monitoring",
}: RunButtonProps) {
  return (
    <button className="run-button" disabled={disabled || running} onClick={onClick}>
      {running ? "Starting Session..." : label}
    </button>
  );
}
