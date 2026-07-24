# Frontend

This frontend is the React/Electron shell for the local monitoring workflow.

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
- The Electron runtime uses a FastAPI-backed local bridge for the main
  detector, session, and playback flow.
- The main Python ownership points for that runtime are:
  - [`../src/detectors/registry.py`](../src/detectors/registry.py)
  - [`../src/session_service.py`](../src/session_service.py)
  - [`../src/session_runner.py`](../src/session_runner.py)
  - [`../src/session_store.py`](../src/session_store.py)

## Runtime Model

A browser-only React app cannot directly launch local Python commands or read
local session files without a host bridge. In the desktop runtime, Electron now
owns that bridge, starts/waits for the local FastAPI backend as needed, and
talks to it for normal operation.

The Python CLI is still useful for tooling and debugging, but it is no longer
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
npm ci
npm run dev
```

Use Node `22` and npm `11.15.0`, matching the root `.nvmrc` and this
package's `packageManager` declaration. CI pins that npm release and retries
one transient dependency or Electron artifact download; persistent failures
remain failures.

The current UI runs through Electron and the local FastAPI backend during
normal desktop development.
