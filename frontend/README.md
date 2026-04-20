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
- The Electron runtime now uses a FastAPI-backed local bridge for the main
  detector/session/playback flow.
- The Python backend contract for that local runtime still builds on:
  - [`../src/analyzer_registry.py`](../src/analyzer_registry.py)
  - [`../src/session_cli.py`](../src/session_cli.py)
  - [`../src/session_runner.py`](../src/session_runner.py)
  - [`../src/session_io.py`](../src/session_io.py)

## Runtime Model

A browser-only React app cannot directly launch local Python commands or read
local session files without a host bridge. In the desktop runtime, Electron now
owns that bridge and talks to the local FastAPI backend for normal operation.

The Python CLI is still useful for tooling/debugging tasks, but it is no longer
the normal frontend runtime transport.

## Useful Tooling Commands

List detectors:

```bash
python3 src/session_cli.py list-detectors --mode video_segments
```

Start one session:

```bash
python3 src/session_cli.py start-session \
  --mode video_segments \
  --input-path ./data/streams/segments \
  --detector video_metrics
```

Read one session snapshot:

```bash
python3 src/session_cli.py read-session --session-id <session-id>
```

Cancel one session:

```bash
python3 src/session_cli.py cancel-session --session-id <session-id>
```

Resolve one playback source:

```bash
python3 src/session_cli.py resolve-playback-source \
  --mode video_segments \
  --input-path ./data/streams/segments
```

## Run The Frontend

After installing the frontend dependencies:

```bash
cd frontend
npm install
npm run dev
```

The current UI runs through Electron and the local FastAPI backend during
normal desktop development.
