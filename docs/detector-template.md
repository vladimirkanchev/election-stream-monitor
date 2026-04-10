# Detector Template

This document gives one small template for adding a new detector in the current
project.

Use it as a reference, not a strict generator.

## 1. Detector function

Example shape:

```python
from pathlib import Path
import time

from analyzer_contract import AnalyzerResult


def analyze_example_detector(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalyzerResult:
    _ = prefix
    start_time = time.time()

    example_score = 0.42

    return {
        "analyzer": "example_detector",
        "source_type": "video",
        "source_group": source_group or file_path.parent.name or file_path.name,
        "source_name": source_name or file_path.name,
        "window_index": window_index,
        "window_start_sec": window_start_sec,
        "window_duration_sec": window_duration_sec,
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "processing_sec": round(time.time() - start_time, 3),
        "example_score": example_score,
        "example_detected": example_score > 0.4,
    }
```

## 2. Registry entry

Add it in [`src/analyzer_registry.py`](../src/analyzer_registry.py):

```python
AnalyzerRegistration(
    name="example_detector",
    analyzer=analyze_example_detector,
    store_name="example_metrics",
    supported_modes=("video_segments", "video_files"),
    supported_suffixes=(".ts", ".mp4"),
    display_name="Example Detector",
    description="Short user-facing explanation of what it checks.",
    category="quality",
    origin="built_in",
    status="optional",
    default_rule_id="example_detector.default_rule",
    default_selected=False,
    produces_alerts=True,
)
```

## 3. Rule example

Add it in [`src/alert_rules.py`](../src/alert_rules.py):

```python
EXAMPLE_RULE = AlertRule(
    detector_id="example_detector",
    title="Example alert",
    should_alert=lambda row: bool(row.get("example_detected")),
    message_builder=lambda row: (
        f"{row.get('source_name', 'Input')} triggered the example rule. "
        f"Score: {row.get('example_score')}."
    ),
)
```

Then include it in the detector-to-rule mapping and, if appropriate, the
built-in rule metadata catalog.

## 4. Schema/store update if needed

If the detector needs a new schema family:

- add columns in [`src/config.py`](../src/config.py)
- add or reuse a store in [`src/stores.py`](../src/stores.py)

If the detector can reuse an existing schema family, prefer that over adding a
new store too early.

## 5. Tests

At minimum:

- detector test
- rule test
- registry or processor test
- session or real-fixture test if timing or rolling behavior matters

## Good habits

Prefer:

- flat outputs
- explicit registration
- readable thresholds
- normalized values when possible

Avoid:

- detector code writing alerts directly
- putting business logic in the frontend first
- overengineering the detector class structure
- skipping the current shared metadata fields just because the detector is small
