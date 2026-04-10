# Frontend Iteration 3

This frontend is the React shell for the richer local monitoring workflow.

## Current State

- The UI includes:
  - source mode selector
  - file or folder path input
  - richer detector catalog cards
  - start button
  - live monitor screen
  - current status card
  - alert feed
  - latest result preview
  - session history
  - alert detail drawer
- The detector list and live session flow currently use a demo bridge in
  [`src/bridge/demoBridge.ts`](./src/bridge/demoBridge.ts).
- The Python backend contract for the real local bridge already exists in:
  - [`../src/analyzer_registry.py`](../src/analyzer_registry.py)
  - [`../src/session_cli.py`](../src/session_cli.py)
  - [`../src/session_runner.py`](../src/session_runner.py)
  - [`../src/session_io.py`](../src/session_io.py)

## Why It Uses a Demo Bridge For Now

A browser-only React app cannot directly launch local Python commands or read
local session files without a host bridge. For the no-FastAPI path, the next
step is to add a small Node/Electron/Tauri bridge that:

1. runs `python3 src/session_cli.py list-detectors`
2. runs `python3 src/session_cli.py run-session ...`
3. polls `python3 src/session_cli.py read-session --session-id ...`
4. returns progress, alerts, and results back to the React app

## Expected Real Bridge Commands

List detectors:

```bash
python3 src/session_cli.py list-detectors --mode video_segments
```

Run one session:

```bash
python3 src/session_cli.py run-session \
  --mode video_segments \
  --input-path ./data/streams/segments \
  --detector video_metrics
```

## Run The Frontend

After installing the frontend dependencies:

```bash
cd frontend
npm install
npm run dev
```

The current UI is a realistic frontend shell for Iteration 1, but it still
needs the real local bridge to launch Python sessions and poll live session
files from the browser flow.
